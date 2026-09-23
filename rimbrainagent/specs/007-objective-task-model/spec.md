# Feature Specification: Objective/Task/Workflow/Lock Model

**Feature Branch**: `007-objective-task-model`

**Created**: 2026-09-23

**Status**: Draft

**Input**: WP-102 (UR-RUN-001..004) — implement state machines, all-or-nothing expiring locks, verifier-only success invariant, and persisted cursors. Exit criteria: state/graph/property tests and a forced-restart trace pass.

## Purpose

Give the runtime a durable task layer above the dispatcher: tasks carry a declared lifecycle, claim resources with all-or-nothing expiring locks, and can only be marked `succeeded` by a verifier that checks the observed game state — never by a dispatch return code alone. Task transitions are canonical events persisted to the feature-006 event store, so the ledger survives process restart and pending work reconciles observed effects before any retry.

## User Stories *(mandatory)*

### User Story 1 - Declared Task Lifecycle (Priority: P1)

A `TaskLedger` manages tasks through a fixed lifecycle: `proposed → locked → dispatched → verifying → succeeded | failed | expired`, with `requeued` returning to `proposed`. Every transition is validated against the declared transition table — illegal transitions (e.g. `proposed → succeeded`, terminal → anything) are refused, fail-closed.

**Why this priority**: UR-RUN-002 demands a declared lifecycle; everything else hangs off it.

**Independent Test**: drive a task through the happy path and attempt every illegal transition; legal ones emit `task.transition` events, illegal ones return a refusal and emit nothing.

**Acceptance Scenarios**:

1. **Given** a proposed task, **When** `acquire()` succeeds, **Then** state is `locked` and a `task.transition` event records `from_state`/`to_state`.
2. **Given** any task, **When** a transition not in the table is requested, **Then** it is refused and no event is emitted.

### User Story 2 - Verifier-Only Success (Priority: P1)

A task carries an `effect` spec (`{field, op, value}` evaluated against observed state via dotted-path lookup). `mark_dispatched` records the dispatch outcome but can NEVER set `succeeded` — only `verify(task, observed)` may produce `succeeded`, and only when the effect check passes. A failed effect check leaves the task in `verifying` or routes it to `requeued`/`failed` per attempts budget.

**Why this priority**: UR-RUN-002 — "only a verifier may mark success" is the core invariant that keeps RPC `ok` from masquerading as game effect.

**Independent Test**: dispatch a task whose effect is not yet observable; assert state is not `succeeded`; supply observed state where the effect holds; assert `succeeded`.

**Acceptance Scenarios**:

1. **Given** a dispatched task with `effect: {field: map.fires, op: eq, value: 0}`, **When** `verify` runs against observed `{map: {fires: 2}}`, **Then** the task does NOT succeed.
2. **Given** the same task, **When** observed `{map: {fires: 0}}`, **Then** `verify` transitions it to `succeeded` and emits the transition.

### User Story 3 - All-or-Nothing Expiring Locks (Priority: P1)

Each task declares `resources` (string keys like `pawn:Human911`, `cell:10,10`). `acquire()` grants ALL keys or NONE — a partial conflict leaves the task in `proposed` and the lock set unchanged. Locks carry a lease (`expires_tick`); expired locks are pruned on `acquire`/`reconcile` so a crashed holder never deadlocks the colony.

**Why this priority**: UR-RUN-001 reconcile correctness — two pending tasks must never hold overlapping resources; a dead process must not hold locks forever.

**Independent Test**: two tasks sharing one resource — second acquire fails atomically; after lease expiry the resource is free again.

**Acceptance Scenarios**:

1. **Given** task A holding `pawn:X` + `cell:1,2`, **When** task B requests `cell:1,2` + `cell:3,4`, **Then** B gets nothing and no lock table entry changes for B.
2. **Given** a lock with `expires_tick <= current tick`, **When** reconcile or acquire runs, **Then** the lock is gone.

### User Story 4 - Restart Durability + Pending Reconcile (Priority: P1)

Transitions append as `task.transition` canonical events to a dedicated `EventStore` (`state/tasks.jsonl`); the ledger rebuilds by folding the log. A `cursor.json` atomic snapshot records `{last_reconciled_seq, last_tick}`. After a forced restart, `reconcile(observed, tick)` re-verifies every open task past its lease: effect observed → `succeeded`; effect absent with attempts left → `requeued` to `proposed`; attempts exhausted → `failed`.

