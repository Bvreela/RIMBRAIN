"""Endpoint + binding registry (feature 002; FR-001/FR-003, UR-MOD-011..013).

``profiles/endpoints.yaml`` and ``profiles/bindings.yaml`` are authoritative and
hand-editable; this module loads them, validates them against the versioned
contracts in ``components/contracts/schemas/runtime/``, and writes back through
the same schema. YAML wins on divergence — there is no UI-only state (SC-003).

Failure conventions (FR-009): loaders raise :class:`RegistryError` carrying the
shared failure envelope ``{ok:false, error:{code,message,details?,retryable}}``;
mutating ops (add/update/delete/set_binding) return that envelope instead of
raising. Named codes: ``registry.validation.failed``, ``registry.endpoint.missing``,
``registry.endpoint.exists``, ``registry.endpoint.bound``.

Validation uses ``jsonschema`` when importable; otherwise a built-in structural
check mirrors the schemas so the runtime keeps a pyyaml-only dependency. The
cross-file rule (every endpoint id referenced by bindings.yaml must exist in
endpoints.yaml) is enforced in both paths — fail-closed at load.

Location overrides for tests/tools: ``RIMBRAIN_PROFILES_DIR`` env var points at
an alternate profiles directory; ``RIMBRAIN_CONTRACT_SCHEMAS`` overrides the
schema directory.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_PROFILES = REPO_ROOT / "profiles"
_DEFAULT_SCHEMAS = REPO_ROOT / "components" / "contracts" / "schemas" / "runtime"

PROFILES_ENV = "RIMBRAIN_PROFILES_DIR"
SCHEMAS_ENV = "RIMBRAIN_CONTRACT_SCHEMAS"

ENDPOINTS_SCHEMA = "endpoints.schema.json"
BINDINGS_SCHEMA = "bindings.schema.json"

ENDPOINTS_HEADER = (
    "# Endpoint registry - named, nonsecret LLM endpoints (UR-MOD-011/012).\n"
    "# Secrets live elsewhere: api_key_ref names an env var or config.local.yaml key.\n"
    "# Hand-editable; the UI (feature 002) reads/writes this same file.\n"
)
BINDINGS_HEADER = (
    "# Role bindings - semantic role -> endpoint+model (UR-MOD-013).\n"
    "# Runtime state, not policy: editing this never mutates an active RimBrain pack.\n"
    "# Episode manifests record the resolved endpoint+model per role (UR-MOD-016).\n"
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_KEYREF_RE = re.compile(r"^(env|config):[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_ROLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_APIS = {"openai-compat", "systemone"}
_CAPABILITIES = {
    "chat", "tool_calls", "reasoning", "typed_decisions", "embeddings", "vision",
}
_ENDPOINT_KEYS = {
    "id", "label", "api", "base_url", "api_key_ref", "strict", "decide_path",
    "models", "capabilities", "context", "cost_hint", "notes",
}
_BINDING_KEYS = {"endpoint", "model", "options"}
_DOC_KEYS = {"schema_version", "endpoints"}
_BINDINGS_DOC_KEYS = {"schema_version", "bindings", "degraded_paths"}

# Capability a role requires of its endpoint (FR-006). Any-of lists; roles not
# listed are ungated. Shared by write-time gating (set_binding, US3/AC2) and
# resolve-time gating (bindings.resolve_role).
ROLE_REQUIREMENTS = {
    "rimbrain.select": {"any": ["typed_decisions", "tool_calls"]},
    "rimbrain.plan": {"any": ["chat", "tool_calls"]},
    "rimbrain.review": {"any": ["chat", "tool_calls"]},
    "rimbrain.embed": {"all": ["embeddings"]},
}

__all__ = [
    "RegistryError", "err",
    "profiles_dir", "endpoints_path", "bindings_path",
    "load_endpoints", "save_endpoints", "load_bindings", "save_bindings",
    "get_endpoint", "add_endpoint", "update_endpoint", "delete_endpoint",
    "set_binding", "endpoint_capable", "ROLE_REQUIREMENTS",
]


def endpoint_capable(endpoint: dict, role: str) -> str | None:
    """Named reason when endpoint lacks the role's required capability."""
    req = ROLE_REQUIREMENTS.get(role)
    if not req:
        return None
    caps = set(endpoint.get("capabilities", []))
    if "all" in req and not set(req["all"]) <= caps:
        return f"requires all of {req['all']}, endpoint has {sorted(caps)}"
    if "any" in req and not set(req["any"]) & caps:
        return f"requires any of {req['any']}, endpoint has {sorted(caps)}"
    return None


