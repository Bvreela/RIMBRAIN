"""Reflection-pipeline tests (feature 017 US4; ex-test_mutate).

Unit tests drive evolve.py directly; the integration tests run

Unit tests drive evolve.py directly; the integration tests run
``run(live_mutate=True)`` against StartSim with the packs dir and
state dir redirected to tmp (monkeypatched env), so candidate/lineage
writes never touch the repo or a real pack file.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import evolve, packmut, templates  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402

from test_phase import StartSim  # noqa: E402
from runtime.loop import run  # noqa: E402


def _env(t, payload, seq=1):
    return {"schema_version": 0, "event_id": f"e-{seq}",
            "sequence": seq, "event_type": t, "payload": payload,
            "game_tick": 1, "wall_time_utc": "t", "source": "test"}


def _transition(tid, to_state, seq=1):
    return _env("task.transition",
                {"task_id": tid, "to_state": to_state}, seq)


MINI = {
    "schema_version": 0, "pack_id": "pack.mini", "revision": "v0",
    "templates": [{"id": "ping", "method": "game.status",
                   "params_schema": {}}],
    "jobs": [], "decision_map": [], "emergency": [],
    "govern": {"goals": [{"id": "keep", "retry_polls": 5,
                          "effect": {"field": "x"}, "steps": []}]},
    "mutate": {"goals_per_pass": 3, "on_failure": True,
               "near_failure": {"requeues": 2, "refusals": 3,
                                "blocked_polls": 2, "escalate": True},
               "cooldown_polls": 5, "max_passes_per_run": 4,
               "max_ops": 5},
}


def _loaded(pack=None):
    pack = pack or MINI
    return {"pack": pack, "hash": templates._hash_of(pack),
            "path": "mini.yaml"}


# mutation ops target the v1 surface — gate inputs are migrated docs
MINI_V1 = templates.migrate_v0(MINI)


def _stub_dispatcher(pack=None):
    d = Dispatcher(None, clock=lambda: "2026-01-01T00:00:00Z")
    d._pack = _loaded(pack)
    d._pack_file = "mini"
    return d


class _Ledger:
    def __init__(self):
        self.tasks = {}
        self._events = 0


def _resolver_endpoint(name, **kw):
    return {"ok": True,
            "resolved": {"endpoint_id": "test-ep", "model": "m-test",
                         "api": "openai-compat"},
            "degraded": False, "tried": []}


def _resolver_rules(name, **kw):
    return {"ok": True,
            "resolved": {"kind": "fallback", "name": "rules-only"},
            "degraded": True, "reason": "fallback", "tried": []}


def _resolver_broken(name, **kw):
    return {"ok": False, "error": {"code": "bindings.unresolved",
                                   "message": "no role"}}


def _chat_ok(endpoint_id, model, messages, usage_tracker=None):
    return {"ok": True, "body": {
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "choices": [{"message": {"content": json.dumps({
            "mutation_id": "mut.test-bump",
            "analysis": {"failure_paths": ["govern.keep stalling"],
                         "likely_paths": ["repeat refusals"]},
            "mutations": [{"op": "set",
                           "path": "govern.goals.keep.retry_polls",
                           "value": 9}],
            "rationale": "longer backoff"})}}]}}


def _chat_bad(endpoint_id, model, messages, usage_tracker=None):
    return {"ok": True, "body": {
        "choices": [{"message": {"content": "not json at all"}}]}}


def _chat_broken(*a, **kw):
    return {"ok": False, "error": {"code": "endpoint.down",
                                   "message": "offline"}}


def _maybe(ps, dispatcher=None, ledger=None, pack=None, poll=10,
           state_dir=None, emit=None, **kw):
    pack = templates.migrate_v0(pack or MINI)  # gate input = loaded doc
    state_dir = state_dir or Path.cwd()
    return evolve.maybe_trigger(
        ps, dispatcher=dispatcher or _stub_dispatcher(pack),
        ledger=ledger or _Ledger(),
        pack_loaded=_loaded(pack), pack=pack, pack_id="mini",
        state_dir=state_dir, tick=1, poll=poll, fair=False,
        emit=emit or (lambda e: None), **kw)


# -- triggers -----------------------------------------------------------------

def test_cadence_fires_after_n_terminal_goals():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    for i in range(2):
        ps.note(_transition(f"govern.g{i}", "succeeded", i))
    assert evolve.check_triggers(ps, MINI, poll=10) == (None, {})
    ps.note(_transition("govern.g2", "succeeded", 3))
    reason, ev = evolve.check_triggers(ps, MINI, poll=10)
    assert reason == "cadence" and ev["terminal_goals"] == 3


def test_failure_trigger_immediate():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    reason, ev = evolve.check_triggers(ps, MINI, poll=1)
    assert reason == "failure" and ev["tasks"] == ["govern.keep"]


def test_non_goal_transitions_do_not_count():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    for i in range(5):
        ps.note(_transition("misc.x", "failed", i))
    assert evolve.check_triggers(ps, MINI, poll=10) == (None, {})


def test_near_failure_requeue_burst():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = evolve.PassState(cfg)
    ps.note(_transition("govern.keep", "requeued", 1))
    ps.note(_transition("govern.keep", "requeued", 2))
    reason, ev = evolve.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and ev["requeued"]


def test_near_failure_refusal_burst_and_blocked():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = evolve.PassState(cfg)
    for i in range(3):
        ps.note(_env("action.refused",
                     {"template_id": "t", "error": {"code": "x"}}, i))
    reason, ev = evolve.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and len(ev["refusals"]) == 3

    ps2 = evolve.PassState(cfg)
    ps2.note_outcome({"state": "blocked"})
    ps2.note_outcome({"state": "blocked"})
    reason, ev = evolve.check_triggers(ps2, MINI, poll=10)
    assert reason == "near_failure" and ev["blocked_polls"] == 2
    ps2.note_outcome({"state": "ok"})
    assert ps2.blocked_run == 0


def test_cooldown_and_pass_budget():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.last_pass_poll = 9           # cooldown_polls=5 -> poll 10 blocked
    ps.note(_transition("govern.keep", "failed"))
    assert evolve.check_triggers(ps, MINI, poll=10) == (None, {})
    reason, _ = evolve.check_triggers(ps, MINI, poll=15)
    assert reason == "failure"
    ps.passes = 4                   # max_passes_per_run=4 -> hard stop
    ps.last_pass_poll = -10**9
    assert evolve.check_triggers(ps, MINI, poll=30) == (None, {})


def test_no_mutate_section_no_triggers():
    ps = evolve.PassState({})
    ps.note(_transition("govern.keep", "failed"))
    assert evolve.check_triggers(ps, MINI, poll=10) == (None, {})


def test_escalate_counts_decision_rows():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = evolve.PassState(cfg)
    ps.note_decisions([{"source": "govern.keep:escalate", "ok": True}])
    reason, ev = evolve.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and ev["escalations"] == 1


# -- digest --------------------------------------------------------------------

def test_digest_bounded_and_grounded():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    ledger = _Ledger()
    ledger.tasks = {"govern.keep": {"state": "failed", "attempts": 2}}
    d = evolve.build_digest(ps, ledger, _loaded(), MINI,
                            "failure", {"tasks": ["govern.keep"]}, 1, 2)
    assert d["pack"]["hash"] == _loaded()["hash"]
    assert d["goals"][0]["id"] == "govern.keep"
    assert d["goals"][0]["spec"]["retry_polls"] == 5
    assert len(json.dumps(d)) < 8000


# -- reflect -------------------------------------------------------------------

def test_reflect_model_proposal_accepted():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_ok)
    assert r["ok"] and r["proposal"]["mutation_id"] == "mut.test-bump"
    assert r["proposal"]["base_revision"] == _loaded()["hash"]
    assert r["usage"]["prompt_tokens"] == 10


def test_reflect_malformed_output_rejected():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_bad)
    assert not r["ok"] and not r.get("degraded")
    assert r["violations"]


def test_reflect_endpoint_down_is_degraded():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_broken)
    assert not r["ok"] and r["degraded"]


def test_reflect_unresolved_role_is_degraded():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_broken, chat=_chat_ok)
    assert not r["ok"] and r["degraded"]
    assert r["error"]["code"] == "evolve.unresolved"


def test_reflect_rules_only_applies_declared_remediation():
    """rules-only fallback: the improve pack's defect-pattern remediation
    becomes the proposal — compiled to packmut ops."""
    pack = copy.deepcopy(MINI)
    pack["improve"] = {"defect_patterns": [{
        "id": "refusal-burst", "event_type": "action.refused",
        "group_by": "payload.template_id", "min_count": 1,
        "remediation": {"ops": [{"op": "set_cfg",
                                 "path": "govern.goals.keep.retry_polls",
                                 "value": 7}]}}]}
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_env("action.refused", {"template_id": "ping"}))
    r = evolve.reflect(ps, {}, _loaded(pack), pack, "near_failure",
                       resolver=_resolver_rules, chat=_chat_broken)
    assert r["ok"] and r["degraded"]
    assert r["proposal"]["mutations"] == [
        {"op": "set", "path": "govern.goals.keep.retry_polls",
         "value": 7}]


def test_reflect_rules_only_no_findings_degrades():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_rules, chat=_chat_broken)
    assert not r["ok"] and r["degraded"]
    assert r["error"]["code"] == "evolve.rules_only_noop"


def _chat_429(*a, **kw):
    return {"ok": False, "error": {"code": "client.http",
                                   "message": "HTTP 429 from x",
                                   "retryable": True,
                                   "details": {"status": 429}}}


def test_reflect_endpoint_429_reports_status_and_identity():
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    r = evolve.reflect(ps, {}, _loaded(), MINI, "near_failure",
                       resolver=_resolver_endpoint, chat=_chat_429)
    assert not r["ok"] and r["degraded"]
    assert r["status"] == 429 and r["retryable"]
    assert r["endpoint_id"] == "test-ep" and r["model"] == "m-test"


def test_reflect_endpoint_down_uses_declared_remediation():
    """Endpoint error still yields a (degraded) proposal when a pack
    defect-pattern remediation compiles — the pass does useful work."""
    pack = copy.deepcopy(MINI)
    pack["improve"] = {"defect_patterns": [{
        "id": "refusal-burst", "event_type": "action.refused",
        "group_by": "payload.template_id", "min_count": 1,
        "remediation": {"ops": [{"op": "set_cfg",
                                 "path": "govern.goals.keep.retry_polls",
                                 "value": 7}]}}]}
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_env("action.refused", {"template_id": "ping"}))
    r = evolve.reflect(ps, {}, _loaded(pack), pack, "near_failure",
                       resolver=_resolver_endpoint, chat=_chat_429)
    assert r["ok"] and r["degraded"]
    assert r["endpoint_error"] == "HTTP 429 from x"
    assert r["proposal"]["mutations"] == [
        {"op": "set", "path": "govern.goals.keep.retry_polls",
         "value": 7}]


def test_degraded_streak_backs_off_cooldown():
    """Consecutive degraded passes multiply cooldown (x2..x16)."""
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["cooldown_polls"] = 10
    ps = evolve.PassState(cfg)
    ps.last_pass_poll = 100
    ps.degraded_streak = 2              # cooldown -> 40
    ps.passes = 1
    # a firing trigger inside the extended window stays suppressed
    ps.note(_transition("govern.keep", "failed", seq=1))
    assert evolve.check_triggers(ps, MINI, 110) == (None, {})  # 10 < 40
    reason, ev = evolve.check_triggers(ps, MINI, 141)
    assert reason == "failure" and ev["tasks"] == ["govern.keep"]


def test_maybe_trigger_degraded_event_carries_diagnostics(tmp_path):
    events = []

    def emit(e):
        events.append(e)

    cfg = copy.deepcopy(MINI["mutate"])
    ps = evolve.PassState(cfg)
    ps.note(_env("action.refused", {"template_id": "ping"}, 1))
    ps.note(_env("action.refused", {"template_id": "ping"}, 2))
    ps.note(_env("action.refused", {"template_id": "ping"}, 3))
    _maybe(ps, poll=10, state_dir=tmp_path, emit=emit,
           resolver=_resolver_endpoint, chat=_chat_429)
    deg = next(e for e in events if e["event_type"] == "mutation.degraded")
    p = deg["payload"]
    assert p["reason"] == "near_failure"
    assert p["status"] == 429 and p["retryable"]
    assert p["endpoint_id"] == "test-ep" and p["model"] == "m-test"
    assert p["streak"] == 1 and p["action"] == "no change applied"
    assert "ping" in p["evidence"]["refusals"]
    trig = next(e for e in events
                if e["event_type"] == "mutation.triggered")
    assert trig["payload"]["evidence"]["refusals"]


# -- gate ------------------------------------------------------------------------

def _proposal(ops, pack=None):
    pack = pack or MINI
    return {"schema_version": 0, "mutation_id": "mut.t",
            "base_revision": templates._hash_of(pack),
            "analysis": {"failure_paths": [], "likely_paths": []},
            "mutations": ops, "rationale": "r"}


def test_gate_full_pack_ops_apply():
    ops = [
        {"op": "set", "path": "govern.goals.keep.retry_polls",
         "value": 9},
        {"op": "upsert", "path": "govern.goals",
         "value": {"id": "new-goal", "retry_polls": 1,
                   "effect": {"field": "y"}, "steps": []}},
        {"op": "append", "path": "emergency",
         "value": {"id": "er", "priority": 1,
                   "when": {"field": "x", "op": "gte", "value": 1},
                   "action": {"template_id": "ping", "params": {}}}},
        {"op": "set", "path": "decide.select.cadence_polls",
         "value": 3},
    ]
    g = evolve.gate(_proposal(ops, MINI_V1), _loaded(MINI_V1), MINI_V1,
                    MINI["mutate"], fair=False)
    assert g["ok"], g
    doc = g["doc"]
    # v0 ops rewrote onto the v1 surfaces
    assert doc["standing_goals"][0]["retry_polls"] == 9
    assert any(g2["id"] == "new-goal" for g2 in doc["standing_goals"])
    assert doc["reflexes"][0]["id"] == "er"
    assert doc["decide"]["select"]["cadence_polls"] == 3


def test_gate_remove_ops():
    pack = copy.deepcopy(MINI)
    pack["universal"] = {"rules": [{"id": "bad-rule", "when": {},
                                    "steps": []}]}
    pack_v1 = templates.migrate_v0(pack)
    ops = [{"op": "remove", "path": "universal.rules.bad-rule"},
           {"op": "remove", "path": "govern.goals.keep"}]
    g = evolve.gate(_proposal(ops, pack_v1), _loaded(pack_v1), pack_v1,
                    MINI["mutate"], fair=False)
    assert g["ok"]
    assert g["doc"]["rules"] == []
    assert g["doc"]["standing_goals"] == []


def test_gate_rejects_budget_stale_vacuous_miss():
    ld = _loaded(MINI_V1)
    many = [{"op": "set", "path": f"senses.govern.k{i}", "value": i}
            for i in range(6)]   # > max_ops 5
    g = evolve.gate(_proposal(many, MINI_V1), ld, MINI_V1,
                    MINI["mutate"], fair=False)
    assert g["gate"] == "budget"

    stale = _proposal(
        [{"op": "set", "path": "senses.govern.x", "value": 1}], MINI_V1)
    stale["base_revision"] = "0" * 64
    g = evolve.gate(stale, ld, MINI_V1, MINI["mutate"], fair=False)
    assert g["gate"] == "stale"

    same = _proposal([{"op": "set",
                       "path": "govern.goals.keep.retry_polls",
                       "value": 5}], MINI_V1)     # already 5 -> no change
    g = evolve.gate(same, ld, MINI_V1, MINI["mutate"], fair=False)
    assert g["gate"] == "vacuous"

    miss = _proposal([{"op": "remove", "path": "govern.goals.nope"},
                      {"op": "remove", "path": "rules.nope"}],
                     MINI_V1)
    g = evolve.gate(miss, ld, MINI_V1, MINI["mutate"], fair=False)
    assert g["gate"] == "validation" and g["violations"]

    # identity surfaces are not mutable
    imm = _proposal([{"op": "set", "path": "pack_id",
                      "value": "pack.hijack"}], MINI_V1)
    g = evolve.gate(imm, ld, MINI_V1, MINI["mutate"], fair=False)
    assert not g["ok"] and "not a mutable surface" in g["violations"][0]


def test_gate_rejects_unknown_method_and_fair_dev():
    ops = [{"op": "append", "path": "templates",
            "value": {"id": "evil", "method": "no.such.rpc",
                      "params_schema": {}}}]
    g = evolve.gate(_proposal(ops, MINI_V1), _loaded(MINI_V1), MINI_V1,
                    MINI["mutate"], fair=False)
    assert not g["ok"] and "sealed inventory" in g["violations"][0]

    dev = [{"op": "append", "path": "templates",
            "value": {"id": "dv", "method": "dev.spawn",
                      "params_schema": {}}}]
    g = evolve.gate(_proposal(dev, MINI_V1), _loaded(MINI_V1),
                    MINI_V1, MINI["mutate"], fair=True)
    assert not g["ok"] and "dev-class" in g["violations"][0]


def test_gate_rejects_schema_breaking_mutation():
    ops = [{"op": "set", "path": "templates",
            "value": []}]  # rewrites to capabilities.templates -> empty
    g = evolve.gate(_proposal(ops, MINI_V1), _loaded(MINI_V1), MINI_V1,
                    MINI["mutate"], fair=False)
    assert not g["ok"] and g["gate"] == "validation"


# -- maybe_trigger + materialize -------------------------------------------------

def test_maybe_trigger_candidate_and_active_pack_untouched(tmp_path):
    emitted: list[dict] = []
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    d = _stub_dispatcher()
    pack_bytes = json.dumps(MINI, sort_keys=True)
    r = _maybe(ps, dispatcher=d, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=_chat_ok)
    assert r["verdict"] == "candidate"
    types = [e["event_type"] for e in emitted]
    assert types[:2] == ["mutation.triggered", "mutation.proposed"]
    assert "mutation.candidate" in types
    # active pack object never mutated by the pass
    assert json.dumps(MINI, sort_keys=True) == pack_bytes
    rows = evolve.lineage_rows(tmp_path)
    assert rows[-1]["state"] == "pending"
    assert Path(rows[-1]["candidate_path"]).is_file()


def test_maybe_trigger_noop_when_no_ops(tmp_path):
    def chat_noop(endpoint_id, model, messages, usage_tracker=None):
        return {"ok": True, "body": {"choices": [{"message": {
            "content": json.dumps({
                "mutation_id": "mut.nope", "analysis": {
                    "failure_paths": [], "likely_paths": []},
                "mutations": [], "rationale": "looks fine"})}}]}}
    emitted: list[dict] = []
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    r = _maybe(ps, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=chat_noop)
    assert r["verdict"] == "noop"
    assert "mutation.noop" in [e["event_type"] for e in emitted]


def test_maybe_trigger_rejection_path(tmp_path):
    emitted: list[dict] = []
    ps = evolve.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    r = _maybe(ps, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=_chat_bad)
    assert r["verdict"] == "rejected"
    rej = next(e for e in emitted
               if e["event_type"] == "mutation.rejected")
    assert rej["payload"]["gate"] == "schema"


def test_maybe_trigger_disabled_returns_none(tmp_path):
    ps = evolve.PassState({})
    ps.note(_transition("govern.keep", "failed"))
    assert _maybe(ps, state_dir=tmp_path) is None


# -- boundary: promote / revert --------------------------------------------------

@pytest.fixture()
def packs(tmp_path, monkeypatch):
    src = REPO_ROOT / "components" / "rimbrain" / "packs"
    dst = tmp_path / "packs"
    for pid in ("start-mode-v0", "improve-v0"):
        (dst / pid).mkdir(parents=True)
        shutil.copy(src / pid / "pack.yaml", dst / pid / "pack.yaml")
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(dst))
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    return dst


def _mk_candidate(packs_dir, pack_id="start-mode-v0", tweak=None):
    doc = yaml.safe_load((packs_dir / pack_id / "pack.yaml")
                         .read_text(encoding="utf-8"))
    if tweak:
        doc = tweak(doc)
    cdir = packs_dir / "candidates"
    cdir.mkdir(exist_ok=True)
    out = cdir / "cand-mut-test-aaaa.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out, templates._hash_of(doc)


def test_boundary_promotes_pending_candidate(packs, tmp_path):
    state = tmp_path / "state"
    parent_hash = templates.current_hash("start-mode-v0")
    cand, cand_hash = _mk_candidate(
        packs, tweak=lambda d: dict(d, revision="v0+mut.test"))
    evolve._append_lineage(state, {
        "candidate_id": cand.stem, "target_pack": "start-mode-v0",
        "candidate_path": str(cand), "candidate_hash": cand_hash,
        "state": "pending"})
    events: list[dict] = []
    out = evolve.boundary("start-mode-v0", state, emit=events.append)
    assert out["promoted"] == cand.stem
    assert templates.current_hash("start-mode-v0") == cand_hash
    assert templates.current_hash("start-mode-v0") != parent_hash
    assert any(e["event_type"] == "mutation.promoted" for e in events)
    rows = evolve.lineage_rows(state)
    promoted = [r for r in rows if r["state"] == "promoted"]
    assert promoted and promoted[-1]["parent_hash"] == parent_hash
    assert Path(promoted[-1]["parent_path"]).is_file()  # parent backup


def test_boundary_rejects_missing_candidate(packs, tmp_path):
    state = tmp_path / "state"
    evolve._append_lineage(state, {
        "candidate_id": "gone", "target_pack": "start-mode-v0",
        "candidate_path": str(packs / "candidates" / "gone.yaml"),
        "candidate_hash": "x", "state": "pending"})
    events: list[dict] = []
    before = templates.current_hash("start-mode-v0")
    out = evolve.boundary("start-mode-v0", state, emit=events.append)
    assert out["promoted"] is None and out["rejected"] == ["gone"]
    assert templates.current_hash("start-mode-v0") == before


def test_boundary_reverts_regressed_promotion(packs, tmp_path):
    state = tmp_path / "state"
    parent = templates.pack_path("start-mode-v0").read_bytes()
    parent_hash = templates.current_hash("start-mode-v0")
    # a promoted lineage row whose recorded baseline was great; the
    # "episode since" contains only failures -> worse score -> revert
    backup = packs / "candidates" / "parent-backup.yaml"
    backup.parent.mkdir(exist_ok=True)
    backup.write_bytes(parent)
    bad = copy.deepcopy(MINI)
    bad["pack_id"] = "pack.start-mode-v0"
    bad["revision"] = "v0+bad"
    templates.pack_path("start-mode-v0") \
        .write_text(yaml.safe_dump(bad), encoding="utf-8")
    evolve._append_lineage(state, {
        "candidate_id": "cand-bad", "target_pack": "start-mode-v0",
        "candidate_path": str(backup), "candidate_hash": "x",
        "state": "promoted", "parent_hash": parent_hash,
        "parent_path": str(backup), "baseline_score": 0.0,
        "events_offset": 0})
    # episode evidence: all-failed transitions -> score > baseline 0.0
    for i in range(3):
        (state / "events.jsonl").open("a").write(
            json.dumps(_transition(f"govern.g{i}", "failed", i)) + "\n")
    events: list[dict] = []
    out = evolve.boundary("start-mode-v0", state, emit=events.append)
    assert out["reverted"] == "cand-bad"
    assert templates.current_hash("start-mode-v0") == parent_hash
    assert any(e["event_type"] == "mutation.reverted" for e in events)


def test_boundary_keeps_improved_promotion(packs, tmp_path):
    state = tmp_path / "state"
    backup = packs / "candidates" / "p.yaml"
    backup.parent.mkdir(exist_ok=True)
    backup.write_bytes(b"keepme")
    evolve._append_lineage(state, {
        "candidate_id": "cand-ok", "target_pack": "start-mode-v0",
        "candidate_path": str(backup), "candidate_hash": "x",
        "state": "promoted", "parent_hash": "p", "parent_path": str(backup),
        "baseline_score": 0.9, "events_offset": 0})
    for i in range(3):   # clean episode -> score 0 < 0.9 -> keep
        (state / "events.jsonl").open("a").write(
            json.dumps(_transition(f"govern.g{i}", "succeeded", i)) + "\n")
    out = evolve.boundary("start-mode-v0", state)
    assert out["reverted"] is None
    assert evolve.lineage_rows(state)[-1]["state"] == "promoted"


# -- packmut compile_legacy -------------------------------------------------------

def test_compile_legacy_drop_rule_targets_only_the_list_that_has_it():
    doc = {"universal": {"rules": [{"id": "a"}]},
           "emergency": [{"id": "b"}],
           "combat": {"raid": {"rules": [{"id": "c"}]}}}
    ops = packmut.compile_legacy(
        [{"op": "drop_rule", "ids": ["a", "c", "nope"]}], doc)
    assert ops == [{"op": "remove", "path": "universal.rules.a"},
                   {"op": "remove", "path": "combat.raid.rules.c"}]
    # v0 paths rewrite to v1 surfaces on the migrated doc
    doc_v1 = templates.migrate_v0(doc)
    changed, misses = packmut.apply_ops(doc_v1, ops)
    assert changed and not misses
    assert doc_v1["rules"] == []
    assert doc_v1["combat"]["raid"]["rules"] == []


# -- integration: run --------------------------------------------------------

def test_run_live_mutate_off_emits_nothing(packs, tmp_path):
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    res = run(d, game, ledger, d.pack["pack"], iterations=30,
          live_mutate=False, stop_on_complete=True)
    assert res["completed"]
    assert not [e for e in events
                if str(e["event_type"]).startswith("mutation.")]


def test_run_live_mutate_fires_and_pack_stays_put(packs, tmp_path):
    """A held run under --live-mutate: goals go terminal -> reflection
    passes fire; the loaded pack file hash never changes mid-run."""
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    pack = copy.deepcopy(d.pack["pack"])
    pack["mutate"] = copy.deepcopy(MINI["mutate"])
    pack["mutate"]["goals_per_pass"] = 5
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    res = run(d, game, ledger, pack, iterations=40,
          live_mutate=True,
          mutate_resolver=_resolver_rules,
          mutate_chat=_chat_broken)
    assert res["completed"]
    mut_events = [e["event_type"] for e in events
                  if str(e["event_type"]).startswith("mutation.")]
    # passes ran (triggered at least once); each resolved to a verdict
    assert "mutation.triggered" in mut_events
    assert any(t in mut_events for t in
               ("mutation.candidate", "mutation.degraded",
                "mutation.rejected", "mutation.noop"))
    assert d.pack["hash"] == templates.current_hash("start-mode-v0")


# -- v1-surface round-trips (T033) ---------------------------------------


def test_phase_and_decide_ops_round_trip():
    doc = templates.migrate_v0({
        "schema_version": 0, "pack_id": "pack.rt", "revision": "v0",
        "templates": [{"id": "ping", "method": "game.status",
                       "params_schema": {}}],
        "jobs": [], "decision_map": [], "emergency": [],
        "start": {"phases": [{"id": "shelter", "steps": []}],
                  "exit": {}},
        "decide": {"select": {"cadence_polls": 1}},
    })
    ops = [
        {"op": "upsert", "path": "phases",
         "value": {"id": "expand", "goals": [],
                   "complete": {"all": []}}},
        {"op": "set", "path": "phases.init.steps.shelter.tag",
         "value": "x"},
        {"op": "set", "path": "decide.plan.cadence_s", "value": 60},
        {"op": "set", "path": "action_list.max_items", "value": 12},
        {"op": "append", "path": "rules",
         "value": {"id": "r1", "when": {}, "steps": []}},
        {"op": "upsert", "path": "options",
         "value": {"id": "opt-x", "summary": "s"}},
    ]
    changed, misses = packmut.apply_ops(doc, ops)
    assert changed and not misses, misses
    assert doc["phases"][0]["steps"][0]["tag"] == "x"
    assert any(p["id"] == "expand" for p in doc["phases"])
    assert doc["decide"]["plan"]["cadence_s"] == 60
    assert doc["action_list"]["max_items"] == 12
    assert doc["rules"][-1]["id"] == "r1"
    assert doc["options"][-1]["id"] == "opt-x"
    # gated candidate validates through the shared gate
    g = evolve.gate(
        {"schema_version": 0, "mutation_id": "mut.rt",
         "base_revision": templates._hash_of(doc),
         "analysis": {}, "mutations": ops, "rationale": "r"},
        {"pack": doc, "hash": templates._hash_of(doc)}, doc,
        {"max_ops": 10}, fair=False)
    assert g["ok"], g
