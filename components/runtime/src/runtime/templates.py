"""Policy-pack loading for the dispatcher (feature 004; FR-302/305, FR-304).

A pack is validated data under ``components/rimbrain/packs/``. A pack id is
a relative path resolved folder-first (``<id>/pack.yaml``, the canonical
form — aux files like notes live beside it) then flat (``<id>.yaml``,
kept for ``candidates/``). Loading:

1. parse + schema-validate (jsonschema when available, else a builtin mirror);
2. cross-check every template ``method`` against the sealed bridge inventory
   (``baselines/upstream-85cb050/rpc-inventory.json``) — unknown method rejects
   the whole pack (fail-closed, no partial pack);
3. compute the pack revision hash = sha256(canonical-JSON) (feature 001) —
   stable across loads, byte-sensitive;
4. drift checks compare the loaded hash against the current file hash so a
   mid-run pack edit refuses new dispatches (``dispatch.pack_drift``,
   constitution: scored runs reject dirty state).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml

try:
    from contracts.canonical import canonical_bytes
except ImportError:  # pragma: no cover - contracts always co-installed
    from contracts import canonical_bytes  # type: ignore[no-redef]

from ._root import bundle_root, repo_root

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKS_ENV = "RIMBRAIN_PACKS_DIR"
# frozen: editable packs live beside the exe; the bundled copies inside the
# image are the fallback so the binary still runs standalone (UR-ARC-009)
_DEFAULT_BUNDLED = bundle_root() / "components" / "rimbrain" / "packs"
DEFAULT_PACKS = (_P if (_P := repo_root() / "packs").is_dir()
                 else _DEFAULT_BUNDLED)
INVENTORY = bundle_root() / "baselines" / "upstream-85cb050" / "rpc-inventory.json"

PACK_SCHEMA = bundle_root() / "components" / "contracts" / "schemas" / "runtime" / "pack.schema.json"

__all__ = ["PackError", "packs_dir", "pack_path", "list_packs", "load_pack",
           "current_hash", "pack_drift", "inventory_methods"]


def packs_dir() -> Path:
    override = os.environ.get(PACKS_ENV)
    return Path(override) if override else DEFAULT_PACKS


def pack_path(pack_id: str) -> Path:
    """Resolve a pack id to its YAML file — ``<id>/pack.yaml`` when the
    folder exists, else ``<id>.yaml``. Ids are relative paths under
    ``packs_dir()``; absolute ids and ``..`` segments are refused
    fail-closed (ids can arrive from the UI reset channel)."""
    rel = Path(pack_id)
    if rel.is_absolute() or ".." in rel.parts or not str(pack_id).strip():
        raise PackError(err("pack.invalid_id",
                            f"pack id '{pack_id}' is not a relative path",
                            {"pack": pack_id}))
    folder = packs_dir() / rel / "pack.yaml"
    return folder if folder.is_file() else packs_dir() / f"{pack_id}.yaml"


def list_packs() -> list[str]:
    """Pack ids under ``packs_dir()``: folder packs (``<dir>/pack.yaml`` ->
    ``<dir>``) plus flat ``*.yaml`` (aux files inside a folder pack are
    not packs)."""
    base = packs_dir()
    out: set[str] = set()
    for f in base.rglob("*.yaml"):
        try:
            rel = f.relative_to(base)
        except ValueError:
            continue
        if f.name == "pack.yaml":
            if rel.parent.parts:
                out.add(rel.parent.as_posix())
        elif not (f.parent / "pack.yaml").is_file():
            out.add(rel.with_suffix("").as_posix())
    return sorted(out)


def err(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message, "retryable": False}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


class PackError(Exception):
    """Fail-closed pack failure; ``.envelope`` is the common/error shape."""

    def __init__(self, envelope: dict):
        super().__init__(envelope["error"]["message"])
        self.envelope = envelope


def inventory_methods() -> set[str]:
    """Method names from the sealed RPC inventory (cached)."""
    if not INVENTORY.is_file():
        return set()
    if not hasattr(inventory_methods, "_cache"):
        try:
            rows = json.loads(INVENTORY.read_text(encoding="utf-8"))
            inventory_methods._cache = {r.get("name") for r in rows
                                        if isinstance(r, dict) and r.get("name")}
        except (OSError, ValueError):
            inventory_methods._cache = set()
    return inventory_methods._cache


def _jsonschema_problems(doc: dict) -> list[str] | None:
    try:
        import jsonschema
    except ImportError:
        return None
    try:
        schema = json.loads(PACK_SCHEMA.read_text(encoding="utf-8"))
    except OSError:
        return None
    validator = jsonschema.Draft202012Validator(schema)
    problems = [f"{list(e.absolute_path) or '$'}: {e.message}"
                for e in validator.iter_errors(doc)]
    return problems[:25]


def _builtin_problems(doc: dict) -> list[str]:
    """Mirror of pack.schema.json over the *migrated* (v1-union) doc:
    v0 packs keep their keys so legacy requireds still hold; native v1
    packs satisfy the same invariants via v1 surfaces."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: pack must be an object"]
    if "schema_version" not in doc:
        problems.append("$.schema_version: required")
    if not (doc.get("pack_id") or (doc.get("meta") or {}).get("pack_id")):
        problems.append("$.pack_id: required")
    if not (doc.get("revision") or (doc.get("meta") or {}).get("revision")):
        problems.append("$.revision: required")
    templates = templates_of(doc)
    if not isinstance(templates, list) or not templates:
        problems.append("$.templates: required non-empty array")
    elif any(not isinstance(t, dict) or not t.get("id")
             or not t.get("method") or not isinstance(t.get("params_schema"), dict)
             for t in templates):
        problems.append("$.templates: each entry needs id, method, params_schema")
    return problems[:25]


