"""Select stage tests (feature 017; FR-1407..1411, FR-1424, FR-1430):
candidate compile/scoring/truncation, batched question render,
membership validation -> fallback matrix, shadow mode, cadence,
decision records, and the persisted authority registry."""

import json

import pytest

from runtime import policy, select
from runtime.dispatch import Dispatcher
from runtime.phase import PhaseEngine
from runtime.runstate import RunState
from runtime.tasks import TaskLedger

from test_phase import StartSim


def _pack(n_goals=2, **sel_over):
    sel = {"role": "rimbrain.select", "fallback": "priority_head",
           "shadow": True, "batch_pawns": True}
    sel.update(sel_over)
    return {
        "schema_version": 1,
        "meta": {"pack_id": "test.select", "revision": "v1",
                 "class": "dev"},
        "capabilities": {"templates": [
            {"id": "assign-job", "method": "ui.assign_job",
             "params_schema": {}},
            {"id": "set-stock", "method": "steward.stock.set",
             "params_schema": {}}]},
        "phases": [],
        "rules": [],
        "standing_goals": [
            {"id": f"g-{i:02d}",
             "effect": {"field": f"@obs:flag_{i}", "op": "truthy"},
             "steps": [{"template": "set-stock",
                        "params": {"k": f"g-{i}"}}]}
            for i in range(n_goals)],
        "decide": {"select": sel}}


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, events, tmp_path


def _engine(pack, ledger, tmp_path, decisions):
    e = PhaseEngine(pack, ledger,
                    runstate=RunState.load(
                        tmp_path / "state" / "runstate.json"))
    e.decisions = decisions
    return e


def _ctx(pack, game, obs, decisions, poll=0):
    return policy.Ctx(cfg=pack, obs=obs, game=game, state={},
                      tick=0, poll=poll, decisions=decisions)


def _obs(game):
    return {"tick": 0,
            "colonists": {"count": len(game.pawns),
                          "colonist_list": game.pawns},
            "stocks": {"nutrition": 4.0}}


def _call_log():
    calls = []

    def fake(sel, state, questions):
        calls.append({"state": state, "questions": questions})
        return {"ok": True, "body": {"answers": {}}}
    return fake, calls


def test_candidates_compile_ordered_and_bounded(rig):
    """FR-1407: >20 eligibles truncate at the hard bound; declared order
    is the default priority."""
    d, game, ledger, events, tmp = rig
    pack = _pack(n_goals=25)
    e = _engine(pack, ledger, tmp, [])
    ctx = _ctx(pack, game, _obs(game), [])
    cands = select.compile_actions(pack, e, ctx, _obs(game))
    assert len(cands) == 20
    assert cands[0]["id"] == "govern.g-00"
    assert all(c["scope"] == "colony" for c in cands)


def test_when_gate_excludes_goal(rig):
    """A goal whose `when` fails never becomes a candidate."""
    d, game, ledger, events, tmp = rig
    pack = _pack(n_goals=2)
    pack["standing_goals"][1]["when"] = \
        {"field": "@obs:never", "op": "truthy"}
    e = _engine(pack, ledger, tmp, [])
    ctx = _ctx(pack, game, _obs(game), [])
    cands = select.compile_actions(pack, e, ctx, _obs(game))
    assert [c["id"] for c in cands] == ["govern.g-00"]


def test_batch_render_shape(rig):
    """select-batch contract: q.colony + q.pawn.<id>, criteria keyed by
    candidate ids, one payload for all pawns."""
    d, game, ledger, events, tmp = rig
    pack = _pack(n_goals=2, pawn_scope={
        "for_each": "colonists",
        "options": [{"id": "haul", "template": "assign-job",
                     "params": {"pawn": "@var:it.id",
                                "job": "Haul"}}]})
    e = _engine(pack, ledger, tmp, [])
    ctx = _ctx(pack, game, _obs(game), [])
    obs = _obs(game)
    cands = select.compile_actions(pack, e, ctx, obs)
    q = select.build_questions(cands, obs,
                               pack["decide"]["select"], None)
    assert set(q["q.colony"]["criteria"]) == \
        {"govern.g-00", "govern.g-01"}
    pawn_qs = [k for k in q if k.startswith("q.pawn.")]
    assert len(pawn_qs) == len(game.pawns)
    assert all(set(q[k]["criteria"]) ==
               {f"pawn.{p['id']}.haul" for p in game.pawns
                if k == f"q.pawn.{p['id']}"}
               for k in pawn_qs)


def _run_decide(rig, pack, answers=None, caller=None, poll=0):
    d, game, ledger, events, tmp = rig
    decisions: list = []
    e = _engine(pack, ledger, tmp, decisions)
    obs = _obs(game)
    ctx = _ctx(pack, game, obs, decisions, poll=poll)
    emitted = []
    if caller is None:
        caller, calls = _call_log()
    else:
        calls = None
    out = select.decide(d, pack, e, ctx, obs, tick=0, poll=poll,
                        state_dir=tmp / "state", caller=caller,
                        emit=emitted.append)
    return out, decisions, emitted, calls


def test_valid_pick_applies_under_authority(rig):
    """A valid pick under authority drives that goal's steps through
    the engine's ledger machinery."""
    pack = _pack(n_goals=2, shadow=False, rung="authority",
                 qualify={"min_picks": 0, "max_divergence": 1.0})

    def caller(sel, state, questions):
        return {"ok": True, "body": {"answers":
                {"q.colony": {"choice": "govern.g-01"}}}}
    out, decisions, emitted, _ = _run_decide(rig, pack, caller=caller)
    row = next(r for r in decisions if r.get("select"))
    assert row["applied"] == "govern.g-01" and not row["fallback"]
    assert row["template"] == "govern.g-01"
    # ledger saw the goal's task
    d, game, ledger, events, tmp = rig
    assert any(tid.endswith("g-01") for tid in ledger.tasks)


