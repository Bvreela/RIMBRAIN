"""Objective/task/lock ledger (feature 007; UR-RUN-001..004).

Declared lifecycle enforced by TRANSITIONS:

    proposed -> locked -> dispatched -> verifying -> succeeded
       ^          |          |            |
       |          v          v            v
       +------ failed <- requeued/lease lapsed -> expired

Invariants:

- verifier-only success: no API but ``verify()``/``reconcile()`` can reach
  ``succeeded``, and only when the task's effect check passes against
  OBSERVED state (UR-RUN-002). Dispatch ``ok`` is never proof of effect.
- all-or-nothing expiring locks: ``acquire`` grants every declared
  resource key or none; leases expire by game tick (deterministic).
- durability: every transition appends a ``task.transition`` canonical
  envelope to ``state/tasks.jsonl`` (feature-006 EventStore); a fresh
  ledger folds the log to rebuild — memory is disposable (UR-RUN-004).
- reconcile-before-retry: ``reconcile(observed, tick)`` re-verifies open
  tasks past their lease: effect seen => succeeded; absent with attempts
  left => requeued to proposed; exhausted => failed (UR-RUN-003).
- the ledger never calls the bridge; dispatch stays the single writer.
"""

from __future__ import annotations

import json
from pathlib import Path

from .dispatch import _dotted, _op_holds
from .store import EventStore, state_dir, write_atomic

LIFECYCLE = ["proposed", "locked", "dispatched", "verifying",
             "requeued", "succeeded", "failed", "expired"]
TERMINAL = {"succeeded", "failed", "expired"}

# Declared transition table — the ONLY legal (from, to) pairs.
# "requeued" is a marker transition; the task's state becomes "proposed".
TRANSITIONS = {
    "proposed": {"locked", "expired", "failed"},
    "locked": {"dispatched", "expired", "failed"},
    "dispatched": {"verifying", "expired", "failed"},
    "verifying": {"succeeded", "requeued", "failed", "expired"},
    "requeued": {"proposed"},
}