def _fastevolve_problems(doc: dict) -> list[str]:
    """Feature 021 section checks — always run (the JSON schema only
    types the knobs; the trigger predicates need the policy grammar)."""
    fe = doc.get("fastevolve")
    if fe is None:
        return []
    if not isinstance(fe, dict):
        return ["$.fastevolve: must be an object"]
    problems: list[str] = []
    for k in ("max_reloads_per_day", "saves_poll_every",
              "max_anchor_age_days", "max_passes_per_day"):
        v = fe.get(k)
        if v is not None and (not isinstance(v, int)
                              or isinstance(v, bool) or v < 0):
            problems.append(f"$.fastevolve.{k}: must be an int >= 0")
    trig = fe.get("triggers")
    if trig is not None and not isinstance(trig, dict):
        problems.append("$.fastevolve.triggers: must be an object")
    for k in ("fail_when", "near_when"):
        p = (trig or {}).get(k)
        if p is not None:
            problems += [f"$.fastevolve.triggers.{k}: {m}"
                         for m in _pred_problems(p)]
    methods = {t.get("method") for t in templates_of(doc)
               if isinstance(t, dict)}
    if "game.load" not in methods:
        problems.append("$.fastevolve: pack opts into fast-evolve but "
                        "declares no game.load template — retries "
                        "can't reload the day anchor")
    return problems[:25]


def _pred_problems(pred) -> list[str]:
    """Shape-check one predicate tree against the policy.check grammar —
    combinator nodes carry sub-predicates; leaves need a known op."""
    from . import policy
    if not isinstance(pred, dict):
        return ["predicate must be an object"]
    out: list[str] = []
    for k in ("all", "any"):
        if k in pred:
            subs = pred[k]
            if not isinstance(subs, list):
                return [f"'{k}' must be a list of predicates"]
            for s in subs:
                out += _pred_problems(s)
            return out
    if "not" in pred:
        return _pred_problems(pred["not"])
    op = pred.get("op")
    if op not in policy._OPS:
        out.append(f"unknown op '{op}'")
    elif not isinstance(pred.get("field"), str):
        out.append("leaf predicate needs a string 'field'")
    return out


def validate_pack(doc: dict) -> list[str]:
    problems = _jsonschema_problems(doc)
    problems = _builtin_problems(doc) if problems is None else problems
    return (problems + _fastevolve_problems(doc))[:25]


