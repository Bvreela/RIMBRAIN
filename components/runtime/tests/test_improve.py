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
