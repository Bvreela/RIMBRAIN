"""Transparency-view tests (feature 013; FR-1101..1105, SC-1101..1105)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.startmode import run_start  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402
from runtime import views  # noqa: E402

from test_startmode import StartSim  # noqa: E402


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, d.pack["pack"], events, tmp_path / "state"


def test_views_written_each_poll(rig):
    """SC-1101: planning.md + actions.md + decisions.jsonl exist and
    reflect the run."""
    d, game, ledger, cfg, _ev, sdir = rig
    res = run_start(d, game, ledger, cfg, iterations=30)
    assert res["completed"]
    planning = json.loads((sdir / "planning.json").read_text())
    assert planning["mode"] == "start"
    assert planning["complete"] is True
    ids = [g["id"] for g in planning["goals"]]
    # pack order preserved — site first, overflow last phase; govern
    # goals render after the phase list
    n_phases = len(cfg["start"]["phases"])
    assert ids[0] == "site" and ids[n_phases - 1] == "overflow"
    assert ids[n_phases:] == [
        f"govern.{g['id']}" for g in cfg["govern"]["goals"]]
    assert (sdir / "planning.md").is_file()
    assert (sdir / "actions.md").is_file()
    rows = [json.loads(l) for l in
            (sdir / "decisions.jsonl").read_text().splitlines()]
    assert rows and all({"tick", "poll", "source", "template",
                         "params", "ok"} <= set(r) for r in rows)
    # sources trace to pack elements (SC-1103)
    assert all(r["source"].startswith(("rule:", "phase:"))
               for r in rows)


def test_goal_order_follows_pack(rig):
    """SC-1102: reordering the pack changes the rendered goal order."""
    d, game, ledger, cfg, _ev, sdir = rig
    phases = cfg["start"]["phases"]
    # move last phase to front — data edit only, no code change
    phases.insert(0, phases.pop())
    run_start(d, game, ledger, cfg, iterations=5)
    planning = json.loads((sdir / "planning.json").read_text())
    assert planning["goals"][0]["id"] == phases[0]["id"]


def test_render_failure_does_not_abort(rig, monkeypatch):
    """SC-1105: a view exception mid-poll never interrupts control."""
    d, game, ledger, cfg, _ev, _sdir = rig
    calls = {"n": 0}
    real = views.write_planning

    def boom(*a, **kw):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("disk full")
        return real(*a, **kw)

    monkeypatch.setattr(views, "write_planning", boom)
    res = run_start(d, game, ledger, cfg, iterations=30)
    assert res["completed"]  # control path unaffected


def test_decision_rows_match_dispatches(rig):
    """Every decisions.jsonl row corresponds to a real dispatched write."""
    d, game, ledger, cfg, events, sdir = rig
    run_start(d, game, ledger, cfg, iterations=30)
    rows = [json.loads(l) for l in
            (sdir / "decisions.jsonl").read_text().splitlines()]
    issued = [e for e in events if e["event_type"] == "action.issued"]
    assert len(rows) == len(issued)
    # poll stamps are monotonic
    polls = [r["poll"] for r in rows]
    assert polls == sorted(polls)


def test_matrix_window_caps(rig, tmp_path):
    """actions.md renders only the trailing window (FR-1102)."""
    dpath = tmp_path / "decisions.jsonl"
    rows = [{"tick": t, "poll": t, "source": "rule:x",
             "template": "noop", "params": {}, "ok": True}
            for t in range(40)]
    views.record_decisions(dpath, rows)
    views.write_actions(tmp_path, dpath, window=10)
    md = (tmp_path / "actions.md").read_text()
    assert md.count("| rule:x |") == 10
    assert "last 10 of 40" in md


def test_goal_rows_carry_effect(rig):
    """Goals render the pack's declared success condition (detail)."""
    d, game, ledger, cfg, _ev, sdir = rig
    from runtime import views
    from runtime.startmode import StartMode

    mode = StartMode(cfg, ledger)
    snap = views.start_snapshot(mode, ledger, {"tick": 1})
    beds = next(g for g in snap["goals"] if g["id"] == "beds")
    assert beds["effect"] and "beds_total" in beds["effect"]