def _hash_of(doc: dict) -> str:
    """sha256 of the canonical *normalized* doc — every hash site (load,
    drift check, candidate digest) agrees because migration is
    idempotent (feature 017)."""
    return hashlib.sha256(canonical_bytes(migrate_v0(doc))).hexdigest()


# -- schema v1: v0->v1 load-time migration (feature 017) -----------------
# The migrated doc is the union: v1 surfaces overlaid on the intact v0
# cfg blocks, so `@cfg:start.*`/`@cfg:govern.*` resolvers keep working
# verbatim (the retained blocks ARE the alias map — no resolver rewrite)
# and legacy readers keep working until the phase engine lands.

def migrate_v0(doc: dict) -> dict:
    """Return a schema-v1 view of a v0 pack doc. Pure: input unmodified.
    `schema_version` absent => 0 => migrate; 1 => pass through; >1
    rejected by the caller."""
    if int(doc.get("schema_version") or 0) >= 1:
        return doc
    out = dict(doc)
    start = doc.get("start") or {}
    govern = doc.get("govern") or {}
    universal = doc.get("universal") or {}
    out["schema_version"] = 1
    out.setdefault("meta", {"pack_id": doc.get("pack_id"),
                            "revision": doc.get("revision"),
                            "class": doc.get("class")})
    out.setdefault("capabilities", {})
    out["capabilities"].setdefault("templates",
                                   list(doc.get("templates") or []))
    # emergency[] -> reflexes[]: `condition` becomes `when`; the unified
    # predicate evaluator (T008) makes the dialects equivalent.
    out.setdefault("reflexes", [
        {**{("when" if k == "condition" else k): v
            for k, v in r.items()}}
        for r in (doc.get("emergency") or [])])
    out.setdefault("rules", list(universal.get("rules") or []))
    senses = {"universal": {k: v for k, v in universal.items()
                            if k != "rules"}}
    for key in ("site", "shelter", "roof", "food", "cooking",
                "recreation", "hauling", "arm", "defense"):
        if key in start:
            senses[key] = start[key]
    senses["govern"] = {k: v for k, v in govern.items()
                        if k != "goals"}
    out.setdefault("senses", senses)
    phases = ([{"id": "init", "prescriptive": True,
                "steps": list(start.get("phases") or []),
                "complete": dict(start.get("exit") or {}),
                "cfg": start}]
              if start.get("phases") else [])
    # a pack carrying a combat: script gets it as a gated phase kind —
    # engaged only under scripted=True (dev harness / --stage combat)
    if _combat_script(doc) is not None:
        phases.append({"id": "combat", "kind": "combat",
                       "combat": _combat_script(doc)})
    out.setdefault("phases", phases)
    out.setdefault("standing_goals", list(govern.get("goals") or []))
    out.setdefault("options", list(doc.get("goal_options") or []))
    out.setdefault("decide", {
        "select": {"role": "rimbrain.select", "batch_pawns": True,
                   "fallback": "priority_head", "shadow": True},
        "plan": {"role": "rimbrain.plan", "cadence_s": 150,
                 "on_phase_boundary": True}})
    return out


_COMBAT_SCRIPT_KEYS = frozenset({
    "checkpoint", "prereq", "rounds", "hostile_count", "pawn_kind",
    "spawn_offset", "setup", "spawn", "engage", "cleanup"})


def _combat_script(doc: dict):
    """`combat:` is the dev-harness script (feature 010) only when it
    carries script keys — the fair-class combat cfg block (feature 019)
    shares the key and must not become a ``kind: combat`` phase."""
    blk = doc.get("combat")
    return blk if isinstance(blk, dict) \
        and _COMBAT_SCRIPT_KEYS & blk.keys() else None


_V0_TO_V1 = {
    "templates": "capabilities.templates",
    "emergency": "reflexes",
    "universal.rules": "rules",
    "universal": "senses.universal",
    "start.phases": "phases.0.steps",
    "start.exit": "phases.0.complete",
    "start": "phases.0.cfg",
    "govern.goals": "standing_goals",
    "govern": "senses.govern",
    "goal_options": "options",
}


