# Tasks: Objective/Task/Workflow/Lock Model (007)

**Inputs**: `spec.md`, `plan.md` | **Feature**: `specs/007-objective-task-model`

## Phase 1: Contracts

- [x] T119 `components/contracts/schemas/events/types/task.transition.schema.json`: payload `{task_id, kind, from_state, to_state, reason, attempts, game_tick?}` â€” `to_state` enum of lifecycle states, `additionalProperties: false`; register native in `event-map.yaml`; corpus `ev__task.transition.valid.01.json` + 2 invalid (unknown `to_state`, missing `task_id`) (FR-607/608)

## Phase 2: Ledger

- [x] T120 `components/runtime/src/runtime/tasks.py`: `TaskLedger(path=None)` â€” `propose(task)` (task: `{task_id, kind, action, resources[], effect{field,op,value}, lease_ticks, max_attempts}`), transition table enforcement (illegal â†’ refuse, zero events), `acquire` (all-or-nothing, tick-expiry prune), `mark_dispatched`, `verify(observed)` (verifier-only `succeeded`, inconclusive stays `verifying`), `fail`, `reconcile(observed, tick)` (succeeded/requeued/failed per effect+attempts), `task.transition` envelopes â†’ `EventStore` `state/tasks.jsonl`, fold-on-open rebuild, `cursor.json` via `write_atomic` (FR-601..605, UR-RUN-001..004)

## Phase 3: Wiring

- [x] T121 `loop.py`: optional `ledger` param on `run_loop`/`main` â€” `ledger.reconcile(state, tick)` before reflex each poll + cursor stamp; absent ledger = unchanged (FR-606, UR-RUN-001 spine order)

## Phase 4: Tests + Polish

- [x] T122 [P] `tests/test_tasks.py`: happy-path lifecycle, illegal-transition matrix (zero events), verifier-only success incl. inconclusive-missing-field, lock atomicity + expiry, forced-restart fold equivalence, reconcile verdicts (succeeded/requeued/failed), determinism (same log+state+tick â‡’ same outcome), loop wiring reconcile-before-attend (SC-601..605)
- [x] T123 Polish: INDEX row 007, runtime README tasks section, AGENTS.md phase note, validate_components
