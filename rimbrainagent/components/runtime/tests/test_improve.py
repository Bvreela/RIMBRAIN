"""Improvement-cycle tests (feature 009; FR-801/803/808, SC-801/802)."""

from __future__ import annotations

import yaml

from runtime.improve import (diagnose, predict_metrics, run_improve,
                             score)

CFG = {
    "cadence": {"max_iterations": 5},
    "defect_patterns": [
        {"id": "repeated_refusal", "event_type": "action.refused",
         "group_by": "payload.template_id", "min_count": 2,
         "remediation": "fix_template_params"},
    ],
    "metrics": {"refusal_rate": 0.4, "verify_failure_rate": 0.3,
                "task_completion_rate": 0.3, "min_events": 5},
    "audit_gates": ["policy.invariant"],
    "promotion": {"episode_boundary_only": True},
}

PACK = {"schema_version": 0, "pack_id": "pack.test", "revision": "v1",
        "templates": [{"id": "broken", "method": "ui.job",
                       "params_schema": {}},
                      {"id": "good", "method": "ui.job",
                       "params_schema": {}}],
        "jobs": [], "decision_map": [], "emergency": []}


def _refusals(tid="broken", n=3):
    return [{"event_type": "action.refused", "sequence": i + 1,
             "payload": {"template_id": tid,
                         "error": {"code": "dispatch.params_invalid"}}}
            for i in range(n)]


def test_diagnose_finds_repeated_refusal():
    evs = _refusals() + [{"event_type": "action.issued",
                          "sequence": 9, "payload": {}}]
    f = diagnose(evs, CFG)
    assert len(f) == 1
    assert f[0]["defect_class"] == "repeated_refusal"
    assert f[0]["affected"] == ["broken"]
    assert f[0]["span"]["first_seq"] == 1


def test_diagnose_clean_history_noop():
    evs = [{"event_type": "action.issued", "sequence": 1,
            "payload": {}}]
    assert diagnose(evs, CFG) == []


def test_full_cycle_promotes_at_boundary(tmp_path):
    evs = _refusals(n=3) + \
        [{"event_type": "action.issued", "sequence": 10 + i,
          "payload": {"template_id": "good"}} for i in range(8)]
    out = []
    res = run_improve(None, CFG, active_pack=PACK,
                      packs_dir=tmp_path, sink=out.append, events=evs,
                      iterations=1)
    types = [e["event_type"] for e in out]
    assert "selfcheck.diagnosed" in types
    assert "audit.verdict" in types
    assert "improvement.promoted" in types
    promoted = next(e for e in out
                    if e["event_type"] == "improvement.promoted")
    assert promoted["payload"]["episode_boundary"] is True
    assert res["cycles"][0]["verdict"] == "promoted"
    # candidate actually materialized: 'broken' quarantined
    from pathlib import Path
    new_pack = yaml.safe_load(
        Path(res["cycles"][0]["pack"]).read_text())
    ids = [t["id"] for t in new_pack["templates"]]
    assert "broken" not in ids and "good" in ids


def test_thin_evidence_defers(tmp_path):
    out = []
    res = run_improve(None, CFG, active_pack=PACK,
                      packs_dir=tmp_path, sink=out.append,
                      events=_refusals(n=2), iterations=1)
    rej = [e for e in out
           if e["event_type"] == "improvement.rejected"]
    assert rej and rej[0]["payload"]["gate"] == "defer"
    assert res["cycles"][0]["verdict"] == "defer"


def test_unsafe_candidate_blocked_by_audit(tmp_path, monkeypatch):
    # candidate would contain a model executor -> audit must refuse
    import runtime.improve as imp
    monkeypatch.setattr(imp, "audit_policy",
                        lambda p: {"check_id": "policy.invariant",
                                   "domain": "policy", "verdict": "fail",
                                   "subject": str(p),
                                   "reasons": ["model executor"],
                                   "details": {}})
    out = []
    res = run_improve(None, CFG, active_pack=PACK,
                      packs_dir=tmp_path, sink=out.append,
                      events=_refusals() +
                      [{"event_type": "action.issued", "sequence": 9,
                        "payload": {}}] * 5,
                      iterations=1)
    rej = [e for e in out
           if e["event_type"] == "improvement.rejected"]
    assert rej[0]["payload"]["gate"] == "audit"
    assert res["cycles"][0]["verdict"] == "audit_fail"


