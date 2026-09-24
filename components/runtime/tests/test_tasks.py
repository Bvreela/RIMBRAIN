"""Task ledger tests (feature 007; FR-601..606, SC-601..605).

- declared lifecycle; illegal transitions refuse with zero events;
- verifier-only success (dispatch ok is never success);
- all-or-nothing expiring locks;
- forced-restart rebuild from tasks.jsonl alone;
- reconcile verdicts: succeeded / requeued / failed / expired;
- loop wiring: reconcile precedes attend.
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
from runtime.simgame import SimGame  # noqa: E402
from runtime.tasks import TaskLedger, TRANSITIONS, TERMINAL  # noqa: E402


def _task(tid="task.t1", **kw) -> dict:
    t = {"task_id": tid, "kind": "firefight",
         "action": {"template_id": "firefight",
                    "params": {"pawn": "p1", "job": "Firefight",
                               "target": [10, 10]}},
         "resources": ["pawn:p1", "cell:10,10"],
         "effect": {"field": "map.fires", "op": "eq", "value": 0},
         "lease_ticks": 5, "max_attempts": 2}
    t.update(kw)
    return t


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    return TaskLedger(tmp_path / "tasks.jsonl")


def test_happy_path_lifecycle(ledger):
    """proposed -> locked -> dispatched -> verifying -> succeeded."""
    ledger.propose(_task(), tick=0)
    assert ledger.tasks["task.t1"]["state"] == "proposed"
    assert ledger.acquire("task.t1", tick=0)["ok"]
    assert ledger.tasks["task.t1"]["state"] == "locked"
    assert ledger.mark_dispatched("task.t1", tick=1)["ok"]
    assert ledger.tasks["task.t1"]["state"] == "dispatched"
    # effect absent -> not succeeded
    r = ledger.verify("task.t1", {"map": {"fires": 3}}, tick=1)
    assert r["verdict"] == "effect_absent"
    assert ledger.tasks["task.t1"]["state"] == "verifying"
    # effect present -> succeeded
    r = ledger.verify("task.t1", {"map": {"fires": 0}}, tick=2)
    assert r["ok"] and ledger.tasks["task.t1"]["state"] == "succeeded"


def test_illegal_transitions_refused_zero_events(ledger):
    """SC-601: every illegal (from,to) refuses and emits nothing."""
    ledger.propose(_task(), tick=0)
    n = len(ledger._store.load()["events"])
    # proposed may only -> locked/expired/failed
    for to in ("dispatched", "verifying", "succeeded", "requeued"):
        r = ledger._transition("task.t1", to)
        assert not r["ok"] and r["error"]["code"] == "task.illegal_transition"
    assert len(ledger._store.load()["events"]) == n  # zero events emitted
    # terminal -> anything refused
    ledger.acquire("task.t1", tick=0)
    ledger.mark_dispatched("task.t1", tick=0)
    ledger.verify("task.t1", {"map": {"fires": 0}}, tick=0)
    assert ledger.tasks["task.t1"]["state"] == "succeeded"
    n = len(ledger._store.load()["events"])
    for to in TRANSITIONS:
        assert not ledger._transition("task.t1", to)["ok"]
    assert len(ledger._store.load()["events"]) == n


def test_verifier_only_success(ledger):
    """FR-602/UR-RUN-002: no public path but verify reaches succeeded."""
    ledger.propose(_task(), tick=0)
    ledger.acquire("task.t1", tick=0)
    ledger.mark_dispatched("task.t1", tick=0)
    assert ledger.tasks["task.t1"]["state"] == "dispatched"  # NOT succeeded
    # dispatched -> succeeded is not even a legal transition
    assert not ledger._transition("task.t1", "succeeded")["ok"]
    # missing effect field -> inconclusive, stays verifying
    r = ledger.verify("task.t1", {"map": {}} , tick=1)
    assert r["verdict"] == "inconclusive"
    assert ledger.tasks["task.t1"]["state"] == "verifying"


def test_locks_all_or_nothing_and_expiry(ledger):
    """SC-603/604: conflict grants nothing; expiry frees the resource."""
    ledger.propose(_task("a"), tick=0)
    ledger.propose(_task("b", resources=["cell:10,10", "cell:3,4"]), tick=0)
    assert ledger.acquire("a", tick=0)["ok"]
    before = dict(ledger.locks)
    r = ledger.acquire("b", tick=0)
    assert not r["ok"] and r["error"]["code"] == "task.lock_conflict"
    assert ledger.locks == before  # zero entries changed
    assert ledger.tasks["b"]["state"] == "proposed"
    # expiry: lease_ticks=5, expires at tick 5 -> free at tick 5
    assert ledger.acquire("b", tick=5)["ok"]
    assert ledger.tasks["b"]["state"] == "locked"


def test_requeue_respects_transition(ledger):
    """requeued marker lands the task back in proposed."""
    ledger.propose(_task(), tick=0)
    ledger.acquire("task.t1", tick=0)
    ledger.mark_dispatched("task.t1", tick=0)
    ledger.verify("task.t1", {"map": {"fires": 9}}, tick=1)
    r = ledger.reconcile({"map": {"fires": 9}}, tick=10)
    assert r["outcomes"] == [{"task_id": "task.t1", "to": "requeued"}]
    assert ledger.tasks["task.t1"]["state"] == "proposed"
    assert ledger.tasks["task.t1"]["attempts"] == 1


def test_forced_restart_rebuilds_from_log(tmp_path, monkeypatch):
    """SC-602: kill mid-flight; fresh ledger folds tasks.jsonl alone."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    path = tmp_path / "tasks.jsonl"
    l1 = TaskLedger(path)
    l1.propose(_task(), tick=0)
    l1.acquire("task.t1", tick=0)
    l1.mark_dispatched("task.t1", tick=1)
    del l1  # crash: no graceful shutdown
    l2 = TaskLedger(path)
    assert l2.tasks["task.t1"]["state"] == "dispatched"
    assert l2.tasks["task.t1"]["effect"]["field"] == "map.fires"
    assert l2.locks["pawn:p1"]["task_id"] == "task.t1"
    # reconcile on the fresh instance: effect observed -> succeeded
    r = l2.reconcile({"map": {"fires": 0}}, tick=10)
    assert r["outcomes"] == [{"task_id": "task.t1", "to": "succeeded"}]
    assert l2.tasks["task.t1"]["state"] == "succeeded"
    assert (tmp_path / "cursor.json").is_file()
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert cursor["last_tick"] == 10
    assert (tmp_path / "locks.json").is_file()  # observability snapshot


