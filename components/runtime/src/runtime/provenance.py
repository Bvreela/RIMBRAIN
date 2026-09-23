"""Episode model provenance (feature 002; FR-008, SC-004, US5).

The per-role endpoint+model(+revision) resolved at episode start is recorded
in the run manifest so two runs with different bindings produce distinguishable
manifests and replay/eval comparability holds (UR-MOD-016).
"""

from __future__ import annotations

from . import registry
from .bindings import resolve_role


def episode_manifest(episode_id: str | None = None,
                     *, probe_live: bool = False,
                     usage: dict | None = None) -> dict:
    """Deterministic per-role resolution manifest.

    ``{schema_version, episode_id?, roles: {role: {endpoint_id|kind, model|name,
    api?, degraded, revision?}}, usage?}`` — sorted keys, no secrets, no
    timestamps (timestamp belongs to the episode envelope that embeds this).
    ``usage`` is a ``UsageTracker.snapshot()`` folded in when supplied (US5).
    """
    bdoc = registry.load_bindings()
    roles: dict = {}
    for role in sorted((bdoc.get("bindings") or {}).keys()):
        res = resolve_role(role, probe_live=probe_live)
        entry: dict = {"degraded": res.get("degraded", True)}
        resolved = res.get("resolved")
        if res["ok"] and resolved:
            if "endpoint_id" in resolved:
                entry.update({"endpoint_id": resolved["endpoint_id"],
                              "model": resolved["model"],
                              "api": resolved.get("api")})
            else:
                entry.update({"kind": resolved["kind"],
                              "name": resolved["name"]})
        else:
            entry["error"] = res["error"]["code"]
        roles[role] = entry
    manifest = {"schema_version": 0, "roles": roles}
    if usage:
        manifest["usage"] = {str(k): dict(v) for k, v in sorted(usage.items())}
    if episode_id:
        manifest["episode_id"] = episode_id
    return manifest
