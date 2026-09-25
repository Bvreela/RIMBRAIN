"""Plan-loop tests (feature 005; FR-404..409, SC-401/403/404/405).

End-to-end with injected resolver/chat: proposed -> reviewed -> accepted ->
candidate written + actions dispatched through the Dispatcher (the ONLY
write path). Five runs bit-identical; degraded path completes via rules-only;
scored-episode guard hard-rejects.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import planloop, templates  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402

PACK = "core-survival-v0"
CLOCK = lambda: "2026-01-01T00:00:00Z"  # noqa: E731

_PLAN = {
    "schema_version": 0, "plan_id": "plan.loop-1", "horizon_ticks": 60000,
    "actions": [
        {"template_id": "prioritize-work",
         "params": {"pawn": "{state.first_colonist}",
                    "priorities": {"Growing": 1}}},
        {"template_id": "haul-designate",
         "params": {"designator": "haul", "cells": ["{state.haul_cell}"]}},
    ],
    "policy_mutations": [], "rationale": "loop test",
}


def _resolver(role, **kw):
    return {"ok": True,
            "resolved": {"endpoint_id": "openrouter", "model": "nemotron",
                         "api": "openai-compat"},
            "degraded": False, "reason": "primary", "tried": []}


def _rules_resolver(role, **kw):
    return {"ok": True,
            "resolved": {"kind": "fallback", "name": "rules-only"},
            "degraded": True, "reason": "fallback:rules-only", "tried": []}


def _chat_for(plan):
    def c(endpoint_id, model, messages, **kw):
        content = (json.dumps(plan) if "Critique the plan" not in
                   json.dumps(messages) else "fine")
        return {"ok": True, "body": {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 11}}}
    return c


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    """Isolated packs dir (candidate writes stay out of the repo)."""
    packs = tmp_path / "packs"
    (packs / PACK).mkdir(parents=True)
    src = (REPO_ROOT / "components" / "rimbrain" / "packs"
           / PACK / "pack.yaml")
    shutil.copy(src, packs / PACK / "pack.yaml")
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(packs))
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = SimGame()
    d = Dispatcher(game, clock=CLOCK)
    d.load_pack(PACK)
    return game, d


def test_full_round_proposed_reviewed_accepted(rig):
    game, d = rig
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(_PLAN),
                          clock=CLOCK)
    assert r["ok"]
    kinds = [e["event_type"] for e in r["events"]]
    assert kinds == ["plan.proposed", "plan.reviewed", "plan.accepted"]
    proposed = r["events"][0]["payload"]
    assert proposed["endpoint_id"] == "openrouter"
    assert proposed["usage"]["prompt_tokens"] == 9
    # plan actions went through the single writer into the SimGame
    state = game.current
    assert state["priorities"]["Gomez"] == {"Growing": 1}
    assert any(x["designator"] == "haul" for x in state["designations"])
    assert all(e["outcome"] == "ok" for e in r["dispatched"])


def test_mutation_writes_loadable_candidate(rig, tmp_path):
    """SC-404: accepted mutations materialize a loadable candidate pack."""
    game, d = rig
    plan = dict(_PLAN, plan_id="plan.mut-1", actions=[], policy_mutations=[
        {"op": "edit_decision_map", "target": "q.action",
         "patch": {"question": "q.action", "choice": "gather",
                   "action": {"template_id": "haul-designate",
                              "params": {"designator": "haul",
                                         "cells": ["{state.haul_cell}"]}}}}])
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(plan),
                          clock=CLOCK)
    assert r["ok"] and r["candidates"]
    cand = Path(r["candidates"][0]["path"])
    assert cand.parent.name == "candidates"
    assert str(tmp_path) in str(cand)  # isolated packs dir, not the repo
    # candidate loads through the same validated path (schema + inventory)
    loaded = templates.load_pack(f"candidates/{cand.stem}")
    assert loaded["pack"]["decision_map"][-1]["choice"] == "gather"
    assert loaded["hash"] == r["candidates"][0]["hash"]


def test_invalid_mutation_rejected_no_file(rig, tmp_path):
    game, d = rig
    plan = dict(_PLAN, plan_id="plan.badmut", actions=[], policy_mutations=[
        {"op": "add_template", "target": "bad",
         "patch": {"id": "bad", "method": "ui.does_not_exist",
                   "params_schema": {"type": "object"}}}])
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(plan),
                          clock=CLOCK)
    assert not r["ok"]
    assert not (tmp_path / "packs" / "candidates").exists()


def test_violating_plan_rejected_despite_approval(rig):
    """SC-401 end-to-end: stub chat 'approves' but the gate rejects."""
    game, d = rig
    bad = dict(_PLAN, plan_id="plan.bad",
               actions=[{"template_id": "nope", "params": {}}])
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(bad),
                          clock=CLOCK)
    assert not r["ok"]
    assert r["events"][-1]["event_type"] == "plan.rejected"
    assert game.current["priorities"] == {}  # zero writes


def test_five_runs_bit_identical(rig):
    """SC-403: fixed clock + stub chat -> identical event streams."""
    game, d = rig
    streams = []
    for _ in range(5):
        r = planloop.run_plan(game.current, PACK, dispatcher=None,
                              resolver=_resolver, chat=_chat_for(_PLAN),
                              clock=CLOCK, dispatch_actions=False)
        streams.append(json.dumps(r["events"], sort_keys=True))
    assert len(set(streams)) == 1


def test_degraded_rules_only_completes(rig):
    """SC-405: resolution to rules-only yields the pack fallback plan."""
    game, d = rig
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_rules_resolver, chat=_chat_for(_PLAN),
                          clock=CLOCK)
    assert r["ok"] and r["degraded"] is True
    assert r["events"][0]["payload"]["endpoint_id"] == "rules-only"


def test_scored_episode_guard(rig):
    game, d = rig
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(_PLAN),
                          clock=CLOCK, scored_episode_active=True)
    assert not r["ok"]
    assert r["error"]["code"] == "plan.scored_episode_active"
    assert r["events"][-1]["event_type"] == "plan.rejected"


def test_emitted_events_validate_payload_schemas(rig):
    """US4: every emitted plan.* envelope validates its payload schema.

    (envelope.schema.json uses relative $refs the bare validator can't
    resolve; envelope shape is asserted structurally, payloads strictly.)
    """
    import jsonschema
    game, d = rig
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(_PLAN),
                          clock=CLOCK)
    assert r["ok"]
    types_dir = (REPO_ROOT / "components" / "contracts" / "schemas"
                 / "events" / "types")
    for env in r["events"]:
        for key in ("schema_version", "event_id", "sequence", "event_type",
                    "wall_time_utc", "source", "payload", "privacy"):
            assert key in env, f"envelope missing {key}"
        payload_schema = json.loads(
            (types_dir / f"{env['event_type']}.schema.json")
            .read_text(encoding="utf-8"))
        jsonschema.validate(env["payload"], payload_schema)


def test_malformed_plan_rejected_zero_writes(rig):
    """SC-402: unparseable model output -> plan.rejected, nothing dispatched."""
    game, d = rig
    r = planloop.run_plan(game.current, PACK, dispatcher=d,
                          resolver=_resolver, chat=_chat_for(None),
                          clock=CLOCK)
    assert not r["ok"]
    assert r["error"]["code"] == "plan.malformed"
    assert game.current["priorities"] == {}