class TaskLedger:
    """Folded task ledger over a canonical ``task.transition`` log.

    ``path`` defaults to ``state/tasks.jsonl`` under RIMBRAIN_STATE_DIR.
    ``sink`` receives every emitted envelope (drop-in for tests/loop).
    """

    def __init__(self, path: str | Path | None = None, *,
                 sink=None, clock=None):
        self._path = Path(path) if path else state_dir() / "tasks.jsonl"
        self._store = EventStore(self._path)
        self._sink = sink
        self._clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self._events = 0
        # optional pack-predicate evaluator (feature 012): effects of the
        # form {"pred": <policy predicate>} delegate to the policy engine
        self._effect_eval = None
        self.tasks: dict[str, dict] = {}
        self.locks: dict[str, dict] = {}  # resource -> {task_id, expires_tick}
        for env in self._store.load()["events"]:
            self._apply(env)

    # -- internals -----------------------------------------------------------

    def _apply(self, env: dict) -> None:
        """Fold one transition envelope into in-memory state."""
        p = env.get("payload", {})
        tid = p.get("task_id")
        if not tid:
            return
        self._events = max(self._events, env.get("sequence", 0))
        to_state = p["to_state"]
        if to_state == "reset":
            # brain-reset tombstone (UR-BRN-020): the task and its locks
            # fold away — the row replays identically on process restart
            self.tasks.pop(tid, None)
            for r in [r for r, l in self.locks.items()
                      if l["task_id"] == tid]:
                del self.locks[r]
            return
        task = self.tasks.setdefault(tid, {"task_id": tid})
        if p.get("spec"):  # propose carries the full task spec
            task.update(p["spec"])
        task["attempts"] = p.get("attempts", task.get("attempts", 0))
        task["kind"] = p.get("kind", task.get("kind"))
        task["state"] = "proposed" if to_state == "requeued" else to_state
        if to_state == "locked":
            task["lease_until"] = p.get("lease_until")
            for r in p.get("resources") or []:
                self.locks[r] = {"task_id": tid,
                                 "expires_tick": task["lease_until"]}
        elif to_state in TERMINAL or task["state"] == "proposed":
            for r in [r for r, l in self.locks.items()
                      if l["task_id"] == tid]:
                del self.locks[r]

    def _emit(self, task: dict, from_state, to_state: str,
              reason: str = "", tick: int | None = None,
              extra: dict | None = None) -> dict:
        self._events += 1
        payload = {
            "task_id": task["task_id"],
            "kind": task.get("kind", "task"),
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "attempts": task.get("attempts", 0),
            "resources": list(task.get("resources") or []),
        }
        if from_state is None:  # propose persists the full spec for rebuild
            payload["spec"] = {k: task[k] for k in
                               ("kind", "action", "resources", "effect",
                                "lease_ticks", "max_attempts", "attempts")
                               if k in task}
        if extra:
            payload.update(extra)
        envelope = {
            "schema_version": 0,
            "event_id": f"evt.task-{self._events:06d}",
            "sequence": self._events,
            "event_type": "task.transition",
            "game_tick": tick if tick is not None else task.get("tick"),
            "wall_time_utc": self._clock(),
            "source": "rimbrainagent.runtime.tasks",
            "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": payload,
            "privacy": {"classification": "internal", "redactions": []},
        }
        self._store.append(envelope)
        if self._sink is not None:
            self._sink(envelope)
        self._apply(envelope)
        return envelope

    def _transition(self, task_id: str, to_state: str, reason: str = "",
                    tick: int | None = None,
                    extra: dict | None = None) -> dict:
        task = self.tasks[task_id]
        cur = task["state"]
        if to_state not in TRANSITIONS.get(cur, set()):
            return {"ok": False, "error": {
                "code": "task.illegal_transition",
                "message": f"{cur} -> {to_state} not in transition table",
                "details": {"task_id": task_id, "from": cur, "to": to_state}}}
        return {"ok": True, "event": self._emit(task, cur, to_state,
                                                reason, tick, extra)}

    def _prune_locks(self, tick: int) -> None:
        for r, lock in list(self.locks.items()):
            exp = lock.get("expires_tick")
            if exp is not None and exp <= tick:
                del self.locks[r]

    def _check_effect(self, task: dict, observed: dict):
        """True effect holds / False fails / None inconclusive (missing)."""
        eff = task.get("effect")
        if not eff:
            return None
        if isinstance(eff, dict) and "pred" in eff \
                and self._effect_eval is not None:
            return bool(self._effect_eval(eff, observed))
        val = _dotted(observed, eff["field"])
        if val is None:
            return None
        return bool(_op_holds(eff["op"], val, eff["value"]))

    # -- public API -----------------------------------------------------------

    def propose(self, task: dict, tick: int | None = None) -> dict:
        """Register a task. Duplicate live task_ids refused."""
        tid = task.get("task_id")
        if not tid:
            return {"ok": False, "error": {"code": "task.no_id",
                                           "message": "task_id required"}}
        existing = self.tasks.get(tid)
        if existing and existing.get("state") not in TERMINAL:
            return {"ok": False, "error": {
                "code": "task.duplicate",
                "message": f"{tid} already live ({existing['state']})"}}
        task.setdefault("attempts", 0)
        task.setdefault("max_attempts", 3)
        task.setdefault("resources", [])
        task["tick"] = tick
        self.tasks[tid] = task
        env = self._emit(task, None, "proposed", "proposed", tick)
        return {"ok": True, "event": env}

    def acquire(self, task_id: str, tick: int) -> dict:
        """All-or-nothing lock of the task's resource keys (tick expiry)."""
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": {"code": "task.unknown"}}
        self._prune_locks(tick)
        resources = task.get("resources") or []
        conflicts = [r for r in resources
                     if r in self.locks
                     and self.locks[r]["task_id"] != task_id]
        if conflicts:
            return {"ok": False, "error": {
                "code": "task.lock_conflict",
                "message": "resources held",
                "details": {"conflicts": conflicts}}}
        lease_until = tick + task.get("lease_ticks", 0)
        res = self._transition(task_id, "locked", "acquired", tick,
                               extra={"lease_until": lease_until})
        if res.get("ok"):
            task["lease_until"] = lease_until
        return res

    def mark_dispatched(self, task_id: str, ok: bool = True,
                        tick: int | None = None) -> dict:
        """locked -> dispatched (or failed on dispatch error). NEVER sets
        succeeded — that requires verify() seeing the effect."""
        return self._transition(
            task_id, "dispatched" if ok else "failed",
            "dispatched" if ok else "dispatch_failed", tick)

    def verify(self, task_id: str, observed: dict,
               tick: int | None = None) -> dict:
        """Verifier. effect present -> succeeded; absent -> stays verifying;
        field missing -> inconclusive (fail-closed). dispatched tasks are
        first wound to verifying."""
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": {"code": "task.unknown"}}
        st = task.get("state")
        if st == "dispatched":
            self._transition(task_id, "verifying", "verify_window", tick)
            st = "verifying"
        if st != "verifying":
            return {"ok": False, "error": {
                "code": "task.not_verifying",
                "message": f"state {st} not verifiable"}}
        verdict = self._check_effect(task, observed)
        if verdict is True:
            return self._transition(task_id, "succeeded",
                                    "effect_observed", tick)
        return {"ok": True,
                "verdict": "effect_absent" if verdict is False
                else "inconclusive"}

    def fail(self, task_id: str, reason: str,
             tick: int | None = None) -> dict:
        return self._transition(task_id, "failed", reason, tick)

    def reconcile(self, observed: dict, tick: int) -> dict:
        """Re-verify open tasks past lease BEFORE retry (UR-RUN-003).

        dispatched/verifying past lease: effect present -> succeeded;
        absent + attempts left -> requeued (-> proposed); exhausted ->
        failed; field missing -> inconclusive (stays). proposed/locked
        past lease -> expired. Prunes expired locks; stamps cursor.
        """
        self._prune_locks(tick)
        outcomes = []
        for tid, task in list(self.tasks.items()):
            st = task.get("state")
            if st in TERMINAL:
                continue
            lease = task.get("lease_until")
            if st in ("dispatched", "verifying"):
                if lease is not None and lease > tick:
                    continue  # still inside its verify window
                verdict = self._check_effect(task, observed)
                if verdict is True:
                    if st == "dispatched":
                        self._transition(tid, "verifying",
                                         "verify_window", tick)
                    self._transition(tid, "succeeded",
                                     "effect_observed", tick)
                    outcomes.append({"task_id": tid, "to": "succeeded"})
                elif verdict is False:
                    task["attempts"] = task.get("attempts", 0) + 1
                    if st == "dispatched":
                        self._transition(tid, "verifying",
                                         "verify_window", tick)
                    if task["attempts"] >= task.get("max_attempts", 3):
                        self._transition(tid, "failed",
                                         "attempts_exhausted", tick)
                        outcomes.append({"task_id": tid, "to": "failed"})
                    else:
                        self._transition(tid, "requeued",
                                         "effect_absent_retry", tick)
                        outcomes.append({"task_id": tid, "to": "requeued"})
                else:
                    outcomes.append({"task_id": tid, "to": "inconclusive"})
            elif st in ("proposed", "locked"):
                if lease is not None and lease <= tick:
                    self._transition(tid, "expired", "lease_expired", tick)
                    outcomes.append({"task_id": tid, "to": "expired"})
        write_atomic(self._path.parent / "cursor.json", json.dumps(
            {"last_reconciled_seq": self._events,
             "last_tick": tick}, sort_keys=True).encode() + b"\n")
        write_atomic(self._path.parent / "locks.json", json.dumps(
            self.locks, sort_keys=True).encode() + b"\n")
        return {"ok": True, "outcomes": outcomes,
                "tick": tick, "seq": self._events}

    def reset_ns(self, *prefixes: str, tick: int | None = None) -> int:
        """Tombstone every task under the given id namespaces (UR-BRN-020
        brain reset). Each emits a durable `to_state: reset` row — the
        tombstone folds in `_apply`, so the task and its locks vanish now
        AND on every replay after process restart. The next `propose`
        under the same id starts a clean lifecycle."""
        n = 0
        for tid in [t for t in self.tasks if t.startswith(prefixes)]:
            task = self.tasks[tid]
            self._emit(task, task.get("state"), "reset", "brain.reset",
                       tick)
            n += 1
        return n
