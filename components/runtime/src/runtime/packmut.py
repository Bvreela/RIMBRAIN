"""Pack mutation ops engine (feature 016; FR-1406).

One vocabulary for every mutation path — feature-009 rules-only
remediations, feature-005 planner `policy_mutations`, and the
`rimbrain.improve` reflection proposals all compile down to these ops:

    set     {op, path, value}  — write dict key at path (intermediate
                                 dicts created); on a list node the next
                                 segment selects by element `id`
    append  {op, path, value}  — push value onto the list at path
    remove  {op, path}         — drop the addressed dict key, or the
                                 list element whose `id` == last segment
    upsert  {op, path, value}  — path names a list; replace the element
                                 whose `id` == value['id'], else append

Paths are dotted segments; when the current node is a list a segment
matches the element whose ``id`` field equals it (numeric segments index
positionally as a fallback). Anything unaddressable makes the op a no-op
and reports the miss — a proposal that changes nothing is vacuous and
the gate rejects it.
"""

from __future__ import annotations


def _walk(node, segments: list[str]):
    """Resolve `segments[:-1]` to the parent node of the final segment.

    Returns (parent, last_segment, miss_reason). Dicts descend by key
    (created on demand for `set`-style writes is the CALLER's choice —
    _walk only traverses existing structure); lists select the element
    whose `id` == segment, else positional index."""
    for i, seg in enumerate(segments[:-1]):
        nxt = None
        if isinstance(node, dict):
            nxt = node.get(seg)
        elif isinstance(node, list):
            nxt = next((e for e in node
                        if isinstance(e, dict) and e.get("id") == seg),
                       None)
            if nxt is None and seg.isdigit() and int(seg) < len(node):
                nxt = node[int(seg)]
        if nxt is None:
            return None, segments[-1], f"path dead-ends at '{seg}'"
        node = nxt
    return node, segments[-1], None


def _op_set(doc: dict, path: str, value) -> bool:
    keys = [k for k in path.split(".") if k]
    if not keys:
        return False
    node = doc
    for seg in keys[:-1]:
        if isinstance(node, dict):
            nxt = node.get(seg)
            if not isinstance(nxt, (dict, list)):
                nxt = {}
                node[seg] = nxt
            node = nxt
        elif isinstance(node, list):
            hit = next((e for e in node
                        if isinstance(e, dict) and e.get("id") == seg),
                       None)
            if hit is None and seg.isdigit() and int(seg) < len(node):
                hit = node[int(seg)]
            if not isinstance(hit, (dict, list)):
                return False
            node = hit
        else:
            return False
    last = keys[-1]
    if isinstance(node, dict):
        node[last] = value
        return True
    if isinstance(node, list):
        hit = next((e for e in node
                    if isinstance(e, dict) and e.get("id") == last), None)
        if hit is None and last.isdigit() and int(last) < len(node):
            hit = node[int(last)]
        if isinstance(hit, dict):
            hit.clear()
            hit.update(value if isinstance(value, dict) else {"id": last})
            return True
    return False


def _op_append(doc: dict, path: str, value) -> bool:
    parent, last, miss = _walk(doc, path.split("."))
    if miss is not None:
        return False
    node = parent.get(last) if isinstance(parent, dict) else None
    if isinstance(node, list):
        node.append(value)
        return True
    return False


def _op_remove(doc: dict, path: str) -> bool:
    parent, last, miss = _walk(doc, path.split("."))
    if miss is not None:
        return False
    if isinstance(parent, dict):
        node = parent.get(last)
        if isinstance(node, list):
            return False  # remove needs an element, not the whole list —
            # address it: govern.goals.<id>
        if last in parent:
            del parent[last]
            return True
        return False
    if isinstance(parent, list):
        for i, e in enumerate(parent):
            if isinstance(e, dict) and e.get("id") == last:
                del parent[i]
                return True
        if last.isdigit() and int(last) < len(parent):
            del parent[int(last)]
            return True
    return False


def _op_upsert(doc: dict, path: str, value) -> bool:
    if not isinstance(value, dict) or not value.get("id"):
        return False
    parent, last, miss = _walk(doc, path.split("."))
    if miss is not None:
        return False
    node = parent.get(last) if isinstance(parent, dict) else None
    if not isinstance(node, list):
        return False
    rid = value["id"]
    for i, e in enumerate(node):
        if isinstance(e, dict) and e.get("id") == rid:
            node[i] = value
            return True
    node.append(value)
    return True


_OPS = {"set": _op_set, "append": _op_append, "remove": _op_remove,
        "upsert": _op_upsert}


