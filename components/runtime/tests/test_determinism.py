"""Sim determinism tests (feature 017; FR-1420): repeated sim episodes
produce byte-identical event streams, and the select stage resolves
answers from pack fallback only — zero endpoint resolution attempts
(SC-303 carried forward to the unified run)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.loop import run  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402
from runtime import select as _select  # noqa: E402

CLOCK = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


def _episode(tmp_path, name):
    events: list[dict] = []
    game = SimGame()
    d = Dispatcher(game, sink=events.append, clock=CLOCK)
    d.load_pack("core-survival-v0")
    ledger = TaskLedger(tmp_path / name / "tasks.jsonl",
                        sink=events.append)
    run(d, game, ledger, d.pack["pack"], iterations=5,
        clock=CLOCK)
    return json.dumps(events, sort_keys=True, default=str)


def test_sim_episodes_bit_identical(tmp_path):
    """SC-303: five consecutive sim runs -> one byte-identical stream."""
    streams = {_episode(tmp_path, f"run{i}") for i in range(5)}
    assert len(streams) == 1


def test_sim_never_resolves_an_endpoint(tmp_path, monkeypatch):
    """FR-1420/1425: the sim path must not touch endpoint resolution —
    fallback answers come from the pack only."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    calls = {"n": 0}

    def boom(sel, state, questions):
        calls["n"] += 1
        return {"ok": False, "error": {"code": "test.no_endpoint"}}

    monkeypatch.setattr(_select, "_default_caller", boom)
    events: list[dict] = []
    game = SimGame()
    d = Dispatcher(game, sink=events.append, clock=CLOCK)
    d.load_pack("core-survival-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    res = run(d, game, ledger, d.pack["pack"], iterations=5,
              clock=CLOCK)
    assert res["ok"]
    assert calls["n"] == 0   # caller=None path — never wired
