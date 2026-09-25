"""Public control API for the endpoint registry (feature 002, T070).

This facade is the ONLY runtime surface non-runtime components (dashboard,
tools, lab) should import — internals may move; these entry points are stable.
Every call returns the shared ``{ok,result|error}`` envelope or a plain
registry document; failures carry named codes (FR-009).

Adds the cross-cutting bits the internals don't own:

- probe-result cache (FR-005): ``probe()`` caches each result with its
  ``probed_utc``; ``probe_cached()`` serves last-known without a network call;
- duplicate ``base_url`` flagging (spec edge cases): ``list_endpoints()`` adds
  ``duplicates`` and ``add_endpoint`` warns instead of silently accepting;
- write-time capability gating via ``registry.set_binding`` (US3/AC2).
"""

from __future__ import annotations

from . import discover as _discover
from . import probe as _probe
from . import registry as _registry
from .bindings import resolve_role
from .client import openai_compat_chat, openai_compat_embed, systemone_decide
from .provenance import episode_manifest
from .registry import (RegistryError, delete_endpoint, err,
                       get_endpoint, load_bindings, save_bindings,
                       set_binding, update_endpoint)
from .usage import DEFAULT_TRACKER, UsageTracker

__all__ = [
    "RegistryError",
    "list_endpoints", "list_bindings", "duplicate_base_urls",
    "add_endpoint", "update_endpoint", "delete_endpoint", "get_endpoint",
    "bind_role", "resolve_role", "scan_local",
    "probe", "probe_cached", "probe_cache", "probe_live",
    "validate_pack_doc", "policy_vocabulary",
    "pin_bindings", "episode_manifest",
    "UsageTracker", "DEFAULT_TRACKER",
    "openai_compat_chat", "openai_compat_embed", "systemone_decide",
    "set_binding", "load_bindings", "save_bindings", "err",
]

# Last-known probe result per endpoint id (result embeds probed_utc, FR-005).
_PROBE_CACHE: dict[str, dict] = {}


def duplicate_base_urls() -> list[str]:
    """base_url values registered under more than one endpoint id."""
    seen: dict[str, int] = {}
    for ep in _registry.load_endpoints().get("endpoints", []):
        url = ep.get("base_url")
        if url:
            seen[url] = seen.get(url, 0) + 1
    return sorted(u for u, n in seen.items() if n > 1)


def list_endpoints() -> dict:
    """Registry document plus ``duplicates`` and last-known probe results."""
    doc = _registry.load_endpoints()
    doc["duplicates"] = duplicate_base_urls()
    doc["probes"] = {eid: r for eid, r in _PROBE_CACHE.items()
                     if any(ep.get("id") == eid
                            for ep in doc.get("endpoints", []))}
    return doc


def list_bindings() -> dict:
    return _registry.load_bindings()


def add_endpoint(ep: dict) -> dict:
    """Register an endpoint; warns (not rejects) on duplicate base_url."""
    res = _registry.add_endpoint(ep)
    if res.get("ok") and ep.get("base_url") in duplicate_base_urls():
        res["warning"] = f"duplicate base_url {ep['base_url']!r}"
    return res


def bind_role(role: str, endpoint: str, model: str) -> dict:
    """Write-time capability-gated binding (US3/AC2)."""
    res = _registry.set_binding(role, endpoint, model)
    if res.get("ok"):
        res["result"]["duplicates"] = duplicate_base_urls()
    return res


def scan_local() -> list[dict]:
    return _discover.scan_local()


def pin_bindings(*, probe_live: bool = False) -> dict:
    """Frozen per-role resolution snapshot (FR-008/US5).

    Scored episodes pin at start: resolutions recorded now are the ones the
    episode must use — ``resolve_role(role, pinned=snapshot)`` resolves from
    the snapshot, so a mid-episode ``set_binding`` cannot alter the run.
    """
    return episode_manifest(probe_live=probe_live)


def probe(endpoint_id: str, *, fresh: bool = True) -> dict:
    """Probe an endpoint; caches the result (fresh or failed) with probed_utc."""
    if not fresh and endpoint_id in _PROBE_CACHE:
        return {**_PROBE_CACHE[endpoint_id], "cached": True}
    res = _probe.probe_endpoint(endpoint_id)
    if "probed_utc" not in res:
        res = {**res, "probed_utc": _utcnow()}
    _PROBE_CACHE[endpoint_id] = res
    return res


def probe_cached(endpoint_id: str) -> dict:
    """Last-known probe result without touching the network."""
    if endpoint_id not in _PROBE_CACHE:
        return err("probe.no_cache",
                   f"no cached probe result for '{endpoint_id}'",
                   {"endpoint": endpoint_id}, retryable=True)
    return {**_PROBE_CACHE[endpoint_id], "cached": True}


def probe_cache() -> dict:
    """The live probe-result cache keyed by endpoint id."""
    return _PROBE_CACHE


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- feature 018: guided launcher facade entries (contracts/probe-live.md) --

def probe_live(role: str, *, timeout_s: int = 10) -> dict:
    """Role-shaped live verification — resolves the role's binding
    offline, then runs one real call against the bound model shaped by
    its required capability. See probe.probe_live for verdicts."""
    return _probe.probe_live(role, timeout_s=timeout_s)


def validate_pack_doc(doc: dict) -> dict:
    """Loader-identical pack validation as a pure function — the same
    sequence ``templates.load_pack`` applies after parsing (migrate →
    schema → sealed-inventory methods → policy audit) with no file I/O.
    ``{ok: True, issues: []}`` or ``{ok: False, issues: [...]}``."""
    from . import templates as _t
    if not isinstance(doc, dict):
        return {"ok": False, "issues": ["$: pack must be an object"]}
    sv = doc.get("schema_version") or 0
    try:
        sv = int(sv)
    except (TypeError, ValueError):
        return {"ok": False,
                "issues": [f"$.schema_version: {sv!r} not an integer"]}
    if sv > 1:
        return {"ok": False,
                "issues": [f"$.schema_version: {sv} > 1"]}
    d = _t.migrate_v0(doc)
    issues = list(_t.validate_pack(d))
    inv = _t.inventory_methods()
    for i, t in enumerate(_t.templates_of(d)):
        m = t.get("method") if isinstance(t, dict) else None
        if m and m not in inv:
            issues.append(
                f"$.templates[{i}].method: '{m}' not in bridge inventory")
    if d.get("policy_version") is not None:
        from .policy import validate_policy
        issues += validate_policy(d)
    return {"ok": not issues, "issues": issues[:25]}


def policy_vocabulary() -> dict:
    """Pack-dialect vocabulary for guided editing — sourced from
    policy.py (authoritative); callers never duplicate the table."""
    from . import policy as _p
    return {"ok": True,
            "ops": list(_p._OPS),
            "combinators": ["all", "any", "not"],
            "functions": sorted(_p.FN),
            "resolvers": ["@cfg:", "@obs:", "@var:"]}
