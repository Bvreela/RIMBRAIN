"""Brain policy engine (feature 012; FR-1001, UR-BRN-011..014).

All gameplay strategy lives in RimBrain packs. This module provides only
capability primitives — the vocabulary packs compose:

- ``resolve(spec, ctx)`` — ``@cfg:path``, ``@obs:path``, ``@var:name``,
  ``@fn:name(arg, …)`` (args nest). FNs are generic mechanics; every
  threshold, ordering, and preference list arrives as an argument.
- ``check(pred, ctx)`` — ``{field, op, value}`` predicates with
  ``all``/``any``/``not`` combinators. Missing data evaluates False
  (fail-closed) — never guessed.
- ``run_steps(steps, dispatcher, ctx)`` — ordered writes through the
  single dispatcher; per-step ``when``/``needs``/``for_each``/``times``/
  ``cooldown_polls``/``optional``.
- ``run_rules(rules, dispatcher, ctx)`` — per-poll invariant rules:
  ``for_each`` selector (or ``@fn:`` list) + ``when`` + ordered ``try``
  alternatives + per-candidate cooldown.
- ``validate_policy(pack)`` — fail-closed audit: unknown ``@fn:``,
  selector, op, or template id is a pack error, never silently ignored.

The engine knows no RimWorld def names, phase ids, or strategy orderings.
"""

from __future__ import annotations

import re

_FN_RE = re.compile(r"^@fn:(\w+)\((.*)\)$", re.S)


def _dig(obj, path):
    """Dotted path with list-index segments; None-safe."""
    cur = obj
    for part in str(path).split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)) and part.lstrip("-").isdigit():
            i = int(part)
            cur = cur[i] if -len(cur) <= i < len(cur) else None
        else:
            return None
    return cur


