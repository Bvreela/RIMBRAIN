# Implementation Plan: Objective/Task/Workflow/Lock Model

**Branch**: `007-objective-task-model` | **Spec**: `specs/007-objective-task-model/spec.md`

## Summary

`runtime/tasks.py` — `TaskLedger` implementing the declared lifecycle over a `task.transition` canonical event log (`state/tasks.jsonl` via feature-006 `EventStore`), all-or-nothing tick-expiring resource locks, verifier-only success via `{field, op, value}` effect specs reusing `dispatch._dotted`/`_op_holds`, atomic `cursor.json`, and optional `run_loop` reconcile-before-attend wiring.

## Technical Context

- `store.EventStore` + `write_atomic` already provide canonical append + atomic snapshot.
- `dispatch._dotted(state, path)` and `_op_holds(op, observed, expected)` already implement dotted lookup + predicate ops — reuse for effect checks.
- Envelope shape: mirror `Dispatcher._emit` (schema_version, event_id, sequence, event_type, game_tick, wall_time_utc, source, correlation, revisions, payload, privacy).
- `run_loop` polls status → reflex → decision; ledger slot inserts reconcile before reflex.

## Constitution Check — PASS

Ledger writes only canonical files; never calls the bridge (single writer preserved). Fail-closed on inconclusive verification. Flat files authoritative.

## Structure

```
components/contracts/schemas/events/types/task.transition.schema.json
components/contracts/registry/event-map.yaml            native: task.transition
components/contracts/examples/{valid,invalid}/ev__task.transition.*
components/runtime/src/runtime/tasks.py                 TaskLedger + transitions + locks + cursor
components/runtime/src/runtime/loop.py                  optional ledger= reconcile wiring
components/runtime/tests/test_tasks.py                  lifecycle/locks/verify/restart/property tests
```

## Lifecycle

```
proposed → locked → dispatched → verifying → succeeded
    ↑         |          |            |
    |         v          v            v
    +--- requeued ← expired/lease-lapsed → failed
terminal: succeeded | failed | expired  (expired = lease lapsed before dispatch)
```

Declared table (exhaustive):

| from | to |
|---|---|
| proposed | locked, expired |
| locked | dispatched, expired |
| dispatched | verifying, expired |
| verifying | succeeded, requeued, failed, expired |
| requeued | proposed |

`requeued` is a transition marker — the task's state becomes `proposed` (attempts+1).

## Decisions

- **Single `task.transition` event type** with `{task_id, kind, from_state, to_state, reason, attempts}` — one schema covers the whole graph; granular per-state types would add six schemas with no extra evidence value.
- **Tick-based lease expiry**, never wall clock — deterministic under replay.
- **Effect spec reuses dispatcher predicates** — `{field, op, value}` via `_dotted`/`_op_holds`; missing field ⇒ inconclusive ⇒ stays `verifying` (fail-closed).
- **Locks live in the ledger** (folded from `task.transition` + held in memory per instance), snapshotted to `locks.json` for observability; the log remains authoritative.
- **Cursor is disposable bookkeeping** — `cursor.json` records `{last_reconciled_seq, last_tick}`; reconcile always replays from the log.

## Phases

1. Contracts: `task.transition` schema, event-map entry, corpus examples.
2. `tasks.py`: TaskLedger — propose/acquire/dispatch/verify/fail/expire + fold + reconcile + cursor.
3. `loop.py`: optional `ledger` param — reconcile before attend each poll.
4. Tests + polish (INDEX, README, AGENTS, validators).
