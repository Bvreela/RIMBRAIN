"""Policy-pack loading for the dispatcher (feature 004; FR-302/305, FR-304).

A pack is validated data under ``components/rimbrain/packs/``. Loading:

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

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKS_ENV = "RIMBRAIN_PACKS_DIR"
DEFAULT_PACKS = REPO_ROOT / "components" / "rimbrain" / "packs"
INVENTORY = REPO_ROOT / "baselines" / "upstream-85cb050" / "rpc-inventory.json"

PACK_SCHEMA = REPO_ROOT / "components" / "contracts" / "schemas" / "runtime" / "pack.schema.json"

__all__ = ["PackError", "packs_dir", "load_pack", "current_hash", "pack_drift",
           "inventory_methods"]


def packs_dir() -> Path:
    override = os.environ.get(PACKS_ENV)
    return Path(override) if override else DEFAULT_PACKS


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
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: pack must be an object"]
    for key in ("schema_version", "pack_id", "revision", "templates",
                "jobs", "decision_map", "emergency"):
        if key not in doc:
            problems.append(f"$.{key}: required")
    templates = doc.get("templates")
    if not isinstance(templates, list) or not templates:
        problems.append("$.templates: required non-empty array")
    elif any(not isinstance(t, dict) or not t.get("id")
             or not t.get("method") or not isinstance(t.get("params_schema"), dict)
             for t in templates):
        problems.append("$.templates: each entry needs id, method, params_schema")
    return problems[:25]


def validate_pack(doc: dict) -> list[str]:
    problems = _jsonschema_problems(doc)
    return _builtin_problems(doc) if problems is None else problems


def _hash_of(doc: dict) -> str:
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def load_pack(pack_id: str) -> dict:
    """Load + validate ``<packs_dir>/<pack_id>.yaml`` -> ``{pack, hash, path}``.

    Raises :class:`PackError` (fail-closed) on any violation; never returns a
    partially validated pack.
    """
    path = packs_dir() / f"{pack_id}.yaml"
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
    problems = validate_pack(doc)
    if problems:
        raise PackError(err(
            "pack.validation.failed",
            f"pack '{pack_id}' failed schema validation",
            {"pack": pack_id, "issues": problems}))
    unknown = sorted({t["method"] for t in doc["templates"]}
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
    path = packs_dir() / f"{pack_id}.yaml"
    if not path.is_file():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return _hash_of(doc) if isinstance(doc, dict) else None


def pack_drift(pack_id: str, loaded_hash: str) -> bool:
    """True when the pack file changed since ``load_pack`` (mid-run edit)."""
    now = current_hash(pack_id)
    return now is None or now != loaded_hash
