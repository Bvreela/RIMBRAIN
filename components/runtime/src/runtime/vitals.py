"""Colony-health vitals sampling (feature 009 ext, FR-811).

Periodic health snapshots emitted as canonical ``colony.vitals`` /
``colony.sickness`` / ``colony.letter`` events so the improvement loop
can diagnose outcome-level defects — poor mood, repeat sickness per
pawn-year, starvation, mass downed, deaths, outbreaks, incident letters —
not just dispatch refusals. Sampling is read-only; diagnosis and
remediation stay pack-declared.
"""

from __future__ import annotations

ILLNESS_HEDIFFS = {
    "FoodPoisoning", "Flu", "Plague", "Infection", "Malaria",
    "SleepingSickness", "GutWorms", "MuscleParasites", "ToxicBuildup",
    "FibrousMechanites", "SensoryMechanites", "Malnutrition",
    "Hypothermia", "Heatstroke",
}

# needs below these percentages count as deprivation signals
NEED_LOW = 15


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


def _pawn_down(p: dict) -> bool:
    # PawnBrief emits `downed`/`dead` bools + `job` text; older shapes used
    # a `state` string — accept all three so the field is real.
    return bool(p.get("downed")) or p.get("state") == "downed" \
        or p.get("job") == "downed"


def _pct(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def sample(game, vstate: dict, cfg: dict) -> tuple[dict, list[dict]]:
    """Snapshot colony health -> (vitals payload, events).

    `events` are ``{"type": ..., "payload": ...}`` dicts the caller emits:
    one ``colony.sickness`` per new illness onset per pawn, one
    ``colony.letter`` per unseen game letter. `vstate` persists hediff
    sets, the known roster (dead pawns leave ``FreeColonists`` — absence
    is the death signal), and seen letter ids between samples.
    """
    summary = _rpc(game, "state.summary") or {}
    pawns = _rpc(game, "state.pawns", {"filter": "colonists"}) or []
    moods = [_pct(p.get("mood")) for p in pawns]
    moods = [m for m in moods if m is not None]
    downed = sum(1 for p in pawns if _pawn_down(p)) \
        or summary.get("downed") or 0
    colonists = len(pawns) or len(summary.get("colonist_list") or [])

    # death detection: `dead` flags on present pawns plus roster delta —
    # corpses leave FreeColonists, so a pawn that vanishes is dead
    roster = vstate.setdefault("roster", set())
    dead_ids = vstate.setdefault("dead_ids", set())
    seen = {p.get("id") or p.get("name") for p in pawns} - {None}
    for p in pawns:
        if p.get("dead") or p.get("state") == "dead":
            pid = p.get("id") or p.get("name")
            if pid:
                dead_ids.add(pid)
    dead_ids |= (roster - seen)
    roster |= seen
    vitals = {
        "colonists": colonists,
        "mood_avg": round(sum(moods) / len(moods)) if moods
                    else summary.get("mood_avg"),
        "mood_min": min(moods) if moods else None,
        "downed": downed,
        "dead": len(dead_ids),
        "all_downed": colonists > 0 and downed >= colonists,
    }

    # --- per-pawn detail: illness onsets + needs/threshold signals ---
    illness = set(cfg.get("sickness_hediffs") or ILLNESS_HEDIFFS)
    prev = vstate.setdefault("hediffs", {})
    events: list[dict] = []
    counts = {"bleeding": 0, "needs_tending": 0, "in_mental_state": 0,
              "extreme_risk": 0, "exhausted": 0, "bored": 0, "starving": 0}
    for p in pawns:
        pid = p.get("id") or p.get("name")
        if not pid or p.get("dead") or p.get("state") == "dead":
            continue
        counts["bleeding"] += bool(p.get("bleeding"))
        counts["needs_tending"] += bool(p.get("needs_tending"))
        counts["in_mental_state"] += bool(p.get("mental_state"))
        detail = _rpc(game, "state.pawn", {"pawn": pid}) or {}
        cur = {_hediff_name(h) for h in (detail.get("hediffs") or [])}
        cur = {h for h in cur if h and (h in illness or
                                       h.replace(" ", "") in illness)}
        for h in sorted(cur - prev.get(pid, set())):
            events.append({"type": "colony.sickness",
                           "payload": {"pawn": pid, "hediff": h}})
        prev[pid] = cur
        needs = detail.get("needs") or {}
        thr = detail.get("break_thresholds") or []
        if len(thr) >= 3 and _pct(needs.get("Mood")) is not None \
                and needs["Mood"] < thr[2]:
            counts["extreme_risk"] += 1
        if (_pct(needs.get("Rest")) or 100) < NEED_LOW:
            counts["exhausted"] += 1
        if (_pct(needs.get("Recreation")) or 100) < NEED_LOW:
            counts["bored"] += 1
        if (_pct(needs.get("Food")) or 100) < 10 or "Malnutrition" in cur:
            counts["starving"] += 1
    vitals.update(counts)
    vitals["sick_now"] = sum(len(v) for v in prev.values())

    # --- colony-scale passthrough fields (all already in state.summary) ---
    stocks = summary.get("key_stocks") or {}
    power = summary.get("power") or {}
    outside = summary.get("outside_storage") or {}
    vitals.update({
        "food_days": summary.get("food_days"),
        "nutrition": summary.get("nutrition"),
        "threat_points": summary.get("threat_points"),
        "hostiles": len(summary.get("hostiles") or []),
        "prisoners": summary.get("prisoners") or 0,
        "temp_outdoor": summary.get("temp_outdoor"),
        "season": summary.get("season"),
        "growing_now": summary.get("growing_now"),
        "power_net_w": power.get("net_gain_w"),
        "power_stored_wd": power.get("stored_wd"),
        "medicine": sum(stocks.get(k) or 0 for k in
                        ("MedicineHerbal", "MedicineIndustrial",
                         "MedicineUltratech")),
        "rotting_outside": outside.get("rotting") or 0,
        "alerts": [a.get("label") for a in (summary.get("alerts") or [])
                   if a.get("label")],
        "fires": (_rpc(game, "map.find", {"def": "Fire"}) or {})
                 .get("count") or 0,
    })

    # --- new letters -> colony.letter events (diff by id) ---
    letters_seen = vstate.setdefault("letters", set())
    for l in _rpc(game, "state.letters") or []:
        lid = l.get("id")
        if lid is None or lid in letters_seen:
            continue
        letters_seen.add(lid)
        events.append({"type": "colony.letter",
                       "payload": {"id": lid, "def": l.get("def"),
                                   "label": l.get("label"),
                                   "tick": l.get("tick")}})
    return vitals, events