def resolve(doc, path: str):
    """Return the node AT `path` (None when unresolvable). Same traversal
    rules as the ops: dict segments by key, list segments by element id."""
    node = doc
    for seg in [s for s in path.split(".") if s]:
        if isinstance(node, dict):
            node = node.get(seg)
        elif isinstance(node, list):
            node = next(
                (e for e in node
                 if isinstance(e, dict) and e.get("id") == seg),
                node[int(seg)]
                if seg.isdigit() and int(seg) < len(node) else None)
        else:
            return None
    return node


def compile_legacy(ops: list[dict] | None, doc: dict) -> list[dict]:
    """feature-009 remediation vocabulary -> packmut ops.

    `set_cfg`->set, `append`->append (only when the target resolves to a
    list — a legacy append miss was a silent no-op), `drop_template`/
    `drop_rule`->remove for ids actually present (each id lives in exactly
    one list; emitting removes for every candidate list would fake misses
    the gate then rejects)."""
    out: list[dict] = []
    for op in ops or []:
        kind = op.get("op")
        if kind == "set_cfg":
            out.append({"op": "set", "path": op.get("path", ""),
                        "value": op.get("value")})
        elif kind == "append":
            if isinstance(resolve(doc, op.get("path", "")), list):
                out.append({"op": "append", "path": op["path"],
                            "value": op.get("value")})
        elif kind == "drop_template":
            have = {t.get("id") for t in doc.get("templates") or []
                    if isinstance(t, dict)}
            out += [{"op": "remove", "path": f"templates.{i}"}
                    for i in (op.get("ids") or []) if i in have]
        elif kind == "drop_rule":
            lists = [("universal.rules", resolve(doc, "universal.rules")),
                     ("emergency", doc.get("emergency"))]
            lists += [(f"combat.{k}.rules", v.get("rules"))
                      for k, v in (doc.get("combat") or {}).items()
                      if isinstance(v, dict)]
            for rid in op.get("ids") or []:
                for p, lst in lists:
                    if isinstance(lst, list) and any(
                            isinstance(e, dict) and e.get("id") == rid
                            for e in lst):
                        out.append({"op": "remove",
                                    "path": f"{p}.{rid}"})
    return out


# Mutable pack surfaces (feature 017, T036): every v1 surface the
# reflection pipeline may touch, plus `decision_map`/`combat` — retained
# v0 blocks a proposal may still legitimately target. Pack identity
# (`pack_id`, `schema_version`, `meta`, `revision`, `class`, `hash`) is
# never mutable. Ops written against v0 paths are rewritten through the
# migration map before applying (loaded packs are always v1 shape).
MUTABLE_ROOTS = {
    "phases", "standing_goals", "action_list", "decide", "reflexes",
    "rules", "options", "senses", "metrics", "capabilities", "mutate",
    "improve", "vitals", "blueprints", "defense", "combat", "cycle",
    "decision_map",
}


def rewrite_path(path: str) -> str:
    """v0 dialect -> v1 canonical path (templates.v0_to_v1_path)."""
    from .templates import v0_to_v1_path
    return v0_to_v1_path(path)


def apply_ops(doc: dict, ops: list[dict] | None) -> tuple[bool, list[str]]:
    """Apply a mutation set in order. Returns (changed, misses) — every
    unaddressable op lands in `misses` so the gate can report it. Paths
    are normalized to the v1 surface and must root in MUTABLE_ROOTS."""
    changed, misses = False, []
    for i, op in enumerate(ops or []):
        kind = (op or {}).get("op")
        fn = _OPS.get(kind)
        if fn is None:
            misses.append(f"ops[{i}]: unknown op {kind!r}")
            continue
        raw = str(op.get("path", ""))
        path = rewrite_path(raw)
        root = path.split(".", 1)[0]
        if root not in MUTABLE_ROOTS:
            misses.append(f"ops[{i}]: '{op.get('path', '')}' is not a "
                          f"mutable surface")
            continue
        if path != raw and kind == "set" \
                and resolve(doc, ".".join(path.split(".")[:-1])) is None:
            path = raw  # rewritten parent doesn't exist — set must not
            # fabricate it; apply to the original v0 path
        if kind == "remove":
            ok = fn(doc, path)
        else:
            ok = fn(doc, path, op.get("value"))
        if not ok and path != raw:
            # the v0 path may still resolve on an unmigrated doc —
            # retry the original spelling before reporting a miss
            if kind == "remove":
                ok = fn(doc, raw)
            else:
                ok = fn(doc, raw, op.get("value"))
        changed |= ok
        if not ok:
            misses.append(f"ops[{i}]: {kind} '{op.get('path', '')}' "
                          "did not apply")
    return changed, misses