def _split_args(s: str) -> list[str]:
    """Split on top-level commas (nested parens/brackets/quotes safe)."""
    out, depth, q, cur = [], 0, None, []
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _literal(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    if s in ("null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def resolve(spec, ctx):
    """Resolve a pack value against ctx. ``@``-strings resolve; dicts,
    lists, and literals pass through element-wise."""
    if isinstance(spec, dict):
        return {k: resolve(v, ctx) for k, v in spec.items()}
    if isinstance(spec, list):
        return [resolve(v, ctx) for v in spec]
    if not isinstance(spec, str) or not spec.startswith("@"):
        return spec
    if spec.startswith("@cfg:"):
        return _dig(ctx.cfg, spec[5:])
    if spec.startswith("@obs:"):
        return _dig(ctx.obs, spec[5:])
    if spec.startswith("@var:"):
        v = _dig(ctx.vars, spec[5:])
        if v is None:
            v = _dig(ctx.persist, spec[5:])
        return v
    m = _FN_RE.match(spec)
    if m:
        name, argstr = m.group(1), m.group(2)
        fn = FN.get(name)
        if fn is None:
            return None  # fail-closed; validate_policy names it earlier
        args = [resolve(a, ctx) if a.strip().startswith("@")
                else _literal(a) for a in _split_args(argstr)]
        try:
            return fn(ctx, *args)
        except Exception:
            return None
    return spec


# -- predicates ---------------------------------------------------------------

_OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "empty",
        "not_empty", "truthy", "falsy", "contains", "contains_any",
        "matches", "absent", "present")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check(pred, ctx) -> bool:
    """Evaluate a predicate; unknown ops and unresolvable fields fail
    closed (False)."""
    if not isinstance(pred, dict):
        return bool(pred)
    if "all" in pred:
        return all(check(p, ctx) for p in pred["all"] or [])
    if "any" in pred:
        return any(check(p, ctx) for p in pred["any"] or [])
    if "not" in pred:
        return not check(pred["not"], ctx)
    field = resolve(pred.get("field"), ctx)
    value = resolve(pred.get("value"), ctx)
    values = resolve(pred.get("values"), ctx)
    op = pred.get("op")
    if op == "present":
        return field is not None
    if op == "absent":
        return field is None
    if op == "empty":
        return not field
    if op == "not_empty":
        return bool(field)
    if op == "truthy":
        return bool(field)
    if op == "falsy":
        return not field
    if field is None:
        return False
    if op == "eq":
        return field == value
    if op == "ne":
        return field != value
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _num(field), _num(value)
        if a is None or b is None:
            return False
        return {"gt": a > b, "gte": a >= b,
                "lt": a < b, "lte": a <= b}[op]
    if op == "in":
        return isinstance(value, (list, tuple, set)) and field in value
    if op == "not_in":
        return not (isinstance(value, (list, tuple, set))
                    and field in value)
    if op == "contains":
        return isinstance(field, (list, tuple, set, str)) \
            and value in field
    if op == "contains_any":
        vals = values if isinstance(values, list) else [values]
        return any(str(v).lower() in str(field).lower()
                   for v in vals if v is not None)
    if op == "matches":
        return str(value).lower() in str(field).lower()
    return False


def _brief(v):
    """Compact a resolved value for evidence rows (lists -> size+head)."""
    if isinstance(v, (list, tuple)):
        head = [x.get("id") if isinstance(x, dict) else x
                for x in v[:4]]
        return f"list[{len(v)}]{head if v else ''}"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    return v


def check_detail(pred, ctx):
    """(ok, clauses) — every leaf {field, op, value} predicate yields a
    clause row {field, op, resolved, result, reason}; combinators
    recurse. `reason` names why a clause failed (unresolved surface,
    comparison miss)."""
    clauses = []

    def walk(p):
        if not isinstance(p, dict):
            return bool(p)
        if "all" in p:
            return all(walk(x) for x in p["all"] or [])
        if "any" in p:
            return any(walk(x) for x in p["any"] or [])
        if "not" in p:
            return not walk(p["not"])
        field = resolve(p.get("field"), ctx)
        ok = check(p, ctx)
        reason = None
        if not ok:
            if field is None and p.get("op") not in \
                    ("absent", "empty", "falsy"):
                reason = "unresolved"
            else:
                reason = "mismatch"
        clauses.append({"field": p.get("field"), "op": p.get("op"),
                        "resolved": _brief(field), "result": bool(ok),
                        "reason": reason})
        return ok

    return walk(pred), clauses


# -- context ------------------------------------------------------------------

class Ctx:
    """Evaluation context for one poll: pack cfg, obs, game handle,
    per-run mutable state (cooldowns/trends/caches), vars, tick."""

    def __init__(self, cfg=None, obs=None, game=None, state=None,
                 vars=None, persist=None, tick=0, poll=None,
                 decisions=None):
        self.cfg = cfg or {}
        self.obs = obs or {}
        self.game = game
        self.state = state if state is not None else {}
        self.vars = vars if vars is not None else {}      # scratch
        self.persist = persist if persist is not None else {}
        self.tick = tick
        self.poll = poll if poll is not None else tick
        # transparency: callers pass a list to collect per-poll dispatch
        # rows {tick, poll, source, template, params, ok} (UR-VIEW-002)
        self.decisions = decisions
        # cooldowns key on the poll counter, not game ticks — game speed
        # changes tick deltas
        self.cache: dict = {}

    def rpc(self, method, params=None):
        if self.game is None:
            return {}
        r = self.game.rpc(method, params or {})
        return r.get("result") if r.get("ok") else {}


def _things(res) -> list:
    t = res.get("things") if isinstance(res, dict) else None
    if isinstance(t, list):
        return t
    return res if isinstance(res, list) else []


# -- capability functions ------------------------------------------------------
# Every fn is (ctx, *args). No def names or strategy constants here.

def _fn_add(ctx, *a):
    return sum(float(x or 0) for x in a)


def _fn_sub(ctx, a, *rest):
    out = float(a or 0)
    for x in rest:
        out -= float(x or 0)
    return out


def _fn_mul(ctx, *a):
    out = 1.0
    for x in a:
        out *= float(x or 0)
    return out


def _fn_fdiv(ctx, a, b):
    b = float(b or 1)
    return int(float(a or 0) // b) if b else 0


def _fn_mod(ctx, a, b):
    b = float(b or 0)
    return int(float(a or 0) % b) if b else 0


def _fn_min(ctx, *a):
    return min((float(x or 0) for x in a), default=0.0)


def _fn_max(ctx, *a):
    return max((float(x or 0) for x in a), default=0.0)


def _fn_cell(ctx, x, z):
    return [int(float(x or 0)), int(float(z or 0))]


def _fn_rect(ctx, x, z, w, h):
    return [int(float(v or 0)) for v in (x, z, w, h)]


def _fn_first(ctx, lst):
    return (lst or [None])[0] if isinstance(lst, (list, tuple)) else None


def _fn_nth(ctx, lst, i):
    try:
        return lst[int(i)]
    except (IndexError, TypeError, ValueError):
        return None


def _fn_count(ctx, lst):
    return len(lst) if isinstance(lst, (list, tuple, dict)) else 0


def _fn_ids(ctx, lst):
    return [t.get("id") for t in (lst or [])
            if isinstance(t, dict) and t.get("id")]


def _fn_anchor(ctx, name):
    """Anchor by name from obs['anchors'] — live returns a list of
    {name, rect:{min,max,w,h}}; sim may return a dict name->rect."""
    anchors = ctx.obs.get("anchors")
    if isinstance(anchors, dict):
        v = anchors.get(name)
        if isinstance(v, dict) and "min" in v:
            r = v.get("rect")
            return {"min": v["min"],
                    "rect": (list(r) if isinstance(r, (list, tuple))
                             and len(r) >= 4 else
                             [v["min"][0], v["min"][1],
                              v.get("w", 1), v.get("h", 1)])}
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return {"min": list(v[:2]),
                    "rect": list(v[:4]) + [1] * max(0, 4 - len(v))}
        return None
    for a in (anchors if isinstance(anchors, list) else []):
        if not isinstance(a, dict) or a.get("name") != name:
            continue
        r = a.get("rect") or {}
        mn = r.get("min") if isinstance(r, dict) else None
        if isinstance(mn, (list, tuple)) and len(mn) >= 2:
            return {"min": list(mn[:2]),
                    "rect": [mn[0], mn[1], r.get("w", 1), r.get("h", 1)]}
    return None


def _fn_find_kind(ctx, kind, radius=60):
    """First map.find thing id for a kind (tree/resource_rock/item/...)."""
    res = ctx.rpc("map.find", {"kind": kind, "radius": int(radius or 60)})
    for t in _things(res):
        if isinstance(t, dict) and t.get("id"):
            return t["id"]
    return None


def _fn_find_def(ctx, d):
    res = ctx.rpc("map.find", {"def": d})
    for t in _things(res):
        if isinstance(t, dict) and t.get("id"):
            return t["id"]
    return None


def _fn_find_defs(ctx, defs):
    """All thing rows matching any def in `defs` (map.find per def,
    merged). `find_def` returns the first id; this keeps rows so `pos`
    and per-thing iteration work."""
    out = []
    for d in (defs or []):
        out += [t for t in _things(ctx.rpc("map.find", {"def": d}))
                if isinstance(t, dict)]
    return out


def _fn_checker_cells(ctx, rect):
    """Alternating cells of `rect` ((x+z) even) — the staggered trap
    pattern that leaves a diagonal weave lane for colonists while
    raiders mass onto the trapped cells."""
    rc = _rect_cells(rect)
    if rc is None:
        return []
    x, z, w, h = rc
    return [[cx, cz] for cz in range(z, z + h)
            for cx in range(x, x + w) if (cx + cz) % 2 == 0]


def _fn_find_defs_in(ctx, defs, rect):
    """find_defs filtered to rows inside `rect` — room-scoped lookups so
    ruins/strays elsewhere can't satisfy a room's furniture contract."""
    return [t for t in _fn_find_defs(ctx, defs)
            if _in_rect(_fn_pos(ctx, t), rect)]


def _fn_blueprints_in(ctx, defs, rect):
    """blueprints() filtered to `rect` — pending-build rows scoped to a
    room so unrelated designations don't suppress or satisfy a goal."""
    if isinstance(defs, str):
        defs = [defs]
    defs = [str(d) for d in (defs or [])]
    bps = _things(ctx.obs.get("blueprints") or {})
    return sum(1 for t in bps
               if isinstance(t, dict) and _in_rect(_fn_pos(ctx, t), rect)
               and any(d in _bp_def(t) for d in defs))


def _fn_pos(ctx, thing):
    """Cell [x,z] of a thing row (or a raw cell passthrough)."""
    p = thing.get("pos") if isinstance(thing, dict) else thing
    return list(p[:2]) if isinstance(p, (list, tuple)) and len(p) >= 2 \
        else None


def _rect_cells(rect):
    try:
        return (int(float(v or 0)) for v in rect[:4])
    except (TypeError, ValueError):
        return None


def _fn_wind_path(ctx, cell, axis="x", half_width=2, depth=5, gap=0,
                  foot=1):
    """Two rects flanking the footprint along `axis` — the airflow
    corridor a wind turbine needs clear. `cell` is the placement anchor
    (OccupiedRect center). `foot` is the footprint's extent ALONG the
    corridor axis so corridors start at the footprint edge, not the
    anchor cell — e.g. WindTurbine is 7x2: axis z, span 7 (hw 3),
    depth 8, foot 2 gives the vanilla 7x18 exclusion zone."""
    pos = _fn_pos(ctx, cell)
    if pos is None:
        return None
    x, z = pos
    hw = int(half_width or 0)
    d = int(depth or 0)
    g = int(gap or 0)
    f = int(foot or 1)
    lo = f // 2           # cells the footprint extends toward -axis
    hi = f - lo           # toward +axis (occupies anchor..+hi-1)
    if str(axis) == "x":
        return [[x + hi + g, z - hw, d, 2 * hw + 1],
                [x - lo - g - d, z - hw, d, 2 * hw + 1]]
    return [[x - hw, z + hi + g, 2 * hw + 1, d],
            [x - hw, z - lo - g - d, 2 * hw + 1, d]]


def _footprint_rect(x, z, axis, hw, foot):
    """Occupied rect of a span(2hw+1) x foot footprint anchored at
    (x, z) — GenAdj.OccupiedRect center convention: even dims bias the
    anchor cell toward the +axis end."""
    f = int(foot or 1)
    lo = f // 2
    if str(axis) == "x":
        return [x - lo, z - hw, f, 2 * hw + 1]
    return [x - hw, z - lo, 2 * hw + 1, f]


def _in_rect(pos, rect):
    r = _rect_cells(rect)
    if r is None or pos is None:
        return False
    x, z, w, h = r
    return x <= int(pos[0]) < x + w and z <= int(pos[1]) < z + h


def _fn_obstructions(ctx, rects, kinds, radius=0):
    """Things inside `rects` (one rect or a list) whose map.find kind is
    in `kinds` — the pack decides what counts as blocking (tree,
    harvestable, building, resource_rock, blueprint, ...)."""
    if not isinstance(rects, (list, tuple)) or not rects:
        return []
    if isinstance(rects[0], (int, float)):
        rects = [rects]
    kinds = [str(k) for k in (kinds or [])]
    if not kinds:
        return []
    out, seen = [], set()
    for rect in rects:
        r = _rect_cells(rect)
        if r is None:
            continue
        x, z, w, h = r
        near = [x + w // 2, z + h // 2]
        rad = int(radius or 0) or int((w * w + h * h) ** 0.5) + 5
        for kind in kinds:
            res = ctx.rpc("map.find", {"kind": kind, "near": near,
                                       "radius": rad})
            for t in _things(res):
                if not isinstance(t, dict) or not t.get("id"):
                    continue
                if t["id"] in seen or not _in_rect(t.get("pos"), rect):
                    continue
                seen.add(t["id"])
                out.append(t)
    return out


def _fn_wind_obstructions(ctx, defs, axis="x", half_width=2, depth=5,
                          gap=0, foot=1, kinds=None):
    """Union of obstructions across the wind paths of every thing
    matching `defs` — regrowth/maintenance signal for built turbines."""
    rects, seen = [], set()
    for t in _fn_find_defs(ctx, defs):
        p = _fn_pos(ctx, t)
        if p is None:
            continue
        key = (p[0], p[1])
        if key in seen:
            continue
        seen.add(key)
        rects += _fn_wind_path(ctx, p, axis, half_width, depth, gap,
                               foot) or []
    return _fn_obstructions(ctx, rects, kinds)


def _turbine_scan(ctx, def_name, rect, axis, hw, depth, gap, foot,
                  kinds, stuff, want_blocked):
    """`free_cell`-style scan where each candidate must also satisfy the
    wind-path condition — `want_blocked` False picks a cell with a clear
    corridor, True picks a buildable cell whose corridor is obstructed
    (the site to clear before building). `foot` is the footprint's
    extent along the corridor axis — the full span x foot footprint must
    be obstruction- and zone-free, not just the anchor cell."""
    if not isinstance(rect, (list, tuple)) or len(rect) < 4:
        return None
    key = ("turbine_site", str(def_name), str(list(rect[:4])), str(axis),
           int(hw or 0), int(depth or 0), int(gap or 0), int(foot or 1),
           str(kinds), str(stuff), bool(want_blocked))
    if key in ctx.cache:
        return ctx.cache[key]
    x, z, w, h = _rect_cells(rect) or (0, 0, 0, 0)
    out = None
    for cz in range(z, z + h):
        for cx in range(x, x + w):
            if not _fn_buildable_at(ctx, def_name, [cx, cz], stuff):
                continue
            foot_r = _footprint_rect(cx, cz, axis, hw, foot)
            # the footprint itself can't sit on blockers or a zone —
            # the anchor cell being free is not enough for a multi-cell
            # building
            if _fn_obstructions(ctx, foot_r, kinds):
                continue
            if _path_zoned(ctx, [foot_r]):
                continue
            path = _fn_wind_path(ctx, [cx, cz], axis, hw, depth, gap,
                                 foot)
            # a corridor crossing an existing zone can never be cleared —
            # zones aren't cuttable, so such a site is unusable outright
            # (live: turbine corridor overlapped the rice field and the
            # agent started cutting its own crop)
            if path and _path_zoned(ctx, path):
                continue
            blocked = bool(_fn_obstructions(ctx, path, kinds))
            if blocked == want_blocked:
                out = [cx, cz]
                break
        if out:
            break
    ctx.cache[key] = out
    return out


def _path_zoned(ctx, path, stride=2, max_probes=15):
    """Any zoned cell inside the wind-path rects? Sampled probe (stride)
    bounded by max_probes per rect — zones are contiguous, so sampling
    catches an overlap without a full-cell scan."""
    for r in path or []:
        rc = _rect_cells(r)
        if rc is None:
            continue
        x, z, w, h = rc
        probes = 0
        for cz in range(z, z + h, max(1, int(stride or 2))):
            for cx in range(x, x + w, max(1, int(stride or 2))):
                if _in_zone(ctx, [cx, cz]):
                    return True
                probes += 1
                if probes >= int(max_probes or 15):
                    break
            if probes >= int(max_probes or 15):
                break
    return False


def _fn_turbine_site(ctx, def_name, rect, axis="x", half_width=2,
                     depth=5, gap=0, foot=1, kinds=None, stuff=None):
    """First cell in `rect` where `def_name` dry-run places AND the
    pack-declared wind path is free of `kinds` obstructions."""
    return _turbine_scan(ctx, def_name, rect, axis, half_width, depth,
                         gap, foot, kinds, stuff, want_blocked=False)


def _fn_turbine_site_blocked(ctx, def_name, rect, axis="x", half_width=2,
                             depth=5, gap=0, foot=1, kinds=None,
                             stuff=None):
    """First buildable cell in `rect` whose wind path IS obstructed —
    the site to run clearing designations on."""
    return _turbine_scan(ctx, def_name, rect, axis, half_width, depth,
                         gap, foot, kinds, stuff, want_blocked=True)


def _fn_terrain_at(ctx, cell):
    """Terrain def at a cell (accepts [x,z] or rect [x,z,w,h] — samples
    the min corner)."""
    p = _fn_pos(ctx, cell)
    if p is None:
        return None
    res = ctx.rpc("map.cell", {"cell": p})
    v = res.get("terrain") if isinstance(res, dict) else None
    return v.get("def") if isinstance(v, dict) else v


def _fn_zone_at(ctx, cell):
    """Zone label at a cell (accepts [x,z] or rect [x,z,w,h]); None when
    the cell is unzoned."""
    p = _fn_pos(ctx, cell)
    if p is None:
        return None
    res = ctx.rpc("map.cell", {"cell": p})
    if not isinstance(res, dict):
        return None
    z = res.get("zone")
    if isinstance(z, dict):
        return z.get("label") or z.get("name") or True
    return z or None


def _item_rows(ctx):
    items = ctx.obs.get("items") or {}
    return _things(items)


def _in_zone(ctx, pos):
    """Zone membership probe via map.cell (bounded by caller)."""
    res = ctx.rpc("map.cell", {"cell": pos})
    return isinstance(res, dict) and bool(res.get("zone"))


def _fn_loose_ids(ctx, probe_limit=24):
    """Item ids not inside any zone — 'needs hauling'. Bounded probe."""
    if "loose_ids" in ctx.cache:
        return ctx.cache["loose_ids"]
    out = []
    rows = [t for t in _item_rows(ctx)
            if isinstance(t, dict) and t.get("id")
            and not t.get("forbidden")]
    for t in rows[: int(probe_limit or 24)]:
        if ctx.game is not None and _in_zone(ctx, t.get("pos")):
            continue
        out.append(t["id"])
    if len(rows) > int(probe_limit or 24):
        out += [t["id"] for t in rows[int(probe_limit or 24):]]
    ctx.cache["loose_ids"] = out
    return out


def _fn_loose_id(ctx):
    ids = _fn_loose_ids(ctx)
    return ids[0] if ids else None


def _fn_loose_count(ctx):
    return len(_fn_loose_ids(ctx))


def _fn_stack_of(ctx, thing_id=None):
    """Stack count of a loose item — HaulToCell needs a real count or
    RimWorld logs 'Invalid count: -1' per job."""
    for t in _item_rows(ctx):
        if isinstance(t, dict) and t.get("id") == thing_id:
            c = t.get("count")
            return int(c) if isinstance(c, (int, float)) else 1
    return 1


def _fn_forbidden_ids(ctx):
    forb = ctx.obs.get("forbidden") or {}
    return _fn_ids(ctx, _things(forb))


def _bp_def(t):
    """Blueprint/frame target def across bridge field variants
    (def / build_def / entity_def / defName)."""
    for k in ("def", "build_def", "entity_def", "defName"):
        v = t.get(k)
        if v:
            return str(v)
    return ""


def _fn_blueprints(ctx, defs):
    """Pending blueprints whose def matches any def in `defs`."""
    if isinstance(defs, str):
        defs = [defs]
    defs = [str(d) for d in (defs or [])]
    bps = _things(ctx.obs.get("blueprints") or {})
    return sum(1 for t in bps
               if isinstance(t, dict)
               and any(d in _bp_def(t) for d in defs))


def _fn_blueprints_pending(ctx):
    """All pending blueprint/frame work — lets packs gate busywork rules
    behind construction demand (idle colonists shouldn't get harvest
    assignments while frames wait for builders)."""
    return sum(1 for t in _things(ctx.obs.get("blueprints") or {})
               if isinstance(t, dict))


def _fn_fertile(ctx, rect, step=3):
    """Most fertile rect among `rect` and its 3 neighbors (map.cell)."""
    if ctx.game is None or not isinstance(rect, (list, tuple)):
        return rect
    x, z, w, h = (int(v) for v in rect[:4])
    cands = [list(rect[:4]),
             [x, z - h - 1, w, h], [x + w + 1, z, w, h],
             [x, z + h + 1, w, h],
             # diagonals — when the axial neighbours are zoned or barren
             # the nearest arable soil is often a corner step away
             # (live: healroot base was all rough stone)
             [x - w - 1, z, w, h], [x - w - 1, z - h - 1, w, h],
             [x - w - 1, z + h + 1, w, h], [x + w + 1, z - h - 1, w, h],
             [x + w + 1, z + h + 1, w, h]]
    step = max(1, int(step or 3))
    best, best_f = list(rect[:4]), -1.0
    for r in cands:
        fsum = cells = zoned = 0
        for cx in range(r[0], r[0] + r[2], step):
            for cz in range(r[1], r[1] + r[3], step):
                res = ctx.rpc("map.cell", {"cell": [cx, cz]})
                if isinstance(res, dict) and res.get("zone"):
                    zoned += 1
                    continue
                f = (res or {}).get("fertility") \
                    if isinstance(res, dict) else None
                if isinstance(f, (int, float)):
                    fsum += f
                    cells += 1
        # a candidate that overlaps an existing zone can never be
        # designated — skip it regardless of fertility (live: healroot
        # kept failing by overlapping the rice zone)
        if zoned:
            continue
        if cells and fsum / cells > best_f:
            best, best_f = r, fsum / cells
    return best


def _fn_stuff(ctx, prefs):
    """First preferred material def that's actually available — counted
    stocks first, then loose items; falls back to prefs[0]."""
    prefs = prefs or []
    stocks = ctx.obs.get("stocks") or {}
    counted = stocks.get("counted") if isinstance(stocks, dict) else None
    if isinstance(counted, dict):
        for d in prefs:
            if (counted.get(d) or 0) > 0:
                return d
    loose = {str(t.get("def")) for t in _item_rows(ctx)}
    for d in prefs:
        if d in loose:
            return d
    return prefs[0] if prefs else None


def _fn_buildable_at(ctx, def_name, cell, stuff=None):
    """dry_run placement probe — reads buildability, designates nothing."""
    if ctx.game is None or not def_name or cell is None:
        return False
    res = ctx.rpc("ui.build", {"def": def_name, "at": list(cell),
                               "stuff": stuff, "dry_run": True})
    return isinstance(res, dict) and bool(res.get("placed"))


def _fn_free_cell(ctx, def_name, rect, inset=0, stuff=None):
    """First cell inside rect (inset applied) where `def_name` dry-run
    places cleanly — placement feasibility is probed, not assumed.
    Memoized per poll: `needs` + `at` resolve to one scan."""
    if not isinstance(rect, (list, tuple)) or len(rect) < 4:
        return None
    key = ("free_cell", str(def_name), str(list(rect[:4])),
           int(inset or 0), str(stuff))
    if key in ctx.cache:
        return ctx.cache[key]
    ins = int(inset or 0)
    x, z, w, h = (int(float(v or 0)) for v in rect[:4])
    out = None
    for cz in range(z + ins, z + h - ins):
        for cx in range(x + ins, x + w - ins):
            if _fn_buildable_at(ctx, def_name, [cx, cz], stuff):
                out = [cx, cz]
                break
        if out:
            break
    ctx.cache[key] = out
    return out


def _fn_home(ctx):
    res = ctx.rpc("state.threats")
    hc = res.get("home_center") if isinstance(res, dict) else None
    return hc if isinstance(hc, list) and len(hc) == 2 else [0, 0]


def _fn_near_home(ctx, off):
    home = _fn_home(ctx)
    off = off if isinstance(off, (list, tuple)) else [0, 0]
    dx = off[0] if len(off) > 0 else 0
    dz = off[1] if len(off) > 1 else 0
    return [int(home[0]) + int(dx), int(home[1]) + int(dz)]


def _fn_hostile_faction(ctx):
    res = ctx.rpc("state.factions")
    for f in (res if isinstance(res, list) else []):
        if isinstance(f, dict) and f.get("hostile") and not f.get("defeated"):
            return f.get("name") or ""
    return ""


def _colonist_rows(ctx):
    """Colonist dicts with at least {id, job?} — colonist_list may be
    bare ids; fall back to state.pawns faction==Player when thin."""
    if "colonist_rows" in ctx.cache:
        return ctx.cache["colonist_rows"]
    lst = (_dig(ctx.obs, "colonists.colonist_list")
           or ctx.obs.get("colonist_list") or [])
    rows = [c for c in lst if isinstance(c, dict)]
    if rows and "job" in rows[0]:
        ctx.cache["colonist_rows"] = rows
        return rows
    if ctx.game is None:
        ctx.cache["colonist_rows"] = rows
        return rows
    res = ctx.rpc("state.pawns")
    out = [p for p in (res if isinstance(res, list) else [])
           if isinstance(p, dict) and p.get("faction") == "Player"]
    ctx.cache["colonist_rows"] = out or rows
    return ctx.cache["colonist_rows"]


def _pawn_detail(ctx, pid):
    cache = ctx.state.setdefault("pawn_detail", {})
    if pid not in cache:
        res = ctx.rpc("state.pawn", {"pawn": pid})
        cache[pid] = res if isinstance(res, dict) else {}
    return cache[pid]


def _skill(ctx, pid, name):
    det = _pawn_detail(ctx, pid)
    sk = (det.get("skills") or {}) if isinstance(det, dict) else {}
    v = sk.get(name)
    try:
        return float(str(v).rstrip("!")) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fn_colonist_ids(ctx):
    return [c.get("id") for c in _colonist_rows(ctx) if c.get("id")]


def _fn_best(ctx, skill):
    """Colonist id with the highest `skill` value."""
    best, best_v = None, -1.0
    for c in _colonist_rows(ctx):
        pid = c.get("id")
        if not pid:
            continue
        v = _skill(ctx, pid, skill)
        if v > best_v:
            best, best_v = pid, v
    return best


def _fn_unarmed(ctx):
    """Colonist ids carrying no weapon."""
    out = []
    for c in _colonist_rows(ctx):
        pid = c.get("id")
        if not pid:
            continue
        w = c.get("weapon")
        if w is None:
            w = _pawn_detail(ctx, pid).get("weapon")
        if not w:
            out.append(pid)
    return out


def _find_loose_defs(ctx, defs):
    """Loose map things whose def is in `defs` (map.find per def)."""
    out = []
    for d in defs or []:
        res = ctx.rpc("map.find", {"def": d})
        for t in _things(res):
            if isinstance(t, dict) and t.get("id"):
                out.append(t)
    return out


def _fn_armor_ids(ctx, armor_defs):
    return [t["id"] for t in _find_loose_defs(ctx, armor_defs)]


def _fn_armed_count(ctx):
    rows = _colonist_rows(ctx)
    n = 0
    for c in rows:
        pid = c.get("id")
        if not pid:
            continue
        w = c.get("weapon")
        if w is None:
            w = _pawn_detail(ctx, pid).get("weapon")
        if w:
            n += 1
    return n


def _fn_weapons_avail(ctx, weapon_kinds):
    """Loose weapon ids matching pack weapon groups + armed count."""
    loose = 0
    for grp in weapon_kinds or []:
        loose += len(_find_loose_defs(ctx, grp.get("defs") or []))
    return loose + _fn_armed_count(ctx)


def _arm_match(ctx, weapon_kinds):
    """Joint (pawn, weapon) pick: first weapon group in preference order
    with a loose weapon gets the unarmed colonist best at that group's
    skill; leftovers go to the first unarmed colonist."""
    key = ("arm_match", str(weapon_kinds))
    if key in ctx.cache:
        return ctx.cache[key]
    unarmed = _fn_unarmed(ctx)
    match = None
    if unarmed:
        for grp in weapon_kinds or []:
            loose = _find_loose_defs(ctx, grp.get("defs") or [])
            if not loose:
                continue
            skill = grp.get("skill")
            pawn = max(unarmed,
                       key=lambda p: _skill(ctx, p, skill)) \
                if skill else unarmed[0]
            match = {"pawn": pawn, "weapon": loose[0]["id"]}
            break
        if match is None:
            for grp in weapon_kinds or []:
                loose = _find_loose_defs(ctx, grp.get("defs") or [])
                if loose:
                    match = {"pawn": unarmed[0],
                             "weapon": loose[0]["id"]}
                    break
    ctx.cache[key] = match
    return match


def _fn_arm_pawn(ctx, weapon_kinds):
    m = _arm_match(ctx, weapon_kinds)
    return (m or {}).get("pawn")


def _fn_arm_weapon(ctx, weapon_kinds):
    m = _arm_match(ctx, weapon_kinds)
    return (m or {}).get("weapon")


def _def_rank(d, defs):
    """Index of `d` in the pack's ordered defs (best-first); unlisted
    or absent gear ranks worst."""
    try:
        return list(defs or []).index(d)
    except ValueError:
        return len(defs or [])


def _pawn_equipped_def(ctx, pid):
    """Def name of the pawn's equipped weapon. The pawn-row `weapon`
    field is a label/id, not a def — only pawn detail's `equipment`
    rows carry one."""
    det = _pawn_detail(ctx, pid)
    eq = det.get("equipment") or []
    return eq[0].get("def") if eq and isinstance(eq[0], dict) else None


def _pawn_apparel_defs(ctx, pid):
    det = _pawn_detail(ctx, pid)
    return [a["def"] for a in (det.get("apparel") or [])
            if isinstance(a, dict) and a.get("def")]


def _upgrade_match(ctx, weapon_kinds):
    """Best (pawn, loose-weapon) upgrade pair: per weapon group (pack
    order = preference), the loose instance of the best-ranked def goes
    to the highest-skill colonist whose equipped weapon ranks worse.
    Equip auto-drops the old weapon, so upgrades cascade one pair per
    call — the repeat.while loop drains the cascade."""
    key = ("upgrade_match", str(weapon_kinds))
    if key in ctx.cache:
        return ctx.cache[key]
    match = None
    rows = [c for c in _colonist_rows(ctx) if c.get("id")]
    for grp in weapon_kinds or []:
        defs = grp.get("defs") or []
        avail = None
        for rank, d in enumerate(defs):
            loose = _find_loose_defs(ctx, [d])
            if loose:
                avail = (rank, loose[0].get("id"))
                break
        if avail is None:
            continue
        skill = grp.get("skill") or ""
        cands = sorted(rows,
                       key=lambda c: -_skill(ctx, c["id"], skill))
        for c in cands:
            if _is_downed(ctx, c):
                continue
            if _def_rank(_pawn_equipped_def(ctx, c["id"]),
                         defs) > avail[0]:
                match = {"pawn": c["id"], "weapon": avail[1]}
                break
        if match:
            break
    ctx.cache[key] = match
    return match


def _armor_match(ctx, armored_skill, armor_defs):
    """Best loose armor (defs best-first) goes to the highest-skilled
    `armored_skill` colonist whose worn armor ranks worse — melee
    specialists get the best protection first."""
    key = ("armor_match", armored_skill, str(armor_defs))
    if key in ctx.cache:
        return ctx.cache[key]
    match = None
    avail = None
    for rank, d in enumerate(armor_defs or []):
        loose = _find_loose_defs(ctx, [d])
        if loose:
            avail = (rank, loose[0].get("id"))
            break
    if avail is not None:
        rows = [c for c in _colonist_rows(ctx) if c.get("id")]
        cands = sorted(
            rows,
            key=lambda c: -_skill(ctx, c["id"], armored_skill or ""))
        for c in cands:
            if _is_downed(ctx, c):
                continue
            cur = min((_def_rank(d, armor_defs)
                       for d in _pawn_apparel_defs(ctx, c["id"])),
                      default=len(armor_defs or []))
            if cur > avail[0]:
                match = {"pawn": c["id"], "apparel": avail[1]}
                break
    ctx.cache[key] = match
    return match


def _fn_upgrade_pawn(ctx, weapon_kinds):
    return (_upgrade_match(ctx, weapon_kinds) or {}).get("pawn")


def _fn_upgrade_weapon(ctx, weapon_kinds):
    return (_upgrade_match(ctx, weapon_kinds) or {}).get("weapon")


def _fn_upgrade_armor_pawn(ctx, armored_skill, armor_defs):
    return (_armor_match(ctx, armored_skill, armor_defs) or {}) \
        .get("pawn")


def _fn_upgrade_armor(ctx, armored_skill, armor_defs):
    return (_armor_match(ctx, armored_skill, armor_defs) or {}) \
        .get("apparel")


def _fn_equip_pending(ctx, weapon_kinds, armored_skill, armor_defs):
    """Seasonal review work remains: a better loose weapon for some
    colonist, or better loose armor for a worse-armored one."""
    return bool(_upgrade_match(ctx, weapon_kinds)
                or _armor_match(ctx, armored_skill, armor_defs))


def _fn_arm_pending(ctx, weapon_kinds, armor_defs):
    """Arming work remains: an unarmed colonist with a weapon available,
    or loose armor left to wear."""
    if _fn_unarmed(ctx) and _arm_match(ctx, weapon_kinds):
        return True
    return bool(_fn_armor_ids(ctx, armor_defs))


def _fn_armed_ids(ctx):
    """Colonist ids carrying a weapon and able to fight (not downed)."""
    out = []
    for c in _colonist_rows(ctx):
        pid = c.get("id")
        if not pid or _is_downed(ctx, c):
            continue
        w = c.get("weapon")
        if w is None and ctx.game is not None:
            w = _pawn_detail(ctx, pid).get("weapon")
        if w:
            out.append(pid)
    return out


def _fn_drafted_ids(ctx):
    """Colonist ids currently drafted (row flag or pawn detail)."""
    out = []
    for c in _colonist_rows(ctx):
        pid = c.get("id")
        if not pid:
            continue
        d = c.get("drafted")
        if d is None and ctx.game is not None:
            d = _pawn_detail(ctx, pid).get("drafted")
        if d:
            out.append(pid)
    return out


def _fn_nearest_hostile(ctx, cell):
    """Living hostile id nearest `cell` — falls back to dist_home when
    the caller has no position."""
    p = _fn_pos(ctx, cell)
    best, best_d = None, None
    for h in _fn_living_hostiles(ctx):
        if not h.get("id"):
            continue
        hp = _fn_pos(ctx, h)
        if p is not None and hp is not None:
            d = (hp[0] - p[0]) ** 2 + (hp[1] - p[1]) ** 2
        else:
            d = h.get("dist_home")
            if not isinstance(d, (int, float)):
                continue
        if best_d is None or d < best_d:
            best, best_d = h.get("id"), d
    return best


def _hostile_rows(ctx):
    res = ctx.rpc("state.threats")
    hostiles = res.get("hostiles") or res.get("enemies") or [] \
        if isinstance(res, dict) else []
    if isinstance(hostiles, dict):
        hostiles = hostiles.get("things") or hostiles.get("pawns") or []
    out = []
    for h in (hostiles if isinstance(hostiles, list) else []):
        if isinstance(h, dict) and (
                h.get("dead") or (h.get("health") is not None
                                  and float(h.get("health") or 0) <= 0)):
            continue
        out.append(h)
    return out


def _is_downed(ctx, h):
    if not isinstance(h, dict):
        return False
    if h.get("downed") or h.get("incapacitated"):
        return True
    if ctx.game is None or not h.get("id"):
        return False
    det = _pawn_detail(ctx, h["id"])
    if det.get("downed") or det.get("needs_tending"):
        return True
    caps = det.get("capacities") or {}
    con = caps.get("Consciousness") if isinstance(caps, dict) else None
    try:
        return float(str(con).rstrip("%")) <= 30.0 if con else False
    except (TypeError, ValueError):
        return False


def _fn_living_hostiles(ctx):
    return [h for h in _hostile_rows(ctx) if not _is_downed(ctx, h)]


def _fn_downed_ids(ctx):
    return [h.get("id") for h in _hostile_rows(ctx)
            if isinstance(h, dict) and h.get("id") and _is_downed(ctx, h)]


def _fn_dialogs(ctx):
    """Open modal windows from state.dialogs (i/type/kind/choices)."""
    res = ctx.rpc("state.dialogs")
    return res if isinstance(res, list) else []


def _fn_fleeing_ids(ctx, window=3, rise=5):
    """Hostiles whose dist_home is rising over recent polls (routed)."""
    trend = ctx.state.setdefault("dist_trend", {})
    out = []
    for h in _hostile_rows(ctx):
        if not isinstance(h, dict) or not h.get("id"):
            continue
        d = h.get("dist_home")
        if not isinstance(d, (int, float)):
            continue
        hist = trend.setdefault(h["id"], [])
        hist.append(d)
        del hist[:-int(window or 3)]
        if len(hist) >= int(window or 3) and hist[-1] > hist[0] + float(rise or 5):
            out.append(h["id"])
    return out


# -- combat capability (feature 019; contracts/combat-capability.md v0) --------
# Generic capability primitives only — radii/duties/floors/weights are
# `combat:` pack cfg; tactics live in pack rules + pawn_scope options.

_COMBAT_CFG_KEYS = ("rally_anchor", "engage_radius", "overrun_radius",
                    "near_hostile", "release_ticks", "prolonged_ticks",
                    "min_health", "relief", "allow_unarmed",
                    "engage_odds_floor", "power_overrides",
                    "option_weights", "chase_skill", "assault_duties",
                    "watch_lords", "manhunter_mental", "delegate_order")

_ASSAULT_DEFAULT = ("AssaultColony", "PrisonerAssaultColony",
                    "Breaching", "Sapper", "Escort", "Kidnap", "Steal",
                    "HuntEnemiesIndividual", "AssaultThing",
                    "NestAssault")

_POWER_DEFAULT = {"Drifter": 35, "TribalArcher": 45, "TribalWarrior": 50,
                  "PirateGunner": 65, "Scyther": 150, "Centipede": 400}


def _combat_cfg(ctx) -> dict:
    """The pack's `combat:` cfg block — {} when absent or when the key
    carries the dev-harness script (feature-010 shape: spawn/rounds/…)."""
    blk = ctx.cfg.get("combat") if isinstance(ctx.cfg, dict) else None
    if not isinstance(blk, dict):
        return {}
    return blk if any(k in blk for k in _COMBAT_CFG_KEYS) else {}


def _dist(a, b):
    if not (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple))
            and len(a) >= 2 and len(b) >= 2):
        return None
    try:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    except (TypeError, ValueError):
        return None


def _home_areas(ctx):
    """Home-area rects [(x0,z0,x1,z1)] from state.areas — tolerant of
    cells/rect(s)/min-max row shapes; [] when the surface is missing."""
    if "home_areas" in ctx.cache:
        return ctx.cache["home_areas"]
    res = ctx.rpc("state.areas")
    rows = res.get("areas") if isinstance(res, dict) else res
    if not isinstance(rows, list) and isinstance(res, dict):
        rows = res.get("things")
    rects = []
    for a in (rows or []):
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or a.get("label") or a.get("id") or "")
        if "home" not in name.lower():
            continue
        cells = a.get("cells")
        if isinstance(cells, list) and cells:
            xs = [c[0] for c in cells
                  if isinstance(c, (list, tuple)) and len(c) >= 2]
            zs = [c[1] for c in cells
                  if isinstance(c, (list, tuple)) and len(c) >= 2]
            if xs and zs:
                rects.append((min(xs), min(zs), max(xs), max(zs)))
        for r in (a.get("rects")
                  or ([a["rect"]] if a.get("rect") else [])):
            if isinstance(r, (list, tuple)) and len(r) >= 4:
                rects.append((r[0], r[1],
                              r[0] + r[2] - 1, r[1] + r[3] - 1))
        mn, mx = a.get("min"), a.get("max")
        if isinstance(mn, (list, tuple)) and len(mn) >= 2 \
                and isinstance(mx, (list, tuple)) and len(mx) >= 2:
            rects.append((mn[0], mn[1], mx[0], mx[1]))
    ctx.cache["home_areas"] = rects
    return rects