# ---------------------------------------------------------------- errors --

def err(code: str, message: str, details: dict | None = None,
        retryable: bool = False) -> dict:
    """Shared failure envelope (common/error contract, FR-009)."""
    error = {"code": code, "message": message, "retryable": bool(retryable)}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


class RegistryError(Exception):
    """Fail-closed registry failure; ``.envelope`` is the common/error shape."""

    def __init__(self, envelope: dict):
        super().__init__(envelope["error"]["message"])
        self.envelope = envelope


# ----------------------------------------------------------------- paths --

def profiles_dir() -> Path:
    override = os.environ.get(PROFILES_ENV)
    return Path(override) if override else _DEFAULT_PROFILES


def schemas_dir() -> Path:
    override = os.environ.get(SCHEMAS_ENV)
    return Path(override) if override else _DEFAULT_SCHEMAS


def endpoints_path() -> Path:
    return profiles_dir() / "endpoints.yaml"


def bindings_path() -> Path:
    return profiles_dir() / "bindings.yaml"


# ------------------------------------------------------------ validation --

def _load_schema(name: str) -> dict:
    return json.loads((schemas_dir() / name).read_text(encoding="utf-8"))


def _jsonschema_errors(doc: dict, schema_file: str) -> list[str] | None:
    """Return schema violations via jsonschema, or None when unavailable."""
    try:
        import jsonschema
    except ImportError:
        return None
    try:
        schema = _load_schema(schema_file)
    except OSError:
        return None
    validator = jsonschema.Draft202012Validator(schema)
    problems = []
    for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "$" + "".join(f".{p}" if isinstance(p, str) else f"[{p}]"
                              for p in e.absolute_path)
        problems.append(f"{where}: {e.message}")
    return problems[:25]


def _check(cond: bool, problems: list[str], msg: str) -> None:
    if not cond:
        problems.append(msg)