def test_reconcile_exhaustion_fails(ledger):
    """UR-RUN-003: absent effect + exhausted attempts -> failed."""
    ledger.propose(_task(), tick=0)
    ledger.acquire("task.t1", tick=0)
    ledger.mark_dispatched("task.t1", tick=0)
    for tick in (10, 20):
        ledger.reconcile({"map": {"fires": 5}}, tick)
        if ledger.tasks["task.t1"]["state"] == "proposed":
            ledger.acquire("task.t1", tick)
            ledger.mark_dispatched("task.t1", tick)
    ledger.reconcile({"map": {"fires": 5}}, tick=30)
    assert ledger.tasks["task.t1"]["state"] == "failed"


def test_deterministic_fold(tmp_path, monkeypatch):
    """SC-605: same log -> identical task map on two fresh ledgers."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    path = tmp_path / "tasks.jsonl"
    l1 = TaskLedger(path)
    l1.propose(_task("x"), tick=0)
    l1.propose(_task("y", resources=[]), tick=0)
    l1.acquire("x", tick=0)
    del l1
    a, b = TaskLedger(path), TaskLedger(path)
    assert json.dumps(a.tasks, sort_keys=True) == \
        json.dumps(b.tasks, sort_keys=True)
    assert a.locks == b.locks


def test_loop_reconcile_before_attend(tmp_path, monkeypatch):
    """FR-606: reconcile precedes any dispatch — unified run() (017)."""
    from runtime.loop import run
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = SimGame()
    events: list[dict] = []
    d = Dispatcher(game, clock=lambda: "2026-01-01T00:00:00Z",
                   sink=events.append)
    d.load_pack("core-survival-v0")
    led = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                     sink=events.append)
    # stale task whose effect is observed -> reconciled to succeeded
    led.propose(_task("stale", resources=[], lease_ticks=0), tick=0)
    led.acquire("stale", tick=0)
    led.mark_dispatched("stale", tick=0)
    result = run(d, game, led, d.pack["pack"], iterations=1)
    assert "reconcile" in result["outcomes"][0]
    assert led.tasks["stale"]["state"] == "succeeded"  # map.fires==0 at t0
    types = [e["event_type"] for e in events]
    assert "task.transition" in types


def test_event_envelope_shape(ledger):
    """FR-608: transitions are canonical envelopes flowable to the store."""
    ledger.propose(_task(), tick=7)
    env = ledger._store.load()["events"][0]
    for k in ("schema_version", "event_id", "sequence", "event_type",
              "game_tick", "wall_time_utc", "source", "payload", "privacy"):
        assert k in env
    assert env["event_type"] == "task.transition"
    assert env["game_tick"] == 7
    p = env["payload"]
    assert p["from_state"] is None and p["to_state"] == "proposed"
    assert p["spec"]["effect"]["field"] == "map.fires"
