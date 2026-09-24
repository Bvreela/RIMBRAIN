# Tasks: Unified Phase Engine

**Input**: Design documents from `specs/017-unified-phase-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (select-batch.md, plan-output.md, pack-schema-v1.md)

**Tests**: Included — project convention requires traceability-linked passing evidence per feature (Constitution III).

**Organization**: Tasks grouped by user story per spec.md priorities (US1=P1, US2=P2, US5=P2, US3=P3, US4=P4).

**Hard prerequisite**: Feature 016 (`specs/016-live-pack-mutation`) must be landed before implementation — `evolve.py` builds on `mutate.py`/`packmut.py`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

**Purpose**: Baseline + branch

- [ ] T001 Verify feature 016 landed: `components/runtime/tests/test_mutate.py` green, `specs/016-live-pack-mutation/spec.md` status Implemented — do not proceed if open
- [ ] T002 Create branch `feature/017-unified-phase-engine` from main (include all 016 work)
- [ ] T003 [P] Record baseline: run full suite (`cd components/runtime && uv run pytest -q`) — save pass count for regression comparison

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared substrate every story consumes — canonical observation, unified predicate dialect, pack v1 migration, run-state owner, decision-record writer

**⚠ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Implement canonical `observe(game, pack)` in `components/runtime/src/runtime/observe.py` merging `startmode.observe_start` + `planloop.enrich` + `vitals.sample` into sectioned obs `{tick, colony, pawns, map, stocks, vitals, threats}`; keep per-section keys stable for existing `@obs:` resolvers
- [ ] T005 [P] Implement `RunState` in `components/runtime/src/runtime/runstate.py` consolidating mode vars, rule state, mutation PassState, and vitals state into one owned object persisted to `state/runstate.json` (replaces `startmode.json` load/save semantics)
- [ ] T006 [P] Implement v0→v1 pack migration in `components/runtime/src/runtime/templates.py` per `contracts/pack-schema-v1.md`: `start.phases`→`phases[0]` (`id: init, prescriptive: true`), `start.exit`→`phases[0].complete`, `govern.goals`→`standing_goals`, `universal.rules`→`rules`, `emergency`→`reflexes`, `goal_options`→`options`, `jobs`/`decision_map`/`cycle` dropped; `@cfg:start.*`/`@cfg:govern.*` alias map preserved; hash computed on normalized doc; `schema_version > 1` rejected
- [ ] T007 Extend `components/contracts/schemas/runtime/pack.schema.json` for v1 shape (`phases`, `standing_goals`, `options`, `reflexes`, `rules`, `senses`, `decide`, `action_list.max_items≤20`); keep v0 documents valid through migration
- [ ] T008 Unify reflex dialect: load `emergency`/`reflexes` rules into the `policy.check` dialect in `components/runtime/src/runtime/templates.py`, make `Dispatcher.reflex` in `components/runtime/src/runtime/dispatch.py` evaluate via `policy.run_rules`/`policy.check` preserving priority order and pre-decide position, then delete `_condition`/`_op_holds`
- [ ] T009 Implement decision-record writer in `components/runtime/src/runtime/select.py` (or `store.py` helper): append `{poll, tick, phase, offered, pick, applied, fallback, shadow, inputs_hash, latency_ms}` rows to `state/decisions.jsonl`

**Checkpoint**: Foundation ready — obs contract, pack v1, single predicate dialect, RunState, decision logging all in place

---

## Phase 3: User Story 1 — One loop drives the whole colony lifecycle (P1) 🎯 MVP

**Goal**: Single run loop executes observe → reflex → decide → act → verify → reflect for the entire lifecycle; `init` = today's bootstrap semantics; standing goals hold; no subsystem handoffs

**Independent Test**: sim run: init completes bootstrap contract → standing goals hold → run continues; `test_startmode` ported suite green; `startmode.py`/`universal.py`/`run_loop`/`_live_decider` deleted with zero dangling references

### Tests for User Story 1

- [ ] T010 [P] [US1] Port `components/runtime/tests/test_startmode.py` → `components/runtime/tests/test_phase.py` against `PhaseEngine` (phase ordering, requires-gating, effect verification, exit/fix chains, retry backoff, drift freeze, standing-goal re-arm)
- [ ] T011 [P] [US1] Write `components/runtime/tests/test_pack_migration.py` — v0 `start-mode-v0` loads normalized; `emergency` rules fire in `policy.check` dialect; cfg aliases resolve; normalized hash stable across v0 file / v1 candidate

### Implementation for User Story 1

- [ ] T012 [US1] Implement `PhaseEngine` in `components/runtime/src/runtime/phase.py` — ordered `pack.phases` driver porting `StartMode` mechanics: var bindings, `_propose`/`_drive` step lifecycle, `requires`/`need` gates, ledger-verified effects, `complete` contract + `fix` fallback chains, `retry_polls` backoff; `prescriptive: true` phases run deterministic `steps`; port `completed_event` envelope emission (`start.completed`/completion events — FR-705/707 evidence feeds improve metrics)
- [ ] T013 [US1] Implement standing-goal evaluation in `components/runtime/src/runtime/phase.py` — port `_govern_step` semantics (declared order, `when` gates, effect-lapse re-arm, `govern_retry` backoff) reading `standing_goals` (+ migrated `govern.goals`)
- [ ] T014 [US1] Port the `run_start` poll body into `run()` in `components/runtime/src/runtime/loop.py` — observe (T004) → brain-reset (`brain.poll_request` + `ledger.reset_ns` reinit) → vitals sample → `ledger.reconcile` → `dispatcher.reflex` → pack `rules` via `policy.run_rules` → `mode.step`/`PhaseEngine.step` → `views.write_views` → reflect triggers — using `RunState` (T005)
- [ ] T015 [US1] Restructure `components/rimbrain/packs/start-mode-v0/pack.yaml` to schema v1 (phases/init/standing_goals/rules/reflexes/senses/decide/options/mutate/metrics) — verified loadable via T006 migration AND as native v1
- [ ] T016 [US1] Delete `components/runtime/src/runtime/universal.py`, `run_loop`/`_live_decider`/`_sim_decider` from `components/runtime/src/runtime/loop.py`, and `components/runtime/src/runtime/startmode.py` internals (leave import shim until T044); update all imports
- [ ] T045 [US1] Pack-ify combat mode per FR-1429: move `combatmode.py`'s raid-scenario behavior into a dev-class pack (`packs/dev-lab-v0` combat phases/rules using existing dev.* spawn methods); delete `components/runtime/src/runtime/combatmode.py`; verify `cycle` drives it via the unified loop under `--dev`
- [ ] T017 [US1] Update `views.py` `start_snapshot`/`planning_snapshot` → phase snapshot: current phase, phase list w/ effect holds, standing goals — same `holds` live-eval semantics

**Checkpoint**: `--mode run` sim episode completes init + holds standing goals; ported suite green; deleted modules unreferenced

---

## Phase 4: User Story 2 — Laya executes bounded action lists (P2)

**Goal**: Per-poll ≤20-candidate action list (colony + pawn scopes) → batched systemone → validated pick → single-writer dispatch; fallback on invalid/down; shadow-mode qualification

**Independent Test**: stubbed select endpoint: >20 eligibles truncate; invalid pick → fallback + `select.invalid`; endpoint down → fallback + `select.degraded`; one request per poll for all pawns; shadow logs pick but executes fallback

### Tests for User Story 2

- [ ] T018 [P] [US2] Write `components/runtime/tests/test_select.py` — candidate compile/scoring/truncation, batch rendering per `contracts/select-batch.md`, answer validation paths, fallback matrix, shadow mode, decision-record fields

### Implementation for User Story 2

- [ ] T019 [US2] Implement action-list compiler in `components/runtime/src/runtime/select.py` — enumerate satisfiable standing-goal/phase ops (colony scope) + per-pawn job options (pawn scope, idle/drafted-aware), score by pack `action_list.priority` expression, truncate to 20 (hard bound, not pack-editable)
- [ ] T020 [US2] Implement batched systemone render + answer application in `components/runtime/src/runtime/select.py` per `contracts/select-batch.md` — `q.colony` + `q.pawn.<id>` criteria keyed by candidate ids, context stats payload (colony/pawn/efficiency/plan), membership validation, `select.invalid`/`select.degraded` events, pack `fallback` resolution
- [ ] T021 [US2] Implement shadow mode in `components/runtime/src/runtime/select.py` — model pick recorded `shadow: true`, deterministic fallback dispatched, divergence count exposed for qualification
- [ ] T022 [US2] Wire decide stage into the poll loop (`components/runtime/src/runtime/loop.py`): after rules, before/instead-of direct goal drive per pack `decide.select`; `init` structural steps bypass select while `init` pawn jobs route through it (FR-1410); decision records via T009
- [ ] T046 [US2] Implement `decide.select.cadence_polls` (default 1) per FR-1430 in `components/runtime/src/runtime/select.py` — when the select endpoint lags beyond the poll window the engine skips the decision rather than queuing it; fallback continues unaffected
- [ ] T047 [US2] Implement selector-authority registry per FR-1424 in `components/runtime/src/runtime/select.py` — persist per-(model,prompt,context)-tuple rung (`shadow`/`trial`/`authority`) + divergence counts to `state/select_authority.json`; shadow→trial→authority transitions recorded as events; `decide.select` cfg may request a rung but persisted qualification evidence governs actual authority

**Checkpoint**: sim with stubbed select executes goal ops from validated picks; fallback paths proven; records in `state/decisions.jsonl`

---

## Phase 5: User Story 5 — Determinism where it matters + mode/flag surface (P2)

**Goal**: sim/CI fully deterministic (zero endpoint calls); live always model-assisted; explicit flag-interaction contract; simplified CLI

**Independent Test**: repeated sim runs emit identical event streams; test asserting zero endpoint calls in sim; flag matrix table-driven tests; `--mode start` warns+aliases

### Tests for User Story 5

- [ ] T023 [P] [US5] Write `components/runtime/tests/test_determinism.py` — repeated sim episode byte-identical event streams; endpoint-call counter asserts zero in sim
- [ ] T024 [P] [US5] Write flag-matrix tests in `components/runtime/tests/test_modes.py` — every (fair/dev × live-brain × live-mutate × boundary) combination either defined or fails closed

### Implementation for User Story 5

- [ ] T025 [US5] Enforce sim determinism: sim decider path resolves answers from pack `fallback`/`priority_head` only — no endpoint resolution attempted in sim (`components/runtime/src/runtime/select.py` + `loop.py`)
- [ ] T026 [US5] Implement `--mode run` (+ deprecated `start` alias with warning), `--stage plan|reflect` debug entries, and `--game sim|live` (sim default) orthogonal backend selection per FR-1422 in `components/runtime/src/runtime/__main__.py`; delete dead mode paths; explicit flag-interaction table with fail-closed defaults
- [ ] T027 [US5] Update `rimbrain.py` launcher defaults to `--mode run`; keep `--live-mutate` per 016

**Checkpoint**: CLI surface reduced to `run`/`cycle`/`--stage`; flag contract enforced; sim proven deterministic

---

## Phase 6: User Story 3 — Planner strategizes in the loop (P3)

**Goal**: `rimbrain.plan` fires on ~150s cadence + phase boundaries + declared events; accepted plans reorder priorities, toggle goals, promote `goal_options`; failure → last plan stands

**Independent Test**: sim clock advance past cadence → plan request fires; accepted stub plan reorders next action list; failed plan call leaves prior plan in force + degradation event; zero blocked polls during outage

### Tests for User Story 3

- [ ] T028 [P] [US3] Write `components/runtime/tests/test_planstage.py` — cadence/boundary/event triggers, gate rejections (unknown ids, bad params, dev-class), promote→goal materialization, last-plan-standing

### Implementation for User Story 3

- [ ] T029 [US3] Implement plan-stage scheduler in `components/runtime/src/runtime/planstage.py` — pack `decide.plan` triggers (cadence_s default 150, `on_phase_boundary`, `on_events`), non-blocking request, in-force plan object with staleness timestamp
- [ ] T030 [US3] Implement plan digest builder in `components/runtime/src/runtime/planstage.py` — compact obs+ledger projection per `contracts/plan-output.md` (shared digest machinery reused by evolve)
- [ ] T031 [US3] Implement plan gate + application per `contracts/plan-output.md` — id-existence, param-schema, fair-class checks; `goal_order`→priority feed into select scoring (T019); `activate`/`deactivate`; `promote` materializes `options` into run goals/phases
- [ ] T032 [US3] Convert `planloop.run_plan` into the stage entry used by `--stage plan` and the scheduler; remove its standalone promotion machinery (absorbed in Phase 7)

**Checkpoint**: planner cadence observable in sim; accepted plans measurably reorder action lists; outage causes zero stalls

---

## Phase 7: User Story 4 — One reflection pipeline (P4)

**Goal**: single digest→propose→compile→gate→candidate→boundary-promote path covering every pack surface incl. `phases`/`action_list`/`decide`/`reflexes`/`rules`; improve evidence preserved

**Independent Test**: reflection pass proposing a `phases.*` op passes the same gate as other paths; candidate promotes only at boundary; regression auto-reverts via lineage; `improve.diagnose` feeds digests

### Tests for User Story 4

- [ ] T033 [P] [US4] Port `components/runtime/tests/test_mutate.py` → `components/runtime/tests/test_evolve.py` + add phase/action-list/decide mutation round-trips and v0-path op rewriting

### Implementation for User Story 4

- [ ] T034 [US4] Create `components/runtime/src/runtime/evolve.py` — absorb `mutate.py` machinery (PassState→RunState, triggers, digest, reflect, gate, materialize, boundary) + `planloop` candidate promotion
- [ ] T035 [US4] Reduce `components/runtime/src/runtime/improve.py` to evidence functions (`diagnose`, `score`, `predict_metrics`, metrics windows); `_apply_ops`/`propose`/promotion machinery moves to `evolve.py`
- [ ] T036 [US4] Extend `components/runtime/src/runtime/packmut.py` path whitelist += `phases`, `action_list`, `decide`, `reflexes`, `rules`, `options`, `senses`, `metrics`; v0-path ops rewritten through the T006 migration map before `apply_ops`
- [ ] T037 [US4] Merge gate implementations into one (schema `validate_pack` + sealed-inventory + fair-class + budget checks); single candidate format + lineage
- [ ] T038 [US4] Wire reflect triggers into the poll loop's reflect stage (from `mutate.maybe_trigger` semantics — failure/near-failure/cadence/cooldown/budget) using `RunState`

**Checkpoint**: one pipeline mutates every pack surface; init-phase mutation round-trips through boundary promotion; duplicate gate/promote code deleted

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Views, docs, catalog, traceability, final validation

- [ ] T039 [P] Update `views.py` + `components/dashboard/src/dashboard/overlay.py` — unified snapshot: current phase, pending action list, last select pick (+fallback/shadow marker), active plan + staleness, reflection status
- [ ] T040 [P] Update `components/rimbrain/capability-catalog.yaml` + `tools/capability_audit.py` baseline for new/removed fns
- [ ] T041 [P] Update `AGENTS.md` (phase engine, mode surface, determinism contract), `components/rimbrain/CUSTOMIZE.md` (v1 pack shape + migration)
- [ ] T042 Update `specs/40-work-packages/TRACEABILITY.md` rows for FR-1401..FR-1430 linking test evidence
- [ ] T043 Run all `quickstart.md` scenarios (sim end-to-end, select bound, migration, planner cadence, reflect round-trip) — all green; live smoke deferred to bridge availability
- [ ] T044 Full-suite regression: `uv run pytest -q` — all green vs T003 baseline + new coverage; remove `startmode.py` shim and verify zero references

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no deps — **016 must be landed first**
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all stories
- **US1 (Phase 3)**: depends on Phase 2 — engine core
- **US2 (Phase 4)**: depends on Phase 2 + US1 (decide stage needs the loop); T009 writer shared
- **US5 (Phase 7)**: depends on Phase 2 — can parallel US2; CLI cleanup wants US1's loop in place
- **US3 (Phase 6)**: depends on US2 (plan feeds action-list scoring)
- **US4 (Phase 7)**: depends on Phase 2 (migration map, RunState); benefits from US1 stable loop
- **Polish (Phase 8)**: all stories

### User Story Dependencies

- **US1 (P1)**: after Foundational — no story deps
- **US2 (P2)**: after US1 (needs decide insertion point in the loop)
- **US5 (P2)**: after Foundational; CLI task after US1 — mostly parallel with US2
- **US3 (P3)**: after US2 (`goal_order` feeds select scoring)
- **US4 (P4)**: after Foundational; RunState + migration map required

### Parallel Opportunities

- T004∥T005∥T006∥T007∥T008∥T009 — all foundational, different files
- T010∥T011 — ported/new test files
- US2 ∥ US5 (except T026 ordering with US1)
- T039∥T040∥T041 — docs/views/catalog

---

## Parallel Example: Foundational

```bash
Task: "observe.py canonical observation"      (T004)
Task: "runstate.py RunState"                  (T005)
Task: "templates.py v0→v1 migration"          (T006)
Task: "dispatch.py reflex dialect unification" (T008)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 → foundation ready
2. Phase 3 (US1) → unified loop with prescriptive init + standing goals, deterministic decide (priority head = temporary default until US2)
3. **STOP and VALIDATE**: ported suite green, sim end-to-end — this alone delivers the consolidation win

### Incremental Delivery

1. Foundation → US1 (engine) → validate MVP
2. US2 (Laya decide, shadow-mode default) → validate
3. US5 (determinism/CLI) — interleave with US2
4. US3 (planner) → validate
5. US4 (reflect unification) → validate
6. Polish → traceability → merge

### Notes

- Shadow mode default (`decide.select.shadow: true`) means US2 can land with zero live-authority risk; promotion to live authority is a pack/config change after bounded trial evidence.
- Sequencing respects "consolidate first, redesign second": Phases 2–3 are behavior-preserving refactors proven by the ported suite; behavior shifts begin Phase 4.