def test_noop_cycle_invents_no_work(tmp_path):
    out = []
    res = run_improve(None, CFG, active_pack=PACK,
                      packs_dir=tmp_path, sink=out.append,
                      events=[{"event_type": "action.issued",
                               "sequence": 1, "payload": {}}],
                      iterations=2)
    diag = [e for e in out if e["event_type"] == "selfcheck.diagnosed"]
    assert all(e["payload"]["noop"] for e in diag)
    assert not list(tmp_path.rglob("cand-*.yaml"))


def test_predict_metrics_drops_quarantined():
    from runtime.metrics import episode_metrics
    evs = _refusals(n=4) + \
        [{"event_type": "action.issued", "sequence": 10 + i,
          "payload": {"template_id": "good"}} for i in range(6)]
    before = score(episode_metrics(evs), CFG["metrics"])
    cand = predict_metrics(evs, {"broken"})
    after = score(cand, CFG["metrics"])
    assert after < before
    assert cand["refusal_rate"] == 0.0


# --- FR-811/812/813: colony-health failure classes + mutation ops ---

YEAR = 3_600_000  # RimWorld game year in ticks

VITALS_CFG = {
    "defect_patterns": [
        {"id": "poor_mood", "event_type": "colony.vitals",
         "where": {"field": "payload.mood_min", "op": "lt", "value": 30},
         "group_by": "event_type", "min_count": 3,
         "remediation": {"ops": [
             {"op": "set_cfg", "path": "start.cooking.buffer",
              "value": 6}]}},
        {"id": "repeat_sickness", "event_type": "colony.sickness",
         "group_by": "payload.pawn", "window_ticks": YEAR,
         "min_count": 2,
         "remediation": {"ops": [
             {"op": "set_cfg", "path": "start.cooking.station_defs",
              "value": ["ElectricStove"]}]}},
        {"id": "multiple_downed", "event_type": "colony.vitals",
         "where": {"field": "payload.downed", "op": "gte", "value": 2},
         "group_by": "event_type", "min_count": 1,
         "remediation": {"ops": [
             {"op": "drop_rule", "ids": ["chase-fleeing"]}]}},
        {"id": "colonist_death", "event_type": "colony.vitals",
         "where": {"field": "payload.dead", "op": "gte", "value": 1},
         "group_by": "event_type", "min_count": 1,
         "remediation": {"ops": [
             {"op": "drop_rule", "ids": ["chase-fleeing"]}]}},
    ],
}

MUTABLE_PACK = dict(PACK, universal={"rules": [
    {"id": "chase-fleeing"}, {"id": "idle-work"}]},
                    start={"cooking": {"buffer": 2},
                           "recreation": {"defs": ["HorseshoesPin"]}})


def _vitals(tick=0, **kw):
    return {"event_type": "colony.vitals", "sequence": 1,
            "game_tick": tick, "payload": kw}


def test_diagnose_poor_mood_sustained():
    """mood_min < 30 across >=3 samples -> poor_mood finding."""
    evs = [_vitals(tick=t, mood_min=22) for t in (100, 200, 300)]
    findings = diagnose(evs, VITALS_CFG)
    assert any(f["defect_class"] == "poor_mood" for f in findings)
    # two samples only -> below min_count, no finding
    assert not diagnose(evs[:2], VITALS_CFG)


def test_diagnose_downed_and_death_single_sample():
    """multiple_downed + colonist_death fire on one bad sample."""
    evs = [_vitals(tick=50, downed=2, dead=1)]
    ids = {f["defect_class"] for f in diagnose(evs, VITALS_CFG)}
    assert {"multiple_downed", "colonist_death"} <= ids