def _in_home(ctx, pos):
    """pos inside a Home rect — None when no Home surface exists
    (callers treat unknown as not-home, radius checks still apply)."""
    rects = _home_areas(ctx)
    if not rects:
        return None
    p = pos if isinstance(pos, (list, tuple)) else _fn_pos(ctx, pos)
    if not (isinstance(p, (list, tuple)) and len(p) >= 2):
        return None
    return any(x0 <= p[0] <= x1 and z0 <= p[1] <= z1
               for x0, z0, x1, z1 in rects)


def _rally_rect(ctx):
    """Rally rect [x,z,w,h]: steward.status rally, else cfg rally_anchor,
    else 13x13 around home center (Order_Combat fallback)."""
    st = ctx.rpc("steward.status")
    r = st.get("rally") if isinstance(st, dict) else None
    if isinstance(r, (list, tuple)) and len(r) >= 4:
        return list(r[:4])
    anchor = _combat_cfg(ctx).get("rally_anchor")
    if anchor:
        a = _fn_anchor(ctx, anchor)
        if isinstance(a, dict):
            if isinstance(a.get("rect"), (list, tuple)) \
                    and len(a["rect"]) >= 4:
                return list(a["rect"][:4])
            if isinstance(a.get("min"), (list, tuple)):
                return [a["min"][0], a["min"][1], 1, 1]
    hc = _fn_home(ctx)
    return [int(hc[0]) - 6, int(hc[1]) - 6, 13, 13]


