"""Colony-health vitals sampling (feature 009 ext, FR-811).

Periodic health snapshots emitted as canonical ``colony.vitals`` /
``colony.sickness`` events so the improvement loop can diagnose
outcome-level defects — poor mood, repeat sickness per pawn-year,
multiple downed colonists, deaths — not just dispatch refusals.
Sampling is read-only; diagnosis and remediation stay pack-declared.
"""

from __future__ import annotations

ILLNESS_HEDIFFS = {
    "FoodPoisoning", "Flu", "Plague", "Infection", "Malaria",
    "SleepingSickness", "GutWorms", "MuscleParasites", "ToxicBuildup",
    "FibrousMechanites", "SensoryMechanites", "Malnutrition",
}


def _rpc(game, method: str, params: dict | None = None):
    try:
        r = game.rpc(method, params or {})
        return r.get("result") if r.get("ok") else None
    except Exception:
        return None


def _hediff_name(h) -> str:
    if isinstance(h, str):
        return h
    if isinstance(h, dict):
        return str(h.get("def") or h.get("defName") or h.get("label") or "")
    return str(h)


def sample(game, vstate: dict, cfg: dict) -> tuple[dict, list[dict]]:
    """Snapshot colony health -> (vitals payload, [new sickness payloads]).

    `vstate` persists per-pawn illness-hediff sets between samples so
    onsets are emitted once. `cfg` is the pack's ``vitals`` block;
    ``sickness_hediffs`` overrides the default illness classifier.
    """
    summary = _rpc(game, "state.summary") or {}
    pawns = _rpc(game, "state.pawns", {"filter": "colonists"}) or []
    moods = [float(p["mood"]) for p in pawns
             if isinstance(p.get("mood"), (int, float))]
    states = [p.get("state") for p in pawns]
    vitals = {
        "colonists": len(pawns) or len(summary.get("colonist_list") or []),
        "mood_avg": round(sum(moods) / len(moods)) if moods
                    else summary.get("mood_avg"),
        "mood_min": min(moods) if moods else None,
        "downed": sum(1 for s in states if s == "downed")
                  or summary.get("downed") or 0,
        "dead": sum(1 for s in states if s == "dead"),
    }
    illness = set(cfg.get("sickness_hediffs") or ILLNESS_HEDIFFS)
    prev = vstate.setdefault("hediffs", {})
    sick_events = []
    for p in pawns:
        pid = p.get("id") or p.get("name")
        if not pid or p.get("state") == "dead":
            continue
        detail = _rpc(game, "state.pawn", {"pawn": pid}) or {}
        cur = {_hediff_name(h) for h in (detail.get("hediffs") or [])}
        cur = {h for h in cur if h and (h in illness or
                                       h.replace(" ", "") in illness)}
        for h in sorted(cur - prev.get(pid, set())):
            sick_events.append({"pawn": pid, "hediff": h})
        prev[pid] = cur
    vitals["sick_now"] = sum(len(v) for v in prev.values())
    return vitals, sick_events