def _builtin_validate_endpoints(doc: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: document must be an object"]
    _check(isinstance(doc.get("endpoints"), list), problems,
           "$.endpoints: required array")
    if problems:
        return problems
    for key in doc:
        if key not in _DOC_KEYS:
            problems.append(f"$.{key}: unknown property")
    seen: set[str] = set()
    for i, ep in enumerate(doc["endpoints"]):
        where = f"$.endpoints[{i}]"
        if not isinstance(ep, dict):
            problems.append(f"{where}: not an object")
            continue
        for key in ep:
            if key not in _ENDPOINT_KEYS:
                problems.append(f"{where}.{key}: unknown property")
        eid = ep.get("id")
        if not isinstance(eid, str) or not _ID_RE.match(eid):
            problems.append(f"{where}.id: missing or invalid id")
        elif eid in seen:
            problems.append(f"{where}.id: duplicate endpoint id '{eid}'")
        else:
            seen.add(eid)
        _check(ep.get("api") in _APIS, problems,
               f"{where}.api: must be one of {sorted(_APIS)}")
        _check(isinstance(ep.get("base_url"), str) and bool(ep.get("base_url")),
               problems, f"{where}.base_url: required string")
        ref = ep.get("api_key_ref")
        if ref is not None:
            _check(isinstance(ref, str) and bool(_KEYREF_RE.match(ref)),
                   problems,
                   f"{where}.api_key_ref: must be 'env:NAME' or 'config:NAME'")
        if "strict" in ep:
            _check(isinstance(ep["strict"], bool), problems,
                   f"{where}.strict: must be boolean")
        if ep.get("api") == "systemone":
            _check(isinstance(ep.get("decide_path"), str)
                   and ep["decide_path"].startswith("/"), problems,
                   f"{where}.decide_path: required for api=systemone")
        models = ep.get("models")
        _check(isinstance(models, list)
               and all(isinstance(m, str) and m for m in models), problems,
               f"{where}.models: required array of model ids")
        caps = ep.get("capabilities")
        _check(isinstance(caps, list)
               and all(c in _CAPABILITIES for c in caps), problems,
               f"{where}.capabilities: required array subset of {sorted(_CAPABILITIES)}")
    return problems


def _builtin_validate_bindings(doc: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["$: document must be an object"]
    _check(isinstance(doc.get("bindings"), dict), problems,
           "$.bindings: required object")
    if problems:
        return problems
    for key in doc:
        if key not in _BINDINGS_DOC_KEYS:
            problems.append(f"$.{key}: unknown property")
    for role, binding in doc["bindings"].items():
        where = f"$.bindings.{role}"
        _check(bool(_ROLE_RE.match(str(role))), problems,
               f"{where}: invalid role name")
        if not isinstance(binding, dict):
            problems.append(f"{where}: not an object")
            continue
        for key in binding:
            if key not in _BINDING_KEYS:
                problems.append(f"{where}.{key}: unknown property")
        _check(isinstance(binding.get("endpoint"), str)
               and bool(binding["endpoint"]), problems,
               f"{where}.endpoint: required endpoint id")
        _check(isinstance(binding.get("model"), str) and bool(binding["model"]),
               problems, f"{where}.model: required model id")
    degraded = doc.get("degraded_paths", {})
    _check(isinstance(degraded, dict), problems,
           "$.degraded_paths: must be an object when present")
    if isinstance(degraded, dict):
        for role, hops in degraded.items():
            where = f"$.degraded_paths.{role}"
            _check(bool(_ROLE_RE.match(str(role))), problems,
                   f"{where}: invalid role name")
            _check(isinstance(hops, list)
                   and all(isinstance(h, str) and h for h in hops), problems,
                   f"{where}: must be an array of hop strings")
    return problems


def validate_endpoints_doc(doc: dict) -> list[str]:
    """Schema violations for an endpoints document (empty list = valid)."""
    problems = _jsonschema_errors(doc, ENDPOINTS_SCHEMA)
    if problems is None:
        problems = _builtin_validate_endpoints(doc)
    else:
        # JSON Schema cannot express id uniqueness across items; check anyway.
        ids = [e.get("id") for e in doc.get("endpoints", []) if isinstance(e, dict)]
        for dup in sorted({i for i in ids if i is not None and ids.count(i) > 1}):
            problems.append(f"$.endpoints: duplicate endpoint id '{dup}'")
    return problems


def validate_bindings_doc(doc: dict) -> list[str]:
    """Schema violations for a bindings document (empty list = valid)."""
    problems = _jsonschema_errors(doc, BINDINGS_SCHEMA)
    if problems is None:
        problems = _builtin_validate_bindings(doc)
    return problems


def _referenced_endpoint_ids(bindings_doc: dict) -> list[tuple[str, str]]:
    """(where, endpoint_id) pairs referenced by bindings + degraded hops."""
    refs: list[tuple[str, str]] = []
    for role, binding in (bindings_doc.get("bindings") or {}).items():
        refs.append((f"bindings.{role}", binding.get("endpoint")))
    for role, hops in (bindings_doc.get("degraded_paths") or {}).items():
        for hop in hops:
            if isinstance(hop, str) and ":" in hop:
                refs.append((f"degraded_paths.{role}", hop.split(":", 1)[0]))
    return refs


def _check_endpoint_refs(bindings_doc: dict, endpoints_doc: dict) -> None:
    """Fail closed when a binding names an endpoint id that does not exist."""
    known = {e.get("id") for e in endpoints_doc.get("endpoints", [])
             if isinstance(e, dict)}
    for where, eid in _referenced_endpoint_ids(bindings_doc):
        if eid not in known:
            raise RegistryError(err(
                "registry.endpoint.missing",
                f"{where} references unknown endpoint id '{eid}'",
                {"where": where, "endpoint": eid},
            ))


# --------------------------------------------------------------------- io --

def _read_yaml(path: Path):
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, doc: dict, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)
    path.write_text(header + text, encoding="utf-8")


def load_endpoints() -> dict:
    """Load + schema-validate endpoints.yaml -> ``{endpoints: [...]}``.

    Missing file yields an empty registry. Invalid content raises
    RegistryError ``registry.validation.failed`` (fail-closed).
    """
    raw = _read_yaml(endpoints_path())
    doc = {"endpoints": []} if raw is None else raw
    problems = validate_endpoints_doc(doc)
    if problems:
        raise RegistryError(err(
            "registry.validation.failed",
            "endpoints.yaml failed schema validation",
            {"file": str(endpoints_path()), "issues": problems},
        ))
    return doc


def save_endpoints(doc: dict) -> None:
    problems = validate_endpoints_doc(doc)
    if problems:
        raise RegistryError(err(
            "registry.validation.failed",
            "endpoints document failed schema validation; not written",
            {"issues": problems},
        ))
    _write_yaml(endpoints_path(), doc, ENDPOINTS_HEADER)


def load_bindings() -> dict:
    """Load + validate bindings.yaml -> ``{bindings, degraded_paths}``.

    Fail-closed: schema violations raise ``registry.validation.failed`` and
    any reference to an unknown endpoint id raises ``registry.endpoint.missing``.
    """
    raw = _read_yaml(bindings_path())
    doc = {"bindings": {}, "degraded_paths": {}} if raw is None else raw
    problems = validate_bindings_doc(doc)
    if problems:
        raise RegistryError(err(
            "registry.validation.failed",
            "bindings.yaml failed schema validation",
            {"file": str(bindings_path()), "issues": problems},
        ))
    _check_endpoint_refs(doc, load_endpoints())
    return doc


def save_bindings(doc: dict) -> None:
    problems = validate_bindings_doc(doc)
    if problems:
        raise RegistryError(err(
            "registry.validation.failed",
            "bindings document failed schema validation; not written",
            {"issues": problems},
        ))
    _check_endpoint_refs(doc, load_endpoints())
    _write_yaml(bindings_path(), doc, BINDINGS_HEADER)


# -------------------------------------------------------------------- CRUD --

def _endpoint_index(doc: dict, endpoint_id: str) -> int | None:
    for i, ep in enumerate(doc.get("endpoints", [])):
        if ep.get("id") == endpoint_id:
            return i
    return None


def get_endpoint(endpoint_id: str) -> dict | None:
    doc = load_endpoints()
    idx = _endpoint_index(doc, endpoint_id)
    return doc["endpoints"][idx] if idx is not None else None


def add_endpoint(ep: dict) -> dict:
    """Append an endpoint entry; returns an ok/error envelope."""
    try:
        doc = load_endpoints()
    except RegistryError as e:
        return e.envelope
    if not isinstance(ep, dict):
        return err("registry.validation.failed", "endpoint entry must be an object")
    if _endpoint_index(doc, ep.get("id")) is not None:
        return err("registry.endpoint.exists",
                   f"endpoint id '{ep.get('id')}' already registered",
                   {"endpoint": ep.get("id")})
    candidate = dict(doc)
    candidate["endpoints"] = list(doc["endpoints"]) + [ep]
    problems = validate_endpoints_doc(candidate)
    if problems:
        return err("registry.validation.failed",
                   "endpoint entry failed schema validation",
                   {"issues": problems})
    save_endpoints(candidate)
    return {"ok": True, "result": ep}


def update_endpoint(endpoint_id: str, patch: dict) -> dict:
    """Shallow-merge ``patch`` into an existing endpoint entry."""
    try:
        doc = load_endpoints()
    except RegistryError as e:
        return e.envelope
    idx = _endpoint_index(doc, endpoint_id)
    if idx is None:
        return err("registry.endpoint.missing",
                   f"no endpoint id '{endpoint_id}'",
                   {"endpoint": endpoint_id})
    candidate = dict(doc)
    entries = [dict(e) for e in doc["endpoints"]]
    entries[idx].update(patch)
    candidate["endpoints"] = entries
    problems = validate_endpoints_doc(candidate)
    if problems:
        return err("registry.validation.failed",
                   "patched endpoint failed schema validation",
                   {"issues": problems})
    save_endpoints(candidate)
    return {"ok": True, "result": entries[idx]}


def delete_endpoint(endpoint_id: str, *, force: bool = False) -> dict:
    """Remove an endpoint; refuses while bindings still reference it."""
    try:
        doc = load_endpoints()
    except RegistryError as e:
        return e.envelope
    idx = _endpoint_index(doc, endpoint_id)
    if idx is None:
        return err("registry.endpoint.missing",
                   f"no endpoint id '{endpoint_id}'",
                   {"endpoint": endpoint_id})
    if not force:
        raw = _read_yaml(bindings_path()) or {}
        refs = [where for where, eid in _referenced_endpoint_ids(raw)
                if eid == endpoint_id]
        if refs:
            return err("registry.endpoint.bound",
                       f"endpoint '{endpoint_id}' still referenced by bindings.yaml",
                       {"endpoint": endpoint_id, "referenced_by": refs})
    candidate = dict(doc)
    candidate["endpoints"] = [e for e in doc["endpoints"]
                              if e.get("id") != endpoint_id]
    save_endpoints(candidate)
    return {"ok": True, "result": {"deleted": endpoint_id}}


def set_binding(role: str, endpoint: str, model: str) -> dict:
    """Bind ``role`` -> ``{endpoint, model}``; endpoint id must exist and must
    satisfy the role's declared capability requirement (US3/AC2, FR-006)."""
    try:
        endpoints = load_endpoints()
        idx = _endpoint_index(endpoints, endpoint)
        if idx is None:
            return err("registry.endpoint.missing",
                       f"cannot bind '{role}': unknown endpoint id '{endpoint}'",
                       {"role": role, "endpoint": endpoint})
        cap = endpoint_capable(endpoints["endpoints"][idx], role)
        if cap:
            return err("registry.binding.capability",
                       f"cannot bind '{role}' to '{endpoint}': {cap}",
                       {"role": role, "endpoint": endpoint,
                        "required": ROLE_REQUIREMENTS.get(role),
                        "capabilities":
                            endpoints["endpoints"][idx].get("capabilities", [])})
        if model not in endpoints["endpoints"][idx].get("models", []):
            return err("registry.binding.model",
                       f"cannot bind '{role}' to '{endpoint}': model "
                       f"'{model}' not in the endpoint's declared list",
                       {"role": role, "endpoint": endpoint, "model": model,
                        "models": endpoints["endpoints"][idx].get("models", [])})
        doc = load_bindings()
    except RegistryError as e:
        return e.envelope
    if not isinstance(role, str) or not _ROLE_RE.match(role):
        return err("registry.validation.failed",
                   f"invalid role name '{role}'", {"role": role})
    doc.setdefault("bindings", {})[role] = {"endpoint": endpoint, "model": model}
    save_bindings(doc)
    return {"ok": True,
            "result": {"role": role, "endpoint": endpoint, "model": model}}


if __name__ == "__main__":  # CLI shim: python -m runtime.registry (T065)
    from .__main__ import main

    raise SystemExit(main())
