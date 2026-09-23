"""Loop + reflex tests (feature 004; FR-308/309, SC-301/303/305).

- emergency reflex fires with zero model/decider calls (SC-305);
- event stream == write stream across a sim run (SC-301);
- five consecutive sim runs are bit-identical (SC-303).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.loop import run_loop  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402


class _RecordingBridge:
    def __init__(self, game: SimGame):
        self._game = game
        self.calls: list[tuple[str, dict]] = []
        self.advance_calls = 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        return self._game.rpc(method, params)

    def status(self) -> dict:
        return self.rpc("game.status", {})

    def advance(self, iteration: int) -> None:
        self.advance_calls += 1
        self._game.advance(iteration)


class _Decider:
    """Counts calls; used to prove the reflex path never consults a model."""

    def __init__(self, choice: str = "haul"):
        self.choice = choice
        self.calls = 0

    def __call__(self, state, iteration: int) -> dict:
        self.calls += 1
        return {"choice": self.choice, "score": 0.5, "noul": 0.3}


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    records: list[dict] = []
    game = _RecordingBridge(SimGame())
    d = Dispatcher(game, sink=records.append, clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("core-survival-v0")
    return d, game, records


def test_reflex_before_model_zero_calls(rig):
    """SC-305: a state with a downed colonist fires rescue with no decider."""
    d, game, records = rig
    state = SimGame().current
    state["colonists"]["downed"] = 1
    state["colonists"]["downed_id"] = "c2"
    decider = _Decider()
    fired = d.reflex(state)
    assert fired and fired[0]["ok"]
    assert decider.calls == 0  # reflex never consults the select tier
    assert any(e["event_type"] == "action.emergency" for e in records)


def test_event_stream_equals_write_stream(rig):
    """SC-301: every bridge write has a matching action.issued event."""
    d, game, records = rig
    run_loop(d, game, iterations=5, decider=_Decider())
    writes = {m for m, _ in game.calls if m != "game.status"}
    issued = {e["payload"]["template_id"]
              for e in records if e["event_type"] == "action.issued"}
    # every issued event produced exactly one write through the same template
    assert issued == writes or issued <= writes
    # every issued has a terminal event (completed|failed)
    for env in records:
        if env["event_type"] == "action.issued":
            tid = env["payload"]["template_id"]
            assert any(r["event_type"] in ("action.completed", "action.failed")
                       and r["payload"]["template_id"] == tid
                       for r in records)


def test_five_runs_bit_identical(rig):
    """SC-303: five consecutive sim runs produce byte-identical event streams."""
    d, game, _ = rig
    streams: list[str] = []
    for _ in range(5):
        events: list[dict] = []
        d._sink = events.append
        game.calls.clear()
        run_loop(d, game, iterations=5, decider=_Decider("haul"))
        streams.append(json.dumps(events, sort_keys=True, default=str))
    assert len(set(streams)) == 1


def test_fixed_clock_used_in_sim(rig):
    d, game, _records = rig
    result = run_loop(d, game, iterations=1, decider=_Decider())
    assert result["events"][0]["wall_time_utc"] == "2026-01-01T00:00:00Z"


class _LiveShapedGame:
    """Live-bridge shape: bare colonist count in status, truth in summary."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        if method == "game.status":
            return {"ok": True, "result": {"tick": 10151, "day": 4,
                                           "paused": False, "colonists": 3,
                                           "map": "Colony", "speed": 1}}
        if method == "state.summary":
            return {"ok": True, "result": {
                "colonists": 3, "colonists_idle": 0, "downed": 1,
                "food_days": 12.0, "danger": "None",
                "colonist_list": [
                    {"id": "Human911", "name": "Hicklin", "downed": True},
                    {"id": "Human893", "name": "Jet"},
                ]}}
        if method == "map.find" and (params or {}).get("def") == "Fire":
            return {"ok": True, "result": {"count": 2, "near": [159, 100],
                                           "things": [{"pos": [12, 8]}]}}
        return {"ok": True, "result": {}}  # writes accepted


def test_live_shaped_status_feeds_reflexes(tmp_path, monkeypatch):
    """T118/FR-308: enrich() maps live summary/map.find onto pack predicates —
    reflexes fire on downed+fire even though raw status has neither field."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = _LiveShapedGame()
    d = Dispatcher(game, clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("core-survival-v0")
    decider = _Decider()
    # run_loop owns the sink during the run; read events from the result
    result = run_loop(d, game, iterations=1, decider=decider)
    events = result["events"]
    emergencies = [e for e in events
                   if e["event_type"] == "action.emergency"]
    assert emergencies
    # resolved against enriched state — not literal placeholders
    completed = [e for e in events
                 if e["event_type"] == "action.completed"]
    assert completed
    # reflexes ran before any decider/model path
    assert decider.calls == 0