**Why this priority**: UR-RUN-003/004 — pending work must reconcile observed effects after timeout or restart, and state must survive the process.

**Independent Test**: seed tasks mid-flight, drop the object, reopen a fresh ledger on the same files, call `reconcile` with observed state — each task lands in the correct terminal/requeued state purely from the log.

**Acceptance Scenarios**:

1. **Given** a dispatched task whose effect later appears, **When** a NEW ledger instance loads the log and reconciles, **Then** the task succeeds — nothing was held in memory.
2. **Given** a dispatched task whose effect never appears and attempts are exhausted, **When** reconciled, **Then** it ends `failed` with a recorded reason.

### User Story 5 - Loop Wiring (Priority: P2)

`run_loop` accepts an optional `ledger`; each poll runs `ledger.reconcile(state, tick)` BEFORE reflex/decision evaluation (reconcile precedes attend in the spine) and stamps the cursor. Default (no ledger) is unchanged behavior.

**Why this priority**: proves the spine ordering `reconcile → attend → route → dispatch → verify → evidence` end-to-end without forcing adoption.

**Independent Test**: sim loop with a ledger containing a stale pending task — the reconcile transition event appears in the run's event stream before any new dispatch.

## Edge Cases

- **Duplicate task_id**: proposing an existing live (non-terminal) id is refused; reusing a terminal id is allowed (fresh lineage, new correlation).
- **Missing effect field in observed state**: verify is inconclusive — task stays `verifying`, never silently succeeds or fails.
- **Lock held by expired lease vs fresh acquire**: expiry check uses the task's `expires_tick` against the supplied tick — no wall-clock dependence (deterministic).
- **Empty resources**: a task with no resource keys always acquires (vacuous all-or-nothing).
- **Cursor lag**: cursor is advisory bookkeeping; the log is authoritative — reconcile replays from the log, not the cursor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-601**: `runtime/tasks.py` `TaskLedger` enforces the declared transition table; illegal transitions refuse with zero events.
- **FR-602**: `mark_dispatched`/`requeue`/`fail` may never set `succeeded`; only `verify` with a passing effect check may. (UR-RUN-002)
- **FR-603**: `acquire` grants all declared resource keys atomically or none; locks expire by `expires_tick` and are pruned on acquire/reconcile.
- **FR-604**: `reconcile(observed, tick)` re-verifies open tasks past lease BEFORE retry; outcomes: `succeeded` (effect seen), `requeued` (absent, attempts left), `failed` (exhausted). (UR-RUN-003)
- **FR-605**: all transitions persist as `task.transition` envelopes to `state/tasks.jsonl` via `EventStore`; `TaskLedger(path)` folds the log to rebuild state; `cursor.json` written via `write_atomic`. (UR-RUN-004)
- **FR-606**: `run_loop(..., ledger=...)` runs reconcile before attend each poll and writes the cursor; absent ledger = current behavior.
- **FR-607**: `task.transition` payload schema registered native in `event-map.yaml`; corpus valid + invalid examples.
- **FR-608**: transition envelopes reuse the canonical envelope builder (schema_version/event_id/sequence/game_tick/wall_time_utc/source/privacy) so they flow through store/projection unchanged.

### Success Criteria

- **SC-601**: property test — every reachable (state, transition) pair follows the declared table; no path reaches `succeeded` except through `verify`.
- **SC-602**: forced-restart trace — a ledger killed mid-flight rebuilds identically from `tasks.jsonl` alone; reconcile produces the same verdicts as if uninterrupted.
- **SC-603**: lock atomicity — conflicting multi-resource acquire changes zero lock entries.
- **SC-604**: lock expiry — expired leases never block acquire after their tick.
- **SC-605**: determinism — identical log + identical observed state + identical tick ⇒ byte-identical fold and reconcile outcomes.

## Constraints

- Deterministic: tick-based expiry only; no wall-clock reads inside the ledger (caller supplies tick; wall time only in envelope metadata).
- Single writer preserved: the ledger never calls the bridge; it only records decisions about work. Dispatch remains the Dispatcher alone.
- Fail-closed: inconclusive verification or missing observed fields never mark success.
- Canonical flat files authoritative; the in-memory task map and cursor are rebuildable/disposable.