def _rally_center(ctx):
    r = _rally_rect(ctx)
    return [r[0] + r[2] // 2, r[1] + r[3] // 2]


def _is_friendly(ctx, h):
    """Never-engage rows: player/home factions, colony pawns, colony
    animals — berserk/rebellion/breakout rows stay friendly-owned."""
    fac = str(h.get("faction") or "").lower()
    return fac in ("player", "colony", "colonist", "home") \
        or h.get("colonist") is True


def _is_structure(ctx, h):
    k = str(h.get("kind") or h.get("def") or "").lower()
    return bool(h.get("structure")) or "turret" in k \
        or "building" in k or "mortar" in k


def _colonist_outside_home(ctx):
    """Any living colonist standing outside Home — False also when the
    Home surface is missing (manhunter rule stays conservative)."""
    for c in _colonist_rows(ctx):
        if not isinstance(c, dict) or c.get("downed") or c.get("dead"):
            continue
        if _in_home(ctx, _fn_pos(ctx, c)) is False:
            return True
    return False


def _engage_kind(ctx, h):
    """'engage' | 'watch' for one living hostile row — Order_Combat's
    ThreatRules.Engage as pack cfg (research §6)."""
    cfg = _combat_cfg(ctx)
    if h.get("fogged"):
        return "watch"
    pos = _fn_pos(ctx, h)
    if _in_home(ctx, pos) is True:
        return "engage"
    lord = str(h.get("lord") or "")
    if lord and lord in (cfg.get("watch_lords") or ["LordJob_Siege"]):
        return "watch"                       # siege/staging lords
    mental = str(h.get("mental") or "")
    if mental and mental == str(cfg.get("manhunter_mental")
                                or "Manhunter"):
        return "engage" if _colonist_outside_home(ctx) else "watch"
    rc = _rally_center(ctx)
    er = float(cfg.get("engage_radius") or 40)
    d = _dist(pos, rc)
    if d is None:
        dh = h.get("dist_home")
        d = float(dh) if isinstance(dh, (int, float)) else None
    if _is_structure(ctx, h):
        return "engage" if (d is not None and d <= er) else "watch"
    if lord and lord in (cfg.get("assault_duties")
                         or list(_ASSAULT_DEFAULT)):
        return "engage"
    if d is not None and d <= er:
        return "engage"
    return "watch"


def _fn_engaged_hostiles(ctx):
    """Living hostile rows the colony should fight now."""
    return [h for h in _fn_living_hostiles(ctx)
            if not _is_friendly(ctx, h)
            and _engage_kind(ctx, h) == "engage"]


def _fn_watching_hostiles(ctx):
    """Living hostile rows to watch but not engage (siege/staging/far/
    sheltered-manhunter)."""
    return [h for h in _fn_living_hostiles(ctx)
            if not _is_friendly(ctx, h)
            and _engage_kind(ctx, h) == "watch"]


def _pawn_health(ctx, pid, row=None):
    h = (row or {}).get("health") if isinstance(row, dict) else None
    if h is None and ctx.game is not None:
        det = _pawn_detail(ctx, pid)
        h = det.get("health") or det.get("health_summary")
    v = _num(h)
    return None if v is None else (v * 100.0 if v <= 1.5 else v)


def _pawn_need(ctx, pid, need):
    det = _pawn_detail(ctx, pid) if ctx.game is not None else {}
    nd = det.get("needs") or {}
    v = _num(nd.get(need) if isinstance(nd, dict) else None)
    if v is None:
        return None
    return v * 100.0 if v <= 1.5 else v


def _order_explain(ctx, oid):
    """steward.orders.explain row for `oid` — {} on any gap (memoized)."""
    key = ("order_explain", oid)
    if key not in ctx.cache:
        res = ctx.rpc("steward.orders.explain", {"id": oid})
        ctx.cache[key] = res if isinstance(res, dict) else {}
    return ctx.cache[key]


def _pawn_touched(ctx, pid):
    """Manual-touch interlock (FR-1907): pawn under another writer's
    active touch. No steward component -> False (no other writer
    exists); steward present but touch surface unreadable -> True
    (excluded — conservative)."""
    if "touch_surface" not in ctx.cache:
        st = ctx.rpc("steward.status")
        if not isinstance(st, dict) or not st:
            ctx.cache["touch_surface"] = "absent"
        else:
            ctx.cache["touch_surface"] = _order_explain(
                ctx, str(_combat_cfg(ctx).get("delegate_order")
                         or "combat"))
    surf = ctx.cache["touch_surface"]
    if surf == "absent":
        return False
    if not surf:
        return True
    for r in (surf.get("hands_off") or []):
        if isinstance(r, dict) and str(r.get("thing")) == str(pid):
            return True
    return False


def _draftable(ctx, c):
    """One colonist row -> bool (data-model FighterEligibility)."""
    if not isinstance(c, dict) or not c.get("id"):
        return False
    pid = c["id"]
    if c.get("dead") or c.get("downed") or c.get("prisoner") \
            or c.get("slave") or _is_downed(ctx, c):
        return False
    det = _pawn_detail(ctx, pid) if ctx.game is not None else {}
    if det.get("dead") or det.get("downed") or det.get("prisoner") \
            or det.get("slave"):
        return False
    stage = str(c.get("life_stage") or det.get("life_stage")
                or det.get("age_stage") or "").lower()
    if c.get("juvenile") or det.get("juvenile") or "child" in stage \
            or "baby" in stage:
        return False
    vio = c.get("violence_capable", det.get("violence_capable"))
    dis = det.get("disabled_work") or det.get("incapable") \
        or det.get("work_disabled") or []
    if vio is False or any("viol" in str(d).lower() for d in
                           (dis if isinstance(dis, list) else [dis])):
        return False
    if c.get("has_drafter", det.get("has_drafter", True)) is False:
        return False
    cfg = _combat_cfg(ctx)
    h = _pawn_health(ctx, pid, c)
    if h is not None and h < float(cfg.get("min_health") or 30):
        return False
    if not cfg.get("allow_unarmed"):
        w = c.get("weapon")
        if w is None and ctx.game is not None:
            w = det.get("weapon")
        if not w:
            return False
    if _pawn_touched(ctx, pid):
        return False
    return True


def _fn_draftable(ctx, pawns=None):
    """`draftable(id|list)` — bool for one id, filtered ids for a list,
    all eligible colonist ids when no arg."""
    rows = _colonist_rows(ctx)
    if pawns is None:
        return [c["id"] for c in rows if _draftable(ctx, c)]
    if isinstance(pawns, (list, tuple)):
        ids = {str(p) for p in pawns}
        return [c["id"] for c in rows
                if str(c.get("id")) in ids and _draftable(ctx, c)]
    row = next((c for c in rows if c.get("id") == pawns), {"id": pawns})
    return bool(_draftable(ctx, row))


def _fn_fighters(ctx):
    return _fn_draftable(ctx)


def _fn_order_state(ctx, order=None):
    """Steward standing-order state {enabled, engaged, overrun, last,
    hands_off}. obs['orders'] (observe projection) wins; else rpc.
    Fields None when the surface can't say — gates on them eval false."""
    oid = str(order if order is not None else
              (_combat_cfg(ctx).get("delegate_order") or "combat"))
    key = ("order_state", oid)
    if key in ctx.cache:
        return ctx.cache[key]
    row, ex = None, {}
    oobs = (ctx.obs.get("orders") or {}) if isinstance(ctx.obs, dict) \
        else {}
    if isinstance(oobs.get(oid), dict):
        row = oobs[oid]
        ex = row.get("explain") if isinstance(row.get("explain"), dict) \
            else {}
    else:
        st = ctx.rpc("steward.status")
        if isinstance(st, dict):
            row = next((o for o in (st.get("orders") or [])
                        if isinstance(o, dict)
                        and str(o.get("id")) == oid), None)
        ex = _order_explain(ctx, oid)
    text = " ".join(str(v) for v in (
        (row or {}).get("summary"), (row or {}).get("acting_on"),
        ex.get("summary"), ex.get("last")) if v).lower()
    state = {"enabled": None, "engaged": None, "overrun": None,
             "last": None, "hands_off": []}
    if row is not None or ex:
        en = (row or {}).get("enabled", ex.get("enabled"))
        state["enabled"] = bool(en) if en is not None else None
        state["engaged"] = ("engag" in text or "draft" in text
                            or bool((row or {}).get("acting_on")))
        state["overrun"] = "overrun" in text
        state["last"] = (row or {}).get("last") or ex.get("last")
        state["hands_off"] = list(ex.get("hands_off") or [])
    ctx.cache[key] = state
    return state


def _fn_combat_mode(ctx):
    """watch | engage | hold | overrun — colony posture per poll
    (data-model CombatMode). engage = engaged hostiles, fighters not
    yet all drafted; hold = deployed; overrun = breach."""
    engaged = _fn_engaged_hostiles(ctx)
    if not engaged:
        return "watch"
    rc = _rally_center(ctx)
    over_r = float(_combat_cfg(ctx).get("overrun_radius") or 5)
    for h in engaged:
        if _in_home(ctx, _fn_pos(ctx, h)) is True:
            return "overrun"
        d = _dist(_fn_pos(ctx, h), rc)
        if d is None:
            dh = h.get("dist_home")
            d = float(dh) if isinstance(dh, (int, float)) else None
        if d is not None and d <= over_r:
            return "overrun"
    fighters = set(_fn_draftable(ctx))
    drafted = set(_fn_drafted_ids(ctx))
    return "hold" if fighters and fighters <= drafted else "engage"


def _fn_ticks_since_hostile(ctx):
    """Game ticks since a living hostile was last observed — 10**9 when
    none has ever been seen (release window already satisfied)."""
    if _fn_living_hostiles(ctx):
        ctx.state["last_hostile_tick"] = ctx.tick
    last = ctx.state.get("last_hostile_tick")
    return ctx.tick - last if last is not None else 10 ** 9


def _fn_hostiles_in_home(ctx):
    return [h for h in _fn_living_hostiles(ctx)
            if not _is_friendly(ctx, h)
            and _in_home(ctx, _fn_pos(ctx, h)) is True]


def _fn_hostiles_within(ctx, cell, r=10):
    p = cell if isinstance(cell, (list, tuple)) else _fn_pos(ctx, cell)
    return [h for h in _fn_living_hostiles(ctx)
            if (_dist(_fn_pos(ctx, h), p) or 10 ** 9) <= float(r or 10)]


def _fn_nearest_fleeing(ctx, pawn):
    fled = set(_fn_fleeing_ids(ctx))
    p = _fn_pos(ctx, pawn)
    best, best_d = None, None
    for h in _hostile_rows(ctx):
        if h.get("id") not in fled:
            continue
        d = _dist(_fn_pos(ctx, h), p)
        if d is not None and (best_d is None or d < best_d):
            best, best_d = h["id"], d
    return best


def _fn_safe_cell(ctx, pawn):
    """Retreat destination: the Home cell maximizing distance to the
    nearest living hostile — None when every candidate is inside
    `near_hostile` of a hostile (FR-1910 suppression)."""
    cfg = _combat_cfg(ctx)
    near = float(cfg.get("near_hostile") or 30)
    hc = _fn_home(ctx)
    cands = [[hc[0] + dx, hc[1] + dz]
             for dx in (-6, 0, 6) for dz in (-6, 0, 6)]
    living = _fn_living_hostiles(ctx)
    best, best_d = None, -1.0
    for cell in cands:
        d = min((_dist(_fn_pos(ctx, h), cell) or 10 ** 9)
                for h in living) if living else 10 ** 9
        if d > best_d:
            best, best_d = cell, d
    return best if best_d > near or not living else None


def _fn_skill_of(ctx, pid, skill):
    return _skill(ctx, pid, skill)


def _fn_health_of(ctx, pid):
    return _pawn_health(ctx, pid)


def _fn_need_of(ctx, pid, need):
    return _pawn_need(ctx, pid, need)


def _fn_weapon_stats(ctx, thing):
    """Weapon stats {class, range, dps, warmup, cooldown, burst} via
    defs.get — None on any miss (gates evaluate false, conservative)."""
    d = thing.get("def") or thing.get("weapon") \
        if isinstance(thing, dict) else thing
    if not d:
        return None
    d = str(d)
    key = ("weapon_stats", d)
    if key in ctx.cache:
        return ctx.cache[key]
    res = ctx.rpc("defs.get", {"def": d})
    stats = {}
    if isinstance(res, dict):
        st = res.get("stats") if isinstance(res.get("stats"), dict) \
            else res
        verbs = (st.get("verbs") or res.get("verbs") or [])
        v0 = verbs[0] if isinstance(verbs, list) and verbs \
            and isinstance(verbs[0], dict) else {}
        melee = st.get("is_melee", v0.get("is_melee"))
        if melee is None:
            melee = "melee" in d.lower() or "meleeweapon" in d.lower()
        stats = {
            "class": "melee" if melee else "ranged",
            "range": _num(st.get("range", v0.get("range"))),
            "dps": _num(st.get("dps") or st.get("dps_ranged")
                        or st.get("melee_dps")),
            "warmup": _num(v0.get("warmup", st.get("warmup"))),
            "cooldown": _num(v0.get("cooldown", st.get("cooldown"))),
            "burst": _num(v0.get("burst", st.get("burst")))}
        if stats["range"] is None and not melee:
            stats = None
    ctx.cache[key] = stats or None
    return ctx.cache[key]


def _pawn_weapon(ctx, pid, row=None):
    w = (row or {}).get("weapon") if isinstance(row, dict) else None
    if w is None and ctx.game is not None:
        w = _pawn_detail(ctx, pid).get("weapon")
    return w


def _weapon_of(ctx, p):
    """Pawn id/row -> weapon stats (None = unarmed or unknown)."""
    row = p if isinstance(p, dict) else \
        next((c for c in _colonist_rows(ctx) if c.get("id") == p), {})
    pid = row.get("id", p) if isinstance(row, dict) else p
    if not _is_friendly(ctx, row) and isinstance(row, dict) \
            and row in _hostile_rows(ctx):
        w = row.get("weapon")
    else:
        w = _pawn_weapon(ctx, pid, row)
    return _fn_weapon_stats(ctx, w)


def _fn_speed_of(ctx, pid):
    det = _pawn_detail(ctx, pid) if ctx.game is not None else {}
    caps = det.get("capacities") or {}
    v = _num(caps.get("Moving") if isinstance(caps, dict) else None)
    if v is None:
        v = _num(det.get("speed"))
    if v is None:
        return None
    return v * 4.6 if v <= 3.0 else v        # Moving capacity -> cells/s


def _fn_outranges(ctx, p, h):
    pw, hw = _weapon_of(ctx, p), _weapon_of(ctx, h)
    if not pw or not hw or pw.get("range") is None \
            or hw.get("range") is None:
        return False
    return pw["range"] > hw["range"]


def _fn_outranged_by(ctx, p):
    return any(_fn_outranges(ctx, h, p)
               for h in _fn_engaged_hostiles(ctx))


def _fn_outrun_by(ctx, p):
    ps = _fn_speed_of(ctx, p if not isinstance(p, dict)
                      else p.get("id"))
    if ps is None:
        return False
    return any(((_fn_speed_of(ctx, h.get("id")) or 0) > ps)
               for h in _fn_engaged_hostiles(ctx) if h.get("id"))


def _fn_in_range(ctx, p, h):
    pw = _weapon_of(ctx, p)
    if not pw or pw.get("range") is None:
        return False
    d = _dist(_fn_pos(ctx, p), _fn_pos(ctx, h))
    return d is not None and d <= pw["range"]


def _fn_enemy_mix(ctx):
    """{melee, ranged, structure, total} over living hostiles (weapon
    def -> class; unarmed/melee-capable rows count as melee)."""
    out = {"melee": 0, "ranged": 0, "structure": 0, "total": 0}
    for h in _fn_living_hostiles(ctx):
        if _is_friendly(ctx, h):
            continue
        out["total"] += 1
        if _is_structure(ctx, h):
            out["structure"] += 1
            continue
        ws = _weapon_of(ctx, h)
        if ws is None or ws.get("class") == "melee":
            out["melee"] += 1
        else:
            out["ranged"] += 1
    return out


def _fn_enemy_max_range(ctx):
    best = 0.0
    for h in _fn_living_hostiles(ctx):
        r = (_weapon_of(ctx, h) or {}).get("range")
        if isinstance(r, (int, float)) and r > best:
            best = r
    return best


def _fn_threat_power(ctx):
    """Sum of combat-power points over living hostiles (wiki defaults;
    pack `combat.power_overrides` per def/kind)."""
    over = _combat_cfg(ctx).get("power_overrides") or {}
    total = 0.0
    for h in _fn_living_hostiles(ctx):
        if _is_friendly(ctx, h):
            continue
        k = str(h.get("kind") or h.get("def") or "")
        total += float(over.get(k) or _POWER_DEFAULT.get(k) or 50)
    return total


def _fn_manhunters(ctx):
    mh = str(_combat_cfg(ctx).get("manhunter_mental") or "Manhunter")
    return [h for h in _fn_living_hostiles(ctx)
            if str(h.get("mental") or "") == mh]


def _fn_free_beds(ctx, kind="any"):
    """Unoccupied beds in rooms of `kind` (any|medical|prison)."""
    rooms = ctx.obs.get("rooms") if isinstance(ctx.obs, dict) else None
    rows = rooms.get("rooms") if isinstance(rooms, dict) else rooms
    want = {"medical": ("hospital", "medical"),
            "prison": ("prison",)}.get(str(kind), None)
    total = 0
    for r in (rows if isinstance(rows, list) else []):
        if not isinstance(r, dict):
            continue
        role = str(r.get("role") or "").lower()
        if want and not any(w in role for w in want):
            continue
        beds = _num(r.get("beds"))
        occ = _num(r.get("occupied")) or _num(r.get("owners")) or 0
        if beds is not None:
            total += max(0, int(beds - occ))
    return total


def _fn_casualty_ids(ctx):
    """Downed colonist ids."""
    return [c["id"] for c in _colonist_rows(ctx)
            if isinstance(c, dict) and c.get("id")
            and (c.get("downed") or _is_downed(ctx, c))]


def _fn_pawns_needing_tend(ctx):
    """Colonist ids downed or flagged needs_tending."""
    out = []
    for c in _colonist_rows(ctx):
        pid = c.get("id") if isinstance(c, dict) else None
        if not pid:
            continue
        det = _pawn_detail(ctx, pid) if ctx.game is not None else {}
        if c.get("downed") or det.get("downed") \
                or det.get("needs_tending") or _is_downed(ctx, c):
            out.append(pid)
    return out


def _fn_kite_cell(ctx, pawn):
    """Step away from the nearest engaged hostile along the pawn-hostile
    vector, biased home — None when the pawn lacks range+speed edge
    (FR-1910: kite suppressed when outranged or outrun)."""
    p = _fn_pos(ctx, pawn)
    nh = _fn_nearest_hostile(ctx, p)
    if p is None or nh is None:
        return None
    h = next((x for x in _fn_living_hostiles(ctx)
              if x.get("id") == nh), None)
    hp = _fn_pos(ctx, h) if h else None
    if hp is None:
        return None
    ws = _weapon_of(ctx, pawn)
    rng = (ws or {}).get("range") or 0
    dx, dz = p[0] - hp[0], p[1] - hp[1]
    d = (dx * dx + dz * dz) ** 0.5 or 1.0
    step = max(1.0, (rng - d)) if rng > d else 4.0
    return [round(p[0] + dx / d * step), round(p[1] + dz / d * step)]


def _fn_block_cell(ctx, pawn):
    """Cell between the nearest melee hostile and home center —
    choke approximation for melee-block."""
    p = _fn_pos(ctx, pawn)
    hc = _fn_home(ctx)
    nh = _fn_nearest_hostile(ctx, p or hc)
    h = next((x for x in _fn_living_hostiles(ctx)
              if x.get("id") == nh), None) if nh else None
    hp = _fn_pos(ctx, h) if h else None
    if hp is None:
        return None
    return [round((hp[0] + hc[0]) / 2), round((hp[1] + hc[1]) / 2)]


def _combat_evidence(ctx, rid, source):
    """Append a combat-evidence decision row + lifecycle markers.

    combat_engaged/combat_released come from the steward ledger via
    ``order_state().last``; ``combat.overrun``/``combat.prolonged`` are
    pack-side decision-row markers, emitted once per engagement."""
    mode = _fn_combat_mode(ctx)
    engaged = _fn_engaged_hostiles(ctx)
    order = _fn_order_state(ctx)
    cfg = _combat_cfg(ctx)
    markers = ctx.state.setdefault("combat_markers", {})
    if engaged and "start" not in markers:
        markers["start"] = ctx.tick
    if not engaged and "start" in markers:
        del markers["start"]
        markers.pop("overrun", None)
        markers.pop("prolonged", None)
    marks = []
    if mode == "overrun" and "overrun" not in markers:
        markers["overrun"] = ctx.tick
        marks.append({"marker": "combat.overrun"})
    pt = cfg.get("prolonged_ticks")
    if engaged and pt and "start" in markers and "prolonged" \
            not in markers and ctx.tick - markers["start"] >= int(pt):
        markers["prolonged"] = ctx.tick
        marks.append({"marker": "combat.prolonged"})
    ctx.decisions.append({
        "tick": ctx.tick, "poll": ctx.poll,
        "source": f"{source}:{rid}", "rule": rid,
        "kind": "combat-evidence", "mode": mode,
        "engaged": [h.get("id") for h in engaged],
        "watching": [h.get("id") for h in _fn_watching_hostiles(ctx)],
        "fighters": _fn_draftable(ctx),
        "order": {k: order.get(k) for k in
                  ("enabled", "engaged", "overrun", "last")},
        "markers": marks})


_COVER_HINTS = ("wall", "sandbag", "barricade", "tree", "chunk",
                "rock", "bunker", "embrasure")


def _cover_score(ctx, cell):
    """0-4: adjacent cells holding cover-ish things (map.cell things'
    def names matched loosely; missing surface -> 0)."""
    score = 0
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        res = ctx.rpc("map.cell", {"cell": [cell[0] + dx,
                                            cell[1] + dz]})
        if not isinstance(res, dict):
            continue
        names = " ".join(str(t.get("def") or t.get("label") or "")
                         for t in (res.get("things") or [])
                         if isinstance(t, dict)).lower()
        if any(h in names for h in _COVER_HINTS):
            score += 1
    return score


def _fn_rally_cell(ctx, pawn):
    """Distinct cover-preferring cell inside the rally rect per fighter
    (OrderLogic: cover-first score, greedy spread cap 4, center bias
    0.05). Assignments persist in rule_state; taken cells are skipped."""
    row = pawn if isinstance(pawn, dict) else {}
    pid = row.get("id", pawn)
    rect = _rally_rect(ctx)
    rc = _rally_center(ctx)
    st = ctx.state.setdefault("rally_assign", {})
    mine = st.get(str(pid))
    claimed = {tuple(v) for k, v in st.items() if k != str(pid)}
    if mine is not None and tuple(mine) not in claimed:
        return list(mine)
    best, best_s = None, -1e9
    for x in range(rect[0], rect[0] + rect[2]):
        for z in range(rect[1], rect[1] + rect[3]):
            if (x, z) in claimed:
                continue
            s = _cover_score(ctx, [x, z]) \
                - 0.05 * (_dist([x, z], rc) or 0)
            if s > best_s:
                best, best_s = [x, z], s
    if best is None:
        return None
    st[str(pid)] = best
    return best


def _fn_roofed(ctx, cell):
    res = ctx.rpc("map.cell", {"cell": cell})
    return isinstance(res, dict) and bool(res.get("roof"))


def _fn_enclosed_at(ctx, rect, min_cells=1):
    """Enclosed rooms overlapping `rect` with >= min_cells — position-
    aware so a ruin across the map doesn't count as shelter."""
    rooms = ctx.obs.get("rooms") or []
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms") or []
    base = ctx.obs.get("base") or {}
    if isinstance(base, dict) and isinstance(base.get("rooms"), list):
        rooms = list(rooms) + base["rooms"]
    n = 0
    for r in rooms:
        if not isinstance(r, dict) or (r.get("problems") or []):
            continue
        cells = r.get("cells") or r.get("free_floor")
        if cells is not None and int(cells) < int(min_cells or 1):
            continue
        if cells is not None and r.get("outdoors"):
            continue
        pos = _room_pos(r)
        if pos is not None and isinstance(rect, (list, tuple)) \
                and len(rect) >= 4:
            (x0, z0), (x1, z1) = pos
            sx, sz, sw, sh = rect[:4]
            if not (x0 < sx + sw and x1 >= sx
                    and z0 < sz + sh and z1 >= sz):
                continue
        n += 1
    return n


def _room_pos(r):
    def xy(v):
        return (v[0], v[1]) if isinstance(v, (list, tuple)) \
            and len(v) >= 2 else None
    rect = r.get("rect")
    if isinstance(rect, dict):
        lo, hi = xy(rect.get("min")), xy(rect.get("max"))
        if lo and hi:
            return (lo, hi)
    at = xy(r.get("at")) or xy(r.get("cell"))
    return (at, at) if at else None


def _fn_zone_named(ctx, label):
    zones = ctx.obs.get("storage") or []
    if isinstance(zones, dict):
        zones = zones.get("zones") or zones.get("stockpiles") or []
    return any(isinstance(z, dict)
               and (z.get("label") == label or z.get("zone") == label
                    or z.get("name") == label)
               for z in zones)


def _fn_room_count(ctx, min_cells=9):
    """Enclosed rooms map-wide with >= min_cells — 1-cell artifacts and
    outdoor areas don't count as housing."""
    rooms = ctx.obs.get("rooms") or []
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms") or []
    base = ctx.obs.get("base") or {}
    if isinstance(base, dict) and isinstance(base.get("rooms"), list):
        rooms = list(rooms) + base["rooms"]
    n = 0
    for r in rooms:
        if not isinstance(r, dict) or (r.get("problems") or []):
            continue
        cells = r.get("cells") or r.get("free_floor")
        if cells is not None and int(cells) < int(min_cells or 1):
            continue
        if cells is not None and r.get("outdoors"):
            continue
        n += 1
    return n


def _fn_idle_count(ctx, patterns=None):
    """Colonists whose job looks idle — substring match like the
    `contains_any` predicate op, patterns from universal.idle_patterns."""
    pats = [str(p).lower() for p in
            (patterns or ["idle", "wander", "standing", "wait"])]
    return sum(1 for c in _colonist_rows(ctx)
               if any(p in str(c.get("job") or "").lower() for p in pats))


def _fn_steward_stock(ctx, kind, field=None):
    """steward.status stock row for `kind` — whole row, or one field
    (target/current/suspended). Memoized per poll."""
    key = ("steward_stock", str(kind))
    if key not in ctx.cache:
        res = ctx.rpc("steward.status") or {}
        row = next((s for s in (res.get("stock") or [])
                    if isinstance(s, dict) and s.get("kind") == kind),
                   None)
        ctx.cache[key] = row
    row = ctx.cache[key]
    return row.get(field) if (field and isinstance(row, dict)) else row


def _fn_research(ctx):
    """Raw state.research dict {current, available, finished} —
    {} when the bridge lacks it (fail-closed)."""
    res = ctx.rpc("state.research")
    return res if isinstance(res, dict) else {}


def _fn_research_current(ctx):
    """Active project def/label, or None when nothing is queued."""
    cur = _fn_research(ctx).get("current")
    if isinstance(cur, dict):
        return cur.get("def") or cur.get("defName") or cur.get("label")
    return cur


def _fn_research_available(ctx):
    """Def names of projects whose prerequisites are met."""
    out = []
    for p in (_fn_research(ctx).get("available") or []):
        v = (p.get("def") or p.get("defName") or p.get("name")) \
            if isinstance(p, dict) else p
        if v:
            out.append(v)
    return out


def _fn_quests(ctx):
    """Active + available quest rows (state.quests)."""
    res = ctx.rpc("state.quests")
    if isinstance(res, dict):
        res = res.get("quests") or res.get("active") or []
    return res if isinstance(res, list) else []


def _fn_letters(ctx, choice_only=False):
    """state.letters rows with `choices` normalized to label strings;
    `letters(true)` keeps only letters awaiting a decision."""
    res = ctx.rpc("state.letters")
    rows = res.get("letters") if isinstance(res, dict) else res
    out = []
    for l in (rows if isinstance(rows, list) else []):
        if not isinstance(l, dict):
            continue
        labels = []
        for c in l.get("choices") or []:
            v = (c.get("label") or c.get("id") or c.get("name")) \
                if isinstance(c, dict) else c
            if v is not None:
                labels.append(str(v))
        row = dict(l)
        row["choices"] = labels
        if choice_only and not labels:
            continue
        out.append(row)
    return out


def _fn_rank_site(ctx, w=9, h=9, w_items=2.0, w_home=1.0,
                  w_fertile=0.0, fertile_step=4):
    """Score open rects by weighted distance to the item cluster and
    home center plus sampled soil fertility — deterministic; weights
    arrive as arguments. A zero ``w_fertile`` keeps the pure-proximity
    ranking (and zero map.cell calls)."""
    rects = ctx.obs.get("open_rects") or []
    if isinstance(rects, dict):
        rects = rects.get("rects") or []
    if not rects:
        return None
    items = _item_rows(ctx)
    if items:
        cx = sum(t.get("pos", [0, 0])[0] for t in items) / len(items)
        cz = sum(t.get("pos", [0, 0])[1] for t in items) / len(items)
    else:
        cx, cz = 0.0, 0.0
    home = ctx.obs.get("home_center")
    if not isinstance(home, (list, tuple)) or len(home) < 2:
        home = [cx, cz]

    def _cell(rect):
        if isinstance(rect, dict):
            return (rect.get("min") or rect.get("at")
                    or rect.get("cell") or [0, 0])
        return rect

    step = max(1, int(fertile_step or 4))

    def _fertility(rect):
        """Mean map.cell fertility over a coarse grid inside the
        candidate rect — live RPCs, so the step controls the spend."""
        x0, z0 = _cell(rect)[0], _cell(rect)[1]
        fsum = n = 0
        for x in range(int(x0), int(x0) + int(w), step):
            for z in range(int(z0), int(z0) + int(h), step):
                res = ctx.rpc("map.cell", {"cell": [x, z]})
                f = res.get("fertility") if isinstance(res, dict) \
                    else None
                if isinstance(f, (int, float)):
                    fsum += f
                    n += 1
        return fsum / n if n else 0.0

    use_fertility = bool(w_fertile) and ctx.game is not None

    def score(rect):
        x, z = _cell(rect)[0], _cell(rect)[1]
        s = float(w_items) * -((x - cx) ** 2 + (z - cz) ** 2) ** 0.5 \
            + float(w_home) * -((x - home[0]) ** 2
                                + (z - home[1]) ** 2) ** 0.5
        if use_fertility:
            s += float(w_fertile) * _fertility(rect)
        return s

    best = max(rects, key=score)
    cell = _cell(best)
    off = best.get("anchor_off") if isinstance(best, dict) else None
    if isinstance(off, (list, tuple)) and len(off) >= 2:
        cell = [cell[0] + off[0], cell[1] + off[1]]
    return {"min": list(cell)[:2],
            "rect": [int(cell[0]), int(cell[1]), int(w), int(h)],
            "score": score(best)}


FN = {
    "add": _fn_add, "sub": _fn_sub, "mul": _fn_mul, "fdiv": _fn_fdiv,
    "mod": _fn_mod, "min": _fn_min, "max": _fn_max,
    "cell": _fn_cell, "rect": _fn_rect,
    "first": _fn_first, "nth": _fn_nth, "count": _fn_count,
    "ids": _fn_ids, "anchor": _fn_anchor,
    "find_kind": _fn_find_kind, "find_def": _fn_find_def,
    "find_defs": _fn_find_defs, "find_defs_in": _fn_find_defs_in,
    "checker_cells": _fn_checker_cells,
    "pos": _fn_pos,
    "wind_path": _fn_wind_path, "obstructions": _fn_obstructions,
    "wind_obstructions": _fn_wind_obstructions,
    "turbine_site": _fn_turbine_site,
    "turbine_site_blocked": _fn_turbine_site_blocked,
    "terrain_at": _fn_terrain_at, "zone_at": _fn_zone_at,
    "loose_ids": _fn_loose_ids, "loose_id": _fn_loose_id,
    "loose_count": _fn_loose_count, "forbidden_ids": _fn_forbidden_ids,
    "stack_of": _fn_stack_of,
    "blueprints": _fn_blueprints, "blueprints_in": _fn_blueprints_in,
    "blueprints_pending": _fn_blueprints_pending,
    "fertile": _fn_fertile,
    "stuff": _fn_stuff, "home": _fn_home, "near_home": _fn_near_home,
    "buildable_at": _fn_buildable_at, "free_cell": _fn_free_cell,
    "hostile_faction": _fn_hostile_faction,
    "colonists": _colonist_rows, "colonist_ids": _fn_colonist_ids,
    "best": _fn_best, "unarmed": _fn_unarmed,
    "armor_ids": _fn_armor_ids, "armed_count": _fn_armed_count,
    "weapons_avail": _fn_weapons_avail,
    "arm_pawn": _fn_arm_pawn, "arm_weapon": _fn_arm_weapon,
    "arm_pending": _fn_arm_pending,
    "upgrade_pawn": _fn_upgrade_pawn,
    "upgrade_weapon": _fn_upgrade_weapon,
    "upgrade_armor_pawn": _fn_upgrade_armor_pawn,
    "upgrade_armor": _fn_upgrade_armor,
    "equip_pending": _fn_equip_pending,
    "living_hostiles": _fn_living_hostiles,
    "armed_ids": _fn_armed_ids, "drafted_ids": _fn_drafted_ids,
    "nearest_hostile": _fn_nearest_hostile,
    "downed_ids": _fn_downed_ids, "fleeing_ids": _fn_fleeing_ids,
    "dialogs": _fn_dialogs,
    "roofed": _fn_roofed, "enclosed_at": _fn_enclosed_at,
    "zone_named": _fn_zone_named, "rank_site": _fn_rank_site,
    "room_count": _fn_room_count, "idle_count": _fn_idle_count,
    "steward_stock": _fn_steward_stock,
    "research": _fn_research, "research_current": _fn_research_current,
    "research_available": _fn_research_available,
    "quests": _fn_quests, "letters": _fn_letters,
    "engaged_hostiles": _fn_engaged_hostiles,
    "watching_hostiles": _fn_watching_hostiles,
    "draftable": _fn_draftable, "fighters": _fn_fighters,
    "order_state": _fn_order_state, "combat_mode": _fn_combat_mode,
    "ticks_since_hostile": _fn_ticks_since_hostile,
    "hostiles_in_home": _fn_hostiles_in_home,
    "hostiles_within": _fn_hostiles_within,
    "nearest_fleeing": _fn_nearest_fleeing,
    "safe_cell": _fn_safe_cell, "skill_of": _fn_skill_of,
    "health_of": _fn_health_of, "need_of": _fn_need_of,
    "weapon_stats": _fn_weapon_stats, "speed_of": _fn_speed_of,
    "outranges": _fn_outranges, "outranged_by": _fn_outranged_by,
    "outrun_by": _fn_outrun_by, "in_range": _fn_in_range,
    "enemy_mix": _fn_enemy_mix, "enemy_max_range": _fn_enemy_max_range,
    "threat_power": _fn_threat_power, "manhunters": _fn_manhunters,
    "free_beds": _fn_free_beds, "casualty_ids": _fn_casualty_ids,
    "pawns_needing_tend": _fn_pawns_needing_tend,
    "kite_cell": _fn_kite_cell, "block_cell": _fn_block_cell,
    "rally_cell": _fn_rally_cell,
}


# -- selectors ------------------------------------------------------------------

def select(spec, ctx) -> list:
    """Candidate list for `for_each`: a selector name or a `@fn:`/path
    resolver returning a list."""
    if spec is None:
        return []
    if isinstance(spec, dict):
        rows = select(spec.get("from"), ctx)
        if spec.get("where"):
            out = []
            for i, c in enumerate(rows):
                ctx.vars["it"] = c
                ctx.vars["index"] = i
                if check(spec["where"], ctx):
                    out.append(c)
            return out
        return rows
    if isinstance(spec, str) and spec.startswith("@"):
        rows = resolve(spec, ctx)
        return rows if isinstance(rows, list) else []
    fn = _SELECTORS.get(spec)
    return fn(ctx) if fn else []


def _sel_colonists(ctx):
    return _colonist_rows(ctx)


def _sel_unarmed(ctx):
    unarmed = set(_fn_unarmed(ctx))
    return [c for c in _colonist_rows(ctx) if c.get("id") in unarmed]


def _sel_hostiles(ctx):
    return _hostile_rows(ctx)


def _sel_living(ctx):
    return _fn_living_hostiles(ctx)


def _sel_downed(ctx):
    downed = set(_fn_downed_ids(ctx))
    return [h for h in _hostile_rows(ctx)
            if isinstance(h, dict) and h.get("id") in downed]


def _sel_fleeing(ctx):
    fled = set(_fn_fleeing_ids(ctx))
    return [h for h in _hostile_rows(ctx)
            if isinstance(h, dict) and h.get("id") in fled]


def _sel_items(ctx):
    return _item_rows(ctx)


def _sel_forbidden(ctx):
    return _things(ctx.obs.get("forbidden") or {})


def _sel_fighters(ctx):
    ids = set(_fn_draftable(ctx))
    return [c for c in _colonist_rows(ctx) if c.get("id") in ids]


def _sel_engaged(ctx):
    return _fn_engaged_hostiles(ctx)


def _sel_watching(ctx):
    return _fn_watching_hostiles(ctx)


def _sel_casualties(ctx):
    ids = set(_fn_casualty_ids(ctx))
    return [c for c in _colonist_rows(ctx) if c.get("id") in ids]


_SELECTORS = {
    "colonists": _sel_colonists,
    "unarmed_colonists": _sel_unarmed,
    "hostiles": _sel_hostiles,
    "living_hostiles": _sel_living,
    "downed_hostiles": _sel_downed,
    "fleeing_hostiles": _sel_fleeing,
    "items": _sel_items,
    "forbidden_items": _sel_forbidden,
    "fighters": _sel_fighters,
    "draftable": _sel_fighters,
    "engaged_hostiles": _sel_engaged,
    "watching_hostiles": _sel_watching,
    "hostiles_in_home": lambda c: _fn_hostiles_in_home(c),
    "manhunters": lambda c: _fn_manhunters(c),
    "casualties": _sel_casualties,
}


# -- steps & rules --------------------------------------------------------------

def _cooldown_ok(ctx, key, polls) -> bool:
    cd = ctx.state.setdefault("cooldowns", {})
    return ctx.poll - cd.get(key, -10 ** 9) >= int(polls or 0)


def _cooldown_set(ctx, key) -> None:
    ctx.state.setdefault("cooldowns", {})[key] = ctx.poll


def _record(ctx, source, template, params, ok):
    """Append a Quick-Action Matrix row to the ctx decision sink."""
    if ctx.decisions is not None:
        ctx.decisions.append({"tick": ctx.tick, "poll": ctx.poll,
                              "source": source, "template": template,
                              "params": params, "ok": bool(ok)})


def run_steps(steps, dispatcher, ctx, source="steps") -> dict:
    """Execute a step list through the single dispatcher.

    Step fields: template (required), params, when (predicate), needs
    (resolver must be truthy), for_each (selector/resolver list bound to
    @var:it + @var:index), times (repeat N), cooldown_polls (per resolved
    template+params), optional (failure doesn't abort the list).
    ``@var:last_ok``/``@var:last_result`` expose the previous step's
    dispatch outcome so sequential writes can chain (e.g. configure what
    a prior step just created). `ok_when` is an extra predicate checked
    against ``last_result`` — a bridge call that completed but produced
    nothing (e.g. ``placed: []``) can still be judged a failure."""
    results = []
    ctx.vars["last_ok"] = False
    ctx.vars["last_result"] = None
    for st in steps or []:
        if not isinstance(st, dict) or not st.get("template"):
            continue
        candidates = select(st["for_each"], ctx) \
            if st.get("for_each") is not None else [None]
        times = int(resolve(st.get("times"), ctx) or 1)
        for idx, cand in enumerate(candidates):
            ctx.vars["it"] = cand
            ctx.vars["index"] = idx
            # when/needs evaluate per candidate — predicates may gate on
            # @var:it (per-pawn/site choice), which only exists here
            if st.get("when") and not check(st["when"], ctx):
                continue
            if "needs" in st and not resolve(st["needs"], ctx):
                continue
            for _ in range(max(1, times)):
                params = {k: v for k, v in
                          resolve(st.get("params") or {}, ctx).items()
                          if v is not None}  # None -> param omitted
                cd_key = ("step", st["template"],
                          str(sorted(params.items(), key=lambda kv: str(kv))))
                if st.get("cooldown_polls") \
                        and not _cooldown_ok(
                            ctx, cd_key,
                            resolve(st["cooldown_polls"], ctx)):
                    continue
                r = dispatcher.dispatch(st["template"], params)
                ok = bool(r.get("ok"))
                ctx.vars["last_result"] = r.get("result") \
                    if isinstance(r.get("result"), dict) else {}
                if ok and st.get("ok_when") is not None:
                    ok = bool(check(st["ok_when"], ctx))
                ctx.vars["last_ok"] = ok
                if st.get("cooldown_polls"):
                    _cooldown_set(ctx, cd_key)
                results.append({"template": st["template"],
                                "params": params, "ok": ok})
                _record(ctx, source, st["template"], params, ok)
                if not ok and not st.get("optional"):
                    return {"ok": False,
                            "error": r.get("error") or {
                                "code": "policy.ok_when",
                                "message": f"{st['template']} completed but "
                                           "ok_when failed"},
                            "results": results}
    return {"ok": True, "results": results}


def run_rules(rules, dispatcher, ctx, source="rules") -> list[dict]:
    """Evaluate pack invariant rules for this poll. Each rule:
    {id, for_each?, when?, cooldown: {polls, key?}, try: [alternatives]}.
    First `try` alternative whose `when`+`needs` pass gets dispatched;
    the cooldown records the attempt (success or refusal — anti-spam)."""
    fired = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id") or "rule"
        cands = select(rule["for_each"], ctx) \
            if rule.get("for_each") is not None else [None]
        cd = rule.get("cooldown") or {}
        for idx, cand in enumerate(cands):
            ctx.vars["it"] = cand
            ctx.vars["index"] = idx
            if rule.get("when"):
                ok, clauses = check_detail(rule["when"], ctx)
                if not ok:
                    # evidence-marked rules leave a structured gate row
                    # naming the failing clause (T010/FR-1908); other
                    # rules stay silent to keep the log bounded
                    if ctx.decisions is not None and (
                            rule.get("evidence")
                            or rule.get("kind") == "combat-evidence"):
                        ctx.decisions.append({
                            "tick": ctx.tick, "poll": ctx.poll,
                            "source": f"{source}:{rid}", "gate": True,
                            "rule": rid,
                            "subject": (cand.get("id")
                                        if isinstance(cand, dict)
                                        else cand),
                            "clauses": clauses})
                    continue
            if rule.get("kind") == "combat-evidence":
                # evidence-only rule (feature 019): append the combat
                # posture snapshot — engaged/watch sets, fighters,
                # delegate-order state, lifecycle markers — no dispatch
                _combat_evidence(ctx, rid, source)
                fired.append({"rule": rid, "kind": "combat-evidence"})
                continue
            key = resolve(cd.get("key"), ctx) if cd.get("key") else (
                cand.get("id") if isinstance(cand, dict) else cand)
            cd_key = ("rule", rid, key)
            if not _cooldown_ok(ctx, cd_key, resolve(cd.get("polls"), ctx)):
                continue
            for alt in rule.get("try") or []:
                if not isinstance(alt, dict) or not alt.get("template"):
                    continue
                if alt.get("when") and not check(alt["when"], ctx):
                    continue
                if "needs" in alt and not resolve(alt["needs"], ctx):
                    continue
                params = {k: v for k, v in
                          resolve(alt.get("params") or {}, ctx).items()
                          if v is not None}
                r = dispatcher.dispatch(alt["template"], params)
                _cooldown_set(ctx, cd_key)
                fired.append({"rule": rid, "template": alt["template"],
                              "ok": bool(r.get("ok")),
                              "params": params})
                _record(ctx, f"{source}:{rid}", alt["template"],
                        params, r.get("ok"))
                break
    return fired


# -- validation ----------------------------------------------------------------

def _walk_strings(node):
    """Yield every string in a nested pack node."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)


def _walk_preds(node):
    """Yield every predicate-shaped dict (has 'op' or combinators)."""
    if isinstance(node, dict):
        if "op" in node or "all" in node or "any" in node or "not" in node:
            yield node
        for v in node.values():
            yield from _walk_preds(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_preds(v)


def validate_policy(pack: dict, template_ids=None) -> list[str]:
    """Fail-closed pack audit: unknown @fn:, selector, predicate op, or
    template id is a named error. Returns a problem list (empty = ok)."""
    problems: list[str] = []
    known_templates = set(template_ids or [])
    if template_ids is None:
        from .templates import (phases_of, rules_of,  # noqa: E501
                                standing_goals_of, templates_of)
        # lazy import: templates loads policy for pack validation
        known_templates = {t.get("id") for t in templates_of(pack)
                           if isinstance(t, dict)}

    def _check_unit(unit: dict, label: str) -> None:
        """Work-unit checks shared by prescriptive steps and goals:
        declared effect predicate + template refs in steps/escalate."""
        if not isinstance(unit, dict) or not unit.get("id"):
            problems.append(f"{label}s[]: every entry needs an id")
            return
        uid = unit["id"]
        if "effect" not in unit:
            problems.append(f"{label} {uid}: no effect predicate")
        for st in unit.get("steps") or []:
            tid = st.get("template") if isinstance(st, dict) else None
            if not tid:
                problems.append(f"{label} {uid}: step missing template")
            elif tid not in known_templates:
                problems.append(
                    f"{label} {uid}: unknown template '{tid}'")
        for st in (unit.get("escalate") or {}).get("steps") or []:
            tid = st.get("template") if isinstance(st, dict) else None
            if not tid:
                problems.append(
                    f"{label} {uid}: escalate step missing template")
            elif tid not in known_templates:
                problems.append(
                    f"{label} {uid}: escalate unknown template '{tid}'")

    # v1 surfaces (accessors cover migrated v0 too): lifecycle phases —
    # prescriptive `steps` hold the work units; `goals` are phase-scoped
    # standing goals — then pack-level rules and standing_goals.
    phases = phases_of(pack)
    if not isinstance(phases, list):
        problems.append("phases: must be a list")
        phases = []
    for ph in phases:
        if not isinstance(ph, dict) or not ph.get("id"):
            problems.append("phases[]: every phase needs an id")
            continue
        for unit in ph.get("steps") or []:
            _check_unit(unit, "phase")
        for g in ph.get("goals") or []:
            _check_unit(g, "goal")
    for rule in rules_of(pack):
        if not isinstance(rule, dict) or not rule.get("id"):
            problems.append("universal.rules[]: every rule needs an id")
            continue
        fe = rule.get("for_each")
        if isinstance(fe, str) and not fe.startswith("@") \
                and fe not in _SELECTORS:
            problems.append(f"rule {rule['id']}: unknown selector '{fe}'")
        for alt in rule.get("try") or []:
            tid = alt.get("template") if isinstance(alt, dict) else None
            if tid and tid not in known_templates:
                problems.append(
                    f"rule {rule['id']}: unknown template '{tid}'")
    combat = pack.get("combat") or {}
    for section in ("setup", "spawn", "cleanup"):
        for st in combat.get(section) or []:
            tid = st.get("template") if isinstance(st, dict) else None
            if tid and tid not in known_templates:
                problems.append(
                    f"combat.{section}: unknown template '{tid}'")
    for g in standing_goals_of(pack):
        _check_unit(g, "goal")
    for s in _walk_strings(pack):
        for m in _FN_RE.finditer(s) if s.startswith("@fn:") else []:
            if m.group(1) not in FN:
                problems.append(f"unknown @fn:{m.group(1)}")
    # predicate-op audit covers every predicate-bearing surface: v1
    # phases/goals/rules via accessors + the retained cfg alias blocks
    for pred in _walk_preds(
            {"phases": phases, "rules": rules_of(pack),
             "goals": standing_goals_of(pack), "c": combat,
             "cfg": {k: v for k, v in pack.items()
                     if k in ("start", "govern", "universal")}}):
        op = pred.get("op")
        if op and op not in _OPS:
            problems.append(f"unknown predicate op '{op}'")
    return problems