def v0_to_v1_path(path: str) -> str:
    """Rewrite a v0 pack path to its v1 location (longest-prefix match);
    packmut ops addressing v0 paths go through this before apply."""
    for old, new in sorted(_V0_TO_V1.items(), key=lambda kv: -len(kv[0])):
        if path == old or path.startswith(old + "."):
            return new + path[len(old):]
    return path


# v1-surface accessors — one read path for both native v1 packs and
# migrated v0 packs (which retain their original keys as aliases).

def templates_of(pack: dict) -> list:
    return (pack.get("capabilities") or {}).get("templates") \
        or pack.get("templates") or []


def reflexes_of(pack: dict) -> list:
    return pack.get("reflexes") or pack.get("emergency") or []


def rules_of(pack: dict) -> list:
    return pack.get("rules") \
        or (pack.get("universal") or {}).get("rules") or []


def phases_of(pack: dict) -> list:
    if pack.get("phases") is not None:
        return pack["phases"]
    start = pack.get("start") or {}
    phases = ([{"id": "init", "prescriptive": True,
                "steps": start.get("phases") or [],
                "complete": start.get("exit") or {}, "cfg": start}]
              if start.get("phases") else [])
    script = _combat_script(pack)
    if script is not None:
        phases.append({"id": "combat", "kind": "combat",
                       "combat": script})
    return phases


def standing_goals_of(pack: dict) -> list:
    return pack.get("standing_goals") \
        or (pack.get("govern") or {}).get("goals") or []


def options_of(pack: dict) -> list:
    return pack.get("options") or pack.get("goal_options") or []


def decide_of(pack: dict) -> dict:
    return pack.get("decide") or {}


def load_pack(pack_id: str) -> dict:
    """Load + validate the pack at ``pack_path(pack_id)`` -> ``{pack, hash,
    path}``.

    Raises :class:`PackError` (fail-closed) on any violation; never returns a
    partially validated pack.
    """
    path = pack_path(pack_id)
    if not path.is_file():
        raise PackError(err("pack.not_found",
                            f"no pack '{pack_id}' at {path}",
                            {"pack": pack_id, "path": str(path)}))
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(err("pack.parse_failed",
                            f"pack '{pack_id}' is not valid YAML: {exc}",
                            {"pack": pack_id}))
    if not isinstance(doc, dict):
        raise PackError(err("pack.validation.failed",
                            f"pack '{pack_id}' is not an object"))
    if int(doc.get("schema_version") or 0) > 1:
        raise PackError(err(
            "pack.schema_version",
            f"pack '{pack_id}' declares schema_version "
            f"{doc.get('schema_version')} > 1",
            {"pack": pack_id}))
    doc = migrate_v0(doc)
    problems = validate_pack(doc)
    if problems:
        raise PackError(err(
            "pack.validation.failed",
            f"pack '{pack_id}' failed schema validation",
            {"pack": pack_id, "issues": problems}))
    unknown = sorted({t["method"] for t in templates_of(doc)}
                     - inventory_methods())
    if unknown:
        raise PackError(err(
            "pack.inventory_mismatch",
            f"pack '{pack_id}' references methods absent from the bridge "
            f"inventory: {unknown}",
            {"pack": pack_id, "unknown_methods": unknown}))
    if doc.get("policy_version") is not None:
        # feature 012: packs declaring the policy vocabulary are audited
        # fail-closed — unknown @fn/selector/op/template is a load error
        from .policy import validate_policy
        problems = validate_policy(doc)
        if problems:
            raise PackError(err(
                "pack.policy_invalid",
                f"pack '{pack_id}' failed policy validation",
                {"pack": pack_id, "issues": problems}))
    return {"pack": doc, "hash": _hash_of(doc), "path": str(path)}


def current_hash(pack_id: str) -> str | None:
    """Hash of the pack file as it is right now (drift check); None if gone."""
    try:
        path = pack_path(pack_id)
    except PackError:
        return None
    if not path.is_file():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    # normalize so file hash and loaded hash compare on the same shape
    return _hash_of(migrate_v0(doc)) if isinstance(doc, dict) else None


def pack_drift(pack_id: str, loaded_hash: str) -> bool:
    """True when the pack file changed since ``load_pack`` (mid-run edit)."""
    now = current_hash(pack_id)
    return now is None or now != loaded_hash
