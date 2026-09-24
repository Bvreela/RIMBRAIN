"""Combat-phase tests (feature 017 port of feature 010 combat-mode):
prereq gate, clear, timeout, restore — now driven by the unified loop's
`kind: combat` phase under scripted+stage (FR-1429).
"""

import json
import pathlib

import pytest

from runtime.dispatch import Dispatcher
from runtime.loop import run
from runtime.phase import _hostiles
from runtime.tasks import TaskLedger

from test_phase import StartSim


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("dev-lab-v0")  # combat scripting is dev-class tooling
    pack = d.pack["pack"]
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, pack, events, tmp_path


def _pack_with(pack, **combat_over):
    """Override combat cfg on the loaded (migrated) pack — the combat
    phase carries its own cfg copy under phases[].combat."""
    p = dict(pack)
    c = dict(pack.get("combat") or {})
    eng = dict(c.get("engage") or {})
    for k, v in combat_over.items():
        if k in ("tick_budget", "spawn_grace_ticks"):
            eng[k] = v
        else:
            c[k] = v
    c["engage"] = eng
    p["combat"] = c
    p["phases"] = [dict(ph, combat=c) if ph.get("kind") == "combat"
                   else ph for ph in p["phases"]]
    return p


def _mark_completed(state_dir):
    (state_dir / "runstate.json").write_text(
        json.dumps({"completed": True}))


def _combat_out(res):
    """The combat phase's outcome row from run().outcomes."""
    outs = [o for o in res.get("outcomes") or []
            if o.get("phase") == "combat"]
    return next((o for o in outs if "combat" in o),
                outs[-1] if outs else {})


def test_prereq_refuses_without_start_completed(rig):
    """FR-803: combat sits strictly after the init baseline — the
    phase reports combat.prereq and dispatches zero writes."""
    d, game, ledger, pack, events, tmp = rig
    res = run(d, game, ledger, pack, iterations=3,
              scripted=True, stage="combat")
    out = _combat_out(res)
    assert out.get("error") == "combat.prereq"
    assert not any(e["event_type"] == "action.issued"
                   for e in events)  # zero writes


def test_combat_clears_and_restores(rig):
    """SC-803: raid spawned -> defended -> cleared -> healed -> reloaded."""
    d, game, ledger, pack, events, tmp = rig
    _mark_completed(tmp / "state")
    pack = _pack_with(pack, rounds=1, tick_budget=5000)
    res = run(d, game, ledger, pack, iterations=3,
              scripted=True, stage="combat")
    out = _combat_out(res)
    combat = out["combat"]
    assert combat["verdict"] == "cleared"
    assert combat["spawned"] == 2 and combat["cleared"] == 2
    # checkpoint saved and reloaded -> world back to pre-combat state
    assert "rimbrain-combat-checkpoint" in game.saves
    assert game.hostiles == []
    assert game.drafted == set()
    # evidence: save, spawn, draft, attack, heal, load, completion
    types = [e["event_type"] for e in events]
    assert "combat.completed" in types
    methods = [e["payload"].get("template_id") for e in events
               if e["event_type"] == "action.issued"]
    for t in ("save-game", "spawn-hostile", "draft-pawn",
              "attack-target", "heal-pawn", "load-game"):
        assert t in methods


def test_combat_timeout_records_failed(rig):
    """Budget exhausted -> verdict failed, state still restored."""
    d, game, ledger, pack, events, tmp = rig
    _mark_completed(tmp / "state")

    class StubbornSim(StartSim):
        def rpc(self, method, params=None):
            if method == "ui.attack":  # colonists never kill
                return {"ok": True, "result": {"engaged": None}}
            return super().rpc(method, params)

    g2 = StubbornSim()
    d2 = Dispatcher(g2, sink=events.append,
                    clock=lambda: "2026-01-01T00:00:00Z")
    d2.load_pack("dev-lab-v0")  # combat scripting is dev-class
    res = run(d2, g2, ledger,
              _pack_with(d2.pack["pack"], rounds=1, tick_budget=10),
              iterations=3, scripted=True, stage="combat")
    combat = _combat_out(res)["combat"]
    assert combat["rounds"][0]["verdict"] == "failed"
    assert combat["verdict"] == "failed"
    assert g2.hostiles == []  # checkpoint reload wiped the raid