def test_diagnose_repeat_sickness_windowed():
    """2 onsets per pawn inside a game year -> finding; spread apart -> none."""
    sick = lambda p, t: {"event_type": "colony.sickness", "sequence": 1,
                         "game_tick": t,
                         "payload": {"pawn": p, "hediff": "Flu"}}
    close = [sick("c0", 1000), sick("c0", 2000)]
    assert any(f["defect_class"] == "repeat_sickness"
               for f in diagnose(close, VITALS_CFG))
    far = [sick("c0", 1000), sick("c0", 1000 + YEAR + 1)]
    assert not any(f["defect_class"] == "repeat_sickness"
                   for f in diagnose(far, VITALS_CFG))
    # different pawns in-window -> not a per-pawn repeat
    other = [sick("c0", 1), sick("c1", 2)]
    assert not any(f["defect_class"] == "repeat_sickness"
                   for f in diagnose(other, VITALS_CFG))


def test_propose_mutation_ops(tmp_path):
    """FR-813: dict remediation applies declared ops to a candidate."""
    from runtime.improve import propose
    findings = [{"defect_class": "poor_mood", "affected": ["colony.vitals"],
                 "remediation": VITALS_CFG["defect_patterns"][0]["remediation"],
                 "count": 3, "span": {"first_seq": 1, "last_seq": 3}}]
    out = propose(findings, MUTABLE_PACK, tmp_path)
    cand = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert cand["start"]["cooking"]["buffer"] == 6
    assert cand["revision"].endswith("+mut.poor_mood")
    assert cand["templates"] == MUTABLE_PACK["templates"]  # untouched


def test_propose_drop_rule(tmp_path):
    from runtime.improve import propose
    findings = [{"defect_class": "multiple_downed",
                 "affected": ["colony.vitals"],
                 "remediation": VITALS_CFG["defect_patterns"][2]["remediation"],
                 "count": 1, "span": {"first_seq": 1, "last_seq": 1}}]
    out = propose(findings, MUTABLE_PACK, tmp_path)
    cand = yaml.safe_load(out.read_text(encoding="utf-8"))
    ids = [r["id"] for r in cand["universal"]["rules"]]
    assert "chase-fleeing" not in ids and "idle-work" in ids


def test_vitals_sample_emits_health_and_sickness_onsets():
    """FR-811: sampler builds vitals payload + once-per-onset sickness."""
    from runtime.vitals import sample

    class G:
        def __init__(self):
            self.sick = {"c0": ["Flu"]}
        def rpc(self, m, p=None):
            if m == "state.summary":
                return {"ok": True, "result": {"mood_avg": 40}}
            if m == "state.pawns":
                return {"ok": True, "result": [
                    {"id": "c0", "mood": 25},
                    {"id": "c1", "mood": 60, "downed": True},
                    {"id": "c2", "dead": True}]}
            if m == "state.pawn":
                pid = (p or {}).get("pawn")
                return {"ok": True, "result": {
                    "hediffs": [{"def": h} for h in self.sick.get(pid, [])]}}
            return {"ok": False}

    g, vstate = G(), {}
    v, evs = sample(g, vstate, {})
    assert v["mood_min"] == 25 and v["downed"] == 1 and v["dead"] == 1
    assert evs == [{"type": "colony.sickness",
                    "payload": {"pawn": "c0", "hediff": "Flu"}}]
    # same illness next sample -> not re-emitted; a new onset is
    v, evs = sample(g, vstate, {})
    assert evs == [] and v["sick_now"] == 1
    g.sick["c0"] = ["Flu", "FoodPoisoning"]
    v, evs = sample(g, vstate, {})
    assert evs == [{"type": "colony.sickness",
                    "payload": {"pawn": "c0", "hediff": "FoodPoisoning"}}]


