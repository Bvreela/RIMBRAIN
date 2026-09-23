"""Cycle-runner tests (feature 010): checkpoint once, reload per iter,
start->combat->improve ordering, per-cycle ledger namespaces."""

import pathlib

import pytest

from runtime.dispatch import Dispatcher
from runtime.store import EventStore
from runtime.cycle import run_cycle

from test_startmode import StartSim


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    store = EventStore(tmp_path / "state" / "events.jsonl")

    def sink(env):
        events.append(env)
        store.append(env)

    d = Dispatcher(game, sink=sink,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    return d, game, store, events, tmp_path


def _issued(events, template, name):
    return [e for e in events if e["event_type"] == "action.issued"
            and e["payload"]["template_id"] == template
            and e["payload"]["params"].get("name") == name]


def test_cycle_runs_ordered_phases(rig):
    """SC-801: save once -> per iter [load, start, combat, improve]."""
    d, game, store, events, tmp = rig
    pack = d.pack["pack"]
    pack["cycle"]["start_iterations"] = 40
    res = run_cycle(d, game, pack, store, iterations=2,
                    state_root=tmp / "state")
    assert res["ok"]
    assert len(res["iterations"]) == 2
    # cycle checkpoint saved once, loaded every iteration (combat's own
    # checkpoint save/loads are a separate name)
    assert len(_issued(events, "save-game", "rimbrain-cycle")) == 1
    assert len(_issued(events, "load-game", "rimbrain-cycle")) == 2
    # per-iteration namespaces exist (fresh ledger per reload)
    assert (tmp / "state" / "cycle-000").is_dir()
    assert (tmp / "state" / "cycle-001").is_dir()
    # cycle.completed evidence per iteration
    cyc = [e for e in events if e["event_type"] == "cycle.completed"]
    assert len(cyc) == 2
    assert cyc[0]["payload"]["phases"]["start"] == "completed"
    assert cyc[0]["payload"]["phases"]["combat"] in ("cleared", "failed")
    assert cyc[0]["payload"]["phases"]["improve"] in (
        "noop", "promoted", "rejected", "deferred")


def test_cycle_reuses_checkpoint(rig):
    """Second run finds the existing save — no re-save needed."""
    d, game, store, events, tmp = rig
    pack = d.pack["pack"]
    pack["cycle"]["start_iterations"] = 40
    run_cycle(d, game, pack, store, iterations=1, state_root=tmp / "state")
    saves1 = len(_issued(events, "save-game", "rimbrain-cycle"))
    run_cycle(d, game, pack, store, iterations=1, state_root=tmp / "state")
    saves2 = len(_issued(events, "save-game", "rimbrain-cycle"))
    assert saves2 == saves1 == 1  # checkpoint found via game.list_saves


def test_cycle_evidence_accumulates(rig):
    """Events from both iterations land in the shared canonical store."""
    d, game, store, events, tmp = rig
    pack = d.pack["pack"]
    pack["cycle"]["start_iterations"] = 40
    run_cycle(d, game, pack, store, iterations=2, state_root=tmp / "state")
    loaded = store.load()["events"]
    cyc = [e for e in loaded if e["event_type"] == "cycle.completed"]
    assert len(cyc) == 2
