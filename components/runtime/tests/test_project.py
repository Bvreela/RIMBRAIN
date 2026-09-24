"""Projection + store-wiring tests (feature 006; FR-504/505, SC-504/505).

- project() is a pure deterministic fold; rebuild is byte-identical across
  runs and derives from the log alone (SC-504);
- a sim loop run with a store sink persists every emitted event (SC-505).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import project  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.loop import run  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402
from runtime.store import EventStore  # noqa: E402

PACK = "core-survival-v0"


def _env(seq, etype, payload=None):
    return {"schema_version": 0, "event_id": f"evt-{seq}", "sequence": seq,
            "event_type": etype, "game_tick": seq,
            "wall_time_utc": "2026-01-01T00:00:00Z", "source": "t",
            "correlation": {}, "revisions": {"schema_version": 0},
            "payload": payload or {},
            "privacy": {"classification": "internal", "redactions": []}}


def test_project_deterministic_fold():
    events = [
        _env(1, "action.issued", {"template_id": "rescue",
                                  "outcome": "issued"}),
        _env(2, "action.completed", {"template_id": "rescue",
                                     "outcome": "completed"}),
        _env(3, "plan.proposed", {"plan_id": "plan.x"}),
        _env(4, "plan.reviewed", {"plan_id": "plan.x", "verdict": "approved"}),
        _env(5, "plan.accepted", {"plan_id": "plan.x"}),
    ]
    v1, v2 = project.project(events), project.project(list(events))
    assert json.dumps(v1, sort_keys=True) == json.dumps(v2, sort_keys=True)
    assert v1["total"] == 5
    assert v1["counts_by_type"]["action.issued"] == 1
    assert v1["last_action"]["outcome"] == "completed"
    assert v1["last_plan"]["verdict"] == "approved"
    assert (v1["first_seq"], v1["last_seq"]) == (1, 5)


def test_rebuild_writes_projection(tmp_path, monkeypatch):
    """SC-504: rebuild derives from the log alone, byte-stable."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    s = EventStore(tmp_path / "events.jsonl")
    s.append(_env(1, "action.issued", {"template_id": "t",
                                       "outcome": "issued"}))
    view1 = project.rebuild(s)
    view2 = project.rebuild(s)
    assert view1 == view2
    on_disk = json.loads((tmp_path / "projection.json").read_text())
    assert on_disk["total"] == 1


def test_sim_loop_persists_events(tmp_path, monkeypatch):
    """SC-505: dispatcher sink wired to the store -> events.jsonl on
    disk (ported to unified run(), feature 017)."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR",
                       str(REPO_ROOT / "components" / "rimbrain" / "packs"))
    store = EventStore(tmp_path / "events.jsonl")
    game = SimGame()
    d = Dispatcher(game, clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack(PACK)
    from runtime.tasks import TaskLedger
    ledger = TaskLedger(tmp_path / "tasks.jsonl", sink=store.append)
    # SimGame's scripted evolution fires a reflex (fire at iter 1) ->
    # guaranteed envelope writes
    run(d, game, ledger, d.pack["pack"], iterations=3,
        sink=store.append)
    on_disk = EventStore(tmp_path / "events.jsonl").load()
    assert on_disk["total"] > 0
    # every persisted line is the canonical envelope form
    assert all(e["source"].startswith("rimbrainagent.runtime")
               for e in on_disk["events"])
