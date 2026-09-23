# Tasks: Checkpoint-Reload Retry Loops (feature 003)

## Phase 1: Contracts

- [x] T046 [P] Create `components/contracts/schemas/runtime/retry-config.schema.json` — RetryConfig
  contract object (schema_version, config_id, window_ticks|window_hours, max_retries, speed,
  checkpoint_family, gate_ref, mutation_space_ref, budgets) per spec FR-202
- [x] T047 [P] Create `schemas/events/types/retry.*.schema.json` for the six FR-205 event types
  (checkpoint.saved, window.started, gate.evaluated, mutation.applied, iteration.completed,
  loop.completed)

## Phase 2: Engine (components/lab)

- [x] T048 Implement `lab/bridge.py` GameCtl abstraction: `save/load/status/set_speed/list_saves`;
  `LiveBridge` (HTTP /rpc + GET /events, structured `{ok:false}` on transport errors) and
  `SimBridge` (in-memory state, deterministic tick advancement, snapshot save/load)
- [x] T049 [P] Implement `lab/gate.py` predicate evaluator: `{id, field, op, value}` over a state
  dict; ops eq/ne/gt/gte/lt/lte/contains; combinator all|any; returns GateVerdict
  `{passed, predicates[], early_exit}`
- [x] T050 [P] Implement `lab/mutations.py` mutation space: ordered `{id, apply}` list applied to a
  candidate dict; `next()` pops; invalid apply rejected; exhaustion signal
- [x] T051 Implement `lab/retryloop.py` engine: load config → guard (scored-episode reject, FR-208)
  → save checkpoint (namespaced, FR-206) → per window: advance window_ticks at speed, evaluate
  gate, early_exit | mutate+reload | exhausted → emit canonical retry.* events per iteration
  → hard budget bounds (FR-207) → reload-state verification via status tick/day (FR-210)
- [x] T052 Implement fixture exporter: completed run → fixture package per US5 contract
  (manifest.yaml sha256 members, input.jsonl iteration events, expected.jsonl verdicts)

## Phase 3: Tests + config

- [x] T053 [P] Tests `components/lab/tests/test_retryloop.py` (SimBridge, offline): early_exit at
  N<max (SC-202), exhausted at cap (SC-204), one-mutation-per-retry + invalid rejection (FR-204),
  checkpoint tick equality after reload (SC-201), scored-episode rejection (FR-208), budget abort
  (FR-207), fixture export round-trips through the US5 harness (SC-203)
- [x] T054 [P] `configs/retryloop.example.yaml` annotated example; lab README update; specs INDEX
  implemented-artifacts row
- [x] T055 Live smoke: `--mode live` against the loaded game — one checkpoint save, one window,
  gate eval, reload verification (manual verification gate, not CI)

## Phase 4: Convergence

- [x] T056 Capture the pre-run `game.status` (speed/pause) at loop start and restore it on every exit path (early_exit, exhausted, aborted, bridge error) per spec edge cases + US1/AC1 (missing)
- [x] T057 Add `GameCtl.pause()` (LiveBridge -> `game.pause`, SimBridge -> paused state) so restore and operator pause are explicit per FR-201 and the bridge inventory (partial)