def test_invalid_pick_falls_back(rig):
    """A pick outside the offered set -> priority_head fallback +
    select.invalid (FR-1408)."""
    pack = _pack(n_goals=2, shadow=False, rung="authority",
                 qualify={"min_picks": 0, "max_divergence": 1.0})

    def caller(sel, state, questions):
        return {"ok": True, "body": {"answers":
                {"q.colony": {"choice": "bogus"}}}}
    out, decisions, emitted, _ = _run_decide(rig, pack, caller=caller)
    row = next(r for r in decisions if r.get("select"))
    assert row["applied"] == "govern.g-00"
    assert row["fallback"] is True
    assert any(e["event_type"] == "select.invalid" for e in emitted)


def test_endpoint_down_degrades(rig):
    """Unreachable endpoint -> fallback for every question +
    select.degraded; the poll proceeds."""
    pack = _pack(n_goals=2, shadow=False, rung="authority",
                 qualify={"min_picks": 0, "max_divergence": 1.0})

    def down(sel, state, questions):
        return {"ok": False, "error": {"code": "endpoint.down"}}
    out, decisions, emitted, _ = _run_decide(rig, pack, caller=down)
    row = next(r for r in decisions if r.get("select"))
    assert row["applied"] == "govern.g-00"
    assert row["fallback"] is True
    assert any(e["event_type"] == "select.degraded" for e in emitted)


def test_shadow_records_pick_executes_fallback(rig):
    """FR-1424 shadow rung: the pick is recorded, the deterministic
    fallback dispatches."""
    pack = _pack(n_goals=2)  # shadow: true default

    def caller(sel, state, questions):
        return {"ok": True, "body": {"answers":
                {"q.colony": {"choice": "govern.g-01"}}}}
    out, decisions, emitted, _ = _run_decide(rig, pack, caller=caller)
    row = next(r for r in decisions if r.get("select"))
    assert row["pick"] == "govern.g-01"
    assert row["applied"] == "govern.g-00"   # priority_head fallback
    assert row["shadow"] is True and row["fallback"] is True


def test_zero_candidates_no_request(rig):
    """All effects holding -> empty list -> no endpoint call."""
    d, game, ledger, events, tmp = rig
    pack = _pack(n_goals=2)
    decisions: list = []
    e = _engine(pack, ledger, tmp, decisions)
    obs = _obs(game)
    obs["flag_0"] = obs["flag_1"] = True   # both effects already hold
    caller, calls = _call_log()
    ctx = _ctx(pack, game, obs, decisions)
    out = select.decide(d, pack, e, ctx, obs, tick=0, poll=0,
                        state_dir=tmp / "state", caller=caller,
                        emit=lambda e2: None)
    assert calls == []
    assert out["state"] == "holding"


def test_one_request_for_all_pawns(rig):
    """FR: one batched request per poll regardless of pawn count."""
    pack = _pack(n_goals=0, pawn_scope={
        "for_each": "colonists",
        "options": [{"id": "haul", "template": "assign-job",
                     "params": {"pawn": "@var:it.id",
                                "job": "Haul"}}]})
    caller, calls = _call_log()
    _run_decide(rig, pack, caller=caller)
    assert len(calls) == 1
    qs = calls[0]["questions"]
    assert len([k for k in qs if k.startswith("q.pawn.")]) == \
        len(rig[1].pawns)


def test_cadence_skips_not_queues(rig):
    """FR-1430: cadence_polls=2 -> odd polls skip (None -> default
    drive), even polls decide."""
    pack = _pack(n_goals=2, cadence_polls=2)
    caller, calls = _call_log()
    out1 = _run_decide(rig, pack, caller=caller, poll=1)[0]
    out2 = _run_decide(rig, pack, caller=caller, poll=2)[0]
    assert out1 is None and out2 is not None
    assert len(calls) == 1


def test_decision_record_fields(rig):
    """FR-1411: every select decision logs the offered set, pick,
    applied choice, and the inputs hash."""
    pack = _pack(n_goals=2)
    out, decisions, emitted, _ = _run_decide(rig, pack)
    row = next(r for r in decisions if r.get("select"))
    for k in ("tick", "poll", "source", "phase", "offered", "pick",
              "applied", "fallback", "shadow", "inputs_hash",
              "latency_ms"):
        assert k in row, k
    assert row["source"].startswith("select:")
    assert row["offered"] == ["govern.g-00", "govern.g-01"]


def test_authority_registry_persists(rig, tmp_path):
    """FR-1424: (model,prompt,context) tuple state survives restarts —
    a shadow poll accumulates evidence on disk."""
    pack = _pack(n_goals=2)

    def caller(sel, state, questions):
        return {"ok": True, "body": {"answers":
                {"q.colony": {"choice": "govern.g-00"}}}}
    _run_decide(rig, pack, caller=caller)
    reg = json.loads(
        (rig[4] / "state" / "select_authority.json").read_text())
    rec = next(iter(reg["tuples"].values()))
    assert rec["rung"] == "shadow" and rec["picks"] == 1
    assert rec["divergent"] == 0   # pick == fallback -> no divergence
