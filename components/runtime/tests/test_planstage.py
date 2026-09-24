"""Plan stage tests (feature 017 US3; contracts/plan-output.md):
triggers (cadence/boundary/events), the decisive gate, promote ->
runtime goal materialization, and last-plan-standing on outage."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import planstage, simgame, templates  # noqa: E402
from runtime.dispatch import Dispatcher
from runtime.phase import PhaseEngine
from runtime.runstate import RunState
from runtime.tasks import TaskLedger

PACK = {
    "meta": {"id": "planstage-test", "schema_version": 1},
    "templates": [
        {"id": "noop", "method": "ui.noop", "params": []},
        {"id": "evil", "method": "dev.spawn", "params": []},
    ],
    "standing_goals": [
        {"id": "food", "effect": {"field": "@obs:meals_present",
                                  "op": "truthy"},
         "steps": [{"template": "noop", "params": {}}]},
        {"id": "shelter", "when": {"field": "@obs:tick", "op": "gt",
                                   "value": 999999},
         "effect": {"field": "@obs:meals_present", "op": "gt",
                    "value": 99},
         "steps": [{"template": "noop", "params": {}}]},
    ],
    "options": [
        {"id": "opt-patrol",
         "goal": {"id": "plan.opt-patrol",
                  "effect": {"field": "@obs:tick", "op": "gt",
                             "value": 1},
                  "steps": [{"template": "noop",
                             "params": {"note": "@param:note"}}]},
         "params": {"note": {}}},
        {"id": "opt-dev",
         "goal": {"steps": [{"template": "evil", "params": {}}]}},
        {"id": "opt-empty"},
    ],
    "decide": {"plan": {"cadence_s": 150, "on_phase_boundary": True,
                        "on_events": ["raid_letter"]}},
}


@pytest.fixture
def rig(tmp_path):
    ledger = TaskLedger(tmp_path / "tasks.jsonl")
    game = simgame.SimGame()
    d = Dispatcher(game, fair=True)
    engine = PhaseEngine(PACK, ledger,
                         runstate=RunState())
    return d, engine, ledger, game


def _ok(plan):
    return lambda cfg, digest: {"ok": True, "body": {"plan": plan}}


def test_first_fire_is_immediate(rig):
    d, engine, ledger, game = rig
    seen = []
    plan = planstage.tick(d, PACK, engine, ledger, {}, tick=1, poll=0,
                          caller=_ok({"goal_order": ["food"]}),
                          emit=seen.append, now=1000.0)
    assert plan and plan["goal_order"] == ["food"]
    assert seen[-1]["event_type"] == "plan.accepted"


def test_cadence_gates_second_fire(rig):
    d, engine, ledger, game = rig
    calls = []
    caller = lambda c, g: (calls.append(1), _ok({})(c, g))[1]
    planstage.tick(d, PACK, engine, ledger, {}, tick=1, poll=0,
                   caller=caller, now=1000.0)
    planstage.tick(d, PACK, engine, ledger, {}, tick=2, poll=1,
                   caller=caller, now=1100.0)   # < cadence_s
    assert len(calls) == 1
    planstage.tick(d, PACK, engine, ledger, {}, tick=3, poll=2,
                   caller=caller, now=1200.0)   # >= cadence_s
    assert len(calls) == 2


def test_phase_boundary_and_event_triggers(rig):
    d, engine, ledger, game = rig
    calls = []
    caller = lambda c, g: (calls.append(1), _ok({})(c, g))[1]
    planstage.tick(d, PACK, engine, ledger, {}, tick=1, poll=0,
                   caller=caller, now=1000.0)
    engine.rs.phase["init"] = {"done": True}
    planstage.tick(d, PACK, engine, ledger, {}, tick=2, poll=1,
                   caller=caller, now=1010.0)    # boundary fires
    assert len(calls) == 2
    planstage.tick(d, PACK, engine, ledger, {}, tick=3, poll=2,
                   caller=caller, now=1020.0,
                   events=["task.transition"])  # undeclared — no fire
    assert len(calls) == 2
    planstage.tick(d, PACK, engine, ledger, {}, tick=4, poll=3,
                   caller=caller, now=1030.0,
                   events=["raid_letter"])      # declared event fires
    assert len(calls) == 3


def test_gate_rejects_unknown_ids_and_last_plan_stands(rig):
    d, engine, ledger, game = rig
    planstage.tick(d, PACK, engine, ledger, {}, tick=1, poll=0,
                   caller=_ok({"goal_order": ["food"]}), now=1000.0)
    seen = []
    plan = planstage.tick(
        d, PACK, engine, ledger, {}, tick=2, poll=1,
        caller=_ok({"goal_order": ["nonexistent-goal"]}),
        emit=seen.append, now=1200.0)
    assert plan["goal_order"] == ["food"]       # prior plan in force
    rej = [e for e in seen if e["event_type"] == "plan.rejected"]
    assert rej and "unknown goal id" in rej[0]["payload"][
        "violations"][0]


def test_outage_degrades_and_prior_plan_stands(rig):
    d, engine, ledger, game = rig
    planstage.tick(d, PACK, engine, ledger, {}, tick=1, poll=0,
                   caller=_ok({"activate": ["food"]}), now=1000.0)
    seen = []
    down = lambda c, g: {"ok": False, "error": {"code": "e.down"}}
    plan = planstage.tick(d, PACK, engine, ledger, {}, tick=2, poll=1,
                          caller=down, emit=seen.append, now=1200.0)
    assert plan["activate"] == ["food"]
    assert any(e["event_type"] == "plan.degraded" for e in seen)


def test_activate_deactivate_and_promote(rig):
    d, engine, ledger, game = rig
    plan = planstage.tick(
        d, PACK, engine, ledger, {}, tick=1, poll=0,
        caller=_ok({"deactivate": ["food"],
                    "promote": [{"option": "opt-patrol",
                                 "params": {"note": "hi"}}]}),
        now=1000.0)
    assert "food" in engine._plan_off
    assert any(g["id"] == "plan.opt-patrol"
               and g["steps"][0]["params"]["note"] == "hi"
               for g in engine.plan_goals)
    # persisted + re-materialized on engine rebuild
    engine2 = PhaseEngine(PACK, TaskLedger(), runstate=engine.rs)
    assert engine2.plan_goals[0]["id"] == "plan.opt-patrol"
    assert "food" in engine2._plan_off


def test_gate_rejects_bad_params_and_dev_class(rig):
    d, engine, ledger, game = rig
    seen = []
    planstage.tick(
        d, PACK, engine, ledger, {}, tick=1, poll=0, emit=seen.append,
        caller=_ok({"promote": [{"option": "opt-patrol",
                                 "params": {"bogus": 1}}]}),
        now=1000.0)
    planstage.tick(
        d, PACK, engine, ledger, {}, tick=2, poll=1, emit=seen.append,
        caller=_ok({"promote": [{"option": "opt-dev"}]}),
        now=1200.0)
    planstage.tick(
        d, PACK, engine, ledger, {}, tick=3, poll=2, emit=seen.append,
        caller=_ok({"promote": [{"option": "opt-empty"}]}),
        now=1400.0)
    viols = [v for e in seen if e["event_type"] == "plan.rejected"
             for v in e["payload"]["violations"]]
    assert any("params not in schema" in v for v in viols)
    assert any("dev-class" in v for v in viols)
    assert any("no materializable" in v for v in viols)


def test_goal_order_feeds_select_scoring(rig):
    """FR-1413: plan.goal_order boosts matching colony candidates."""
    from runtime import policy, select
    d, engine, ledger, game = rig
    obs = {"tick": 5, "meals_present": 0}
    ctx = policy.Ctx(cfg=PACK, obs=obs, game=game,
                     state=engine.rs.rule_state,
                     persist=engine.rs.vars, tick=5, poll=0)
    # 'shelter' is when-gated off at tick 5 -> food stays alone; make
    # both eligible by lifting the gate
    PACK["standing_goals"][1]["when"] = None
    base = select.compile_actions(PACK, engine, ctx, obs)
    boosted = select.compile_actions(
        PACK, engine, ctx, obs, plan={"goal_order": ["shelter"]})
    assert base[0]["id"].endswith("food")
    assert boosted[0]["id"].endswith("shelter")
