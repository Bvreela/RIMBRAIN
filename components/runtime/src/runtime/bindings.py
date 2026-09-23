"""Role resolution + capability gating (feature 002; FR-003/FR-006, US2/US3).

``resolve_role(role)`` resolves a role's primary binding, capability-gates it,
and on failure walks ``degraded_paths`` in order. Hop grammar:

- ``<endpoint_id>:<model>`` — try that endpoint+model (probe-gated);
- bare sentinel — terminal non-endpoint fallback resolved as
  ``{kind: "fallback", name}`` (rules, rules-only, skip, lexical-bm25, ...).

Fail-closed: a role with no usable resolution reports ``resolved: null`` with
the first failure reason — never a silent call (UR-MOD-017).
"""

from __future__ import annotations

from . import registry
from .registry import err

# Capability a role requires of its endpoint (FR-006); canonical table lives in
# registry so write-time gating (set_binding) shares it without an import cycle.
ROLE_REQUIREMENTS = registry.ROLE_REQUIREMENTS
_SENTINELS = {"rules", "rules-only", "skip", "lexical-bm25"}


def _capable(endpoint: dict, role: str) -> str | None:
    """Named error when endpoint lacks the role's required capability."""
    return registry.endpoint_capable(endpoint, role)


def _hop(endpoint_id: str, model: str, role: str,
         endpoints_doc: dict) -> dict | None:
    ep = next((e for e in endpoints_doc["endpoints"]
               if e.get("id") == endpoint_id), None)
    if ep is None:
        return None
    cap_err = _capable(ep, role)
    if cap_err:
        return {"ok": False, "why": f"capability: {cap_err}",
                "endpoint": endpoint_id, "model": model}
    if model not in ep.get("models", []):
        return {"ok": False, "why": f"model '{model}' not in endpoint's list",
                "endpoint": endpoint_id, "model": model}
    return {"ok": True, "resolved": {"endpoint_id": endpoint_id,
                                     "model": model, "api": ep["api"]}}


def resolve_role(role: str, *, probe_live: bool = False,
                 pinned: dict | None = None) -> dict:
    """Resolve ``role`` to ``{resolved, degraded, reason, tried}``.

    With ``probe_live`` each candidate is probed before acceptance (fail-closed
    on unreachable/incapable); offline resolution checks registry facts only.

    ``pinned`` is a snapshot from ``api.pin_bindings()`` (FR-008/US5): when
    given, resolution comes solely from the snapshot — mid-episode
    ``set_binding`` cannot alter what a scored run resolves to.
    """
    if pinned is not None:
        roles = (pinned.get("roles") or {})
        if role not in roles:
            return err("bindings.unresolved",
                       f"role '{role}' not in pinned snapshot",
                       {"role": role, "pinned_roles": sorted(roles)})
        entry = roles[role]
        if "error" in entry:
            return err("bindings.unresolved",
                       f"role '{role}' unresolved at pin time",
                       {"role": role, "error": entry["error"]})
        resolved = ({"kind": entry["name"], "name": entry["name"]}
                    if "kind" in entry
                    else {"endpoint_id": entry["endpoint_id"],
                          "model": entry["model"], "api": entry.get("api")})
        return {"ok": True, "resolved": resolved,
                "degraded": bool(entry.get("degraded")), "reason": "pinned",
                "tried": [], "pinned": True}
    try:
        bdoc = registry.load_bindings()
        edoc = registry.load_endpoints()
    except registry.RegistryError as exc:
        return exc.envelope

    tried: list[dict] = []
    binding = (bdoc.get("bindings") or {}).get(role)

    def _accept(hop: dict) -> bool:
        if not probe_live:
            return True
        from .probe import probe_endpoint
        p = probe_endpoint(hop["resolved"]["endpoint_id"])
        if p["ok"]:
            return True
        hop["ok"] = False
        hop["why"] = f"probe: {p['error']['code']}"
        return False

    if binding:
        hop = _hop(binding["endpoint"], binding["model"], role, edoc)
        if hop and hop["ok"]:
            tried.append(hop)
            if _accept(hop):
                return {"ok": True, "resolved": hop["resolved"],
                        "degraded": False, "reason": "primary", "tried": tried}
        elif hop:
            tried.append(hop)

    for hop_str in (bdoc.get("degraded_paths") or {}).get(role, []):
        if ":" in hop_str:
            eid, model = hop_str.split(":", 1)
            hop = _hop(eid, model, role, edoc)
            if hop is None:
                tried.append({"ok": False, "why": f"unknown endpoint '{eid}'",
                              "endpoint": eid})
                continue
            tried.append(hop)
            if hop["ok"] and _accept(hop):
                return {"ok": True, "resolved": hop["resolved"],
                        "degraded": True, "reason": f"degraded:{hop_str}",
                        "tried": tried}
        else:
            tried.append({"ok": True, "sentinel": hop_str})
            return {"ok": True,
                    "resolved": {"kind": "fallback", "name": hop_str},
                    "degraded": True, "reason": f"fallback:{hop_str}",
                    "tried": tried}

    first_fail = next((t for t in tried if not t.get("ok")), None)
    return err(
        "bindings.unresolved",
        f"role '{role}': no usable endpoint"
        + (f" ({first_fail['why']})" if first_fail else " (no binding)"),
        {"role": role, "tried": tried},
    )