def test_vitals_dead_via_roster_delta_and_fields():
    """Dead colonists leave FreeColonists -> absence counts as death."""
    from runtime.vitals import sample

    class G:
        def __init__(self, pawns, letters=()):
            self._pawns, self._letters = pawns, letters
        def rpc(self, m, p=None):
            if m == "state.summary":
                return {"ok": True, "result": {
                    "mood_avg": 40, "food_days": 0.8,
                    "threat_points": 500, "alerts": [{"label": "Starvation"}],
                    "key_stocks": {"MedicineIndustrial": 0},
                    "power": {"net_gain_w": -50},
                    "outside_storage": {"rotting": 7}}}
            if m == "state.pawns":
                return {"ok": True, "result": list(self._pawns)}
            if m == "state.pawn":
                return {"ok": True, "result": {
                    "hediffs": [], "needs": {"Rest": 10},
                    "break_thresholds": [35, 20, 5]}}
            if m == "state.letters":
                return {"ok": True, "result": list(self._letters)}
            if m == "map.find":
                return {"ok": True, "result": {"count": 6}}
            return {"ok": False}

    vstate = {}
    v, evs = sample(G([{"id": "c0", "mood": 20},
                     {"id": "c1", "mood": 30}],
                    letters=[{"id": 7, "def": "ThreatBig",
                              "label": "Raid", "tick": 99}]),
                    vstate, {})
    assert v["colonists"] == 2 and v["dead"] == 0
    assert v["food_days"] == 0.8 and v["threat_points"] == 500
    assert v["fires"] == 6 and v["power_net_w"] == -50
    assert v["medicine"] == 0 and v["rotting_outside"] == 7
    assert v["alerts"] == ["Starvation"]
    assert v["exhausted"] == 2  # Rest 10 < NEED_LOW on both
    assert evs == [{"type": "colony.letter", "payload": {
        "id": 7, "def": "ThreatBig", "label": "Raid", "tick": 99}}]
    # letter not re-emitted; c1 vanishes from roster -> dead
    v, evs = sample(G([{"id": "c0", "mood": 20}]), vstate, {})
    assert v["dead"] == 1 and evs == []


def test_propose_drop_rule_reaches_emergency_and_combat(tmp_path):
    from runtime.improve import propose
    pack = dict(PACK, emergency=[{"id": "fire-active"},
                                 {"id": "colonist-downed"}],
                combat={"engage": {"rules": [{"id": "chase-fleeing"},
                                             {"id": "draft-all"}]}})
    findings = [{"defect_class": "fire_rampant",
                 "affected": ["colony.vitals"],
                 "remediation": {"ops": [
                     {"op": "drop_rule",
                      "ids": ["fire-active", "chase-fleeing"]}]},
                 "count": 2, "span": {"first_seq": 1, "last_seq": 2}}]
    out = propose(findings, pack, tmp_path)
    cand = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert [r["id"] for r in cand["emergency"]] == ["colonist-downed"]
    assert [r["id"] for r in cand["combat"]["engage"]["rules"]] == \
        ["draft-all"]


def test_ops_candidate_promotes_on_metrics_tie(tmp_path):
    """FR-813: outcome-defect candidates can't move dispatch metrics —
    a tie (cand <= inc) promotes instead of metrics_fail."""
    cfg = dict(CFG)
    cfg["defect_patterns"] = VITALS_CFG["defect_patterns"][:1]  # poor_mood
    pack = dict(MUTABLE_PACK)
    evs = [_vitals(tick=t, mood_min=20) for t in (1, 2, 3)] + \
        [{"event_type": "action.issued", "sequence": 10 + i,
          "payload": {"template_id": "good"}} for i in range(6)]
    out = []
    res = run_improve(None, cfg, active_pack=pack, packs_dir=tmp_path,
                      sink=out.append, events=evs, iterations=1)
    assert res["cycles"][0]["verdict"] == "promoted"
    prom = [e for e in out if e["event_type"] == "improvement.promoted"]
    assert prom and prom[0]["payload"]["metrics"]["incumbent_score"] == \
        prom[0]["payload"]["metrics"]["candidate_score"]
