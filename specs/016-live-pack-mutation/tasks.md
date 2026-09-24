# Tasks: Live-Run Pack Mutation — Failure-Triggered Self-Improvement

**Input**: Design documents from `specs/016-live-pack-mutation/` (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Included — project quality gates require every feature to land with passing evidence (constitution: verification ladder).

**Organization**: US1 = failure/near-failure triggered reflection (P1, MVP). US2 = periodic cadence (P2). US3 = boundary promotion + auto-revert (P1, depends on US1's candidates). US4 = transparency (P3).

## Phase 1: Setup — contracts, bindings, pack config

- [x] T001 [P] Create `components/contracts/schemas/runtime/mutation.schema.json` from `specs/016-live-pack-mutation/contracts/mutation.schema.json` (MutationProposal: `mutation_id` pattern `^mut\.[a-z0-9][a-z0-9._-]{0,63}$`, `analysis.{failure_paths,likely_paths}` required, op enum `set|append|remove|upsert`, `path` required, `value` required for set/append/upsert + must carry `id` for upsert, forbidden for remove)
- [x] T002 [P] Add `mutation.*` event-type payload schemas under `components/contracts/schemas/events/types/` (triggered|proposed|candidate|rejected|promoted|reverted|degraded|noop — payload fields per `contracts/mutation-events.md`; `mutation.promoted.episode_boundary` enum `[true]` like improvement.promoted)
- [x] T003 Register the 8 new event types in `components/contracts/registry/event-map.yaml` and add corpus cases (valid + boundary-violation `episode_boundary:false`) under `tests/contract/`
- [x] T004 [P] Add `rimbrain.improve` role to `profiles/bindings.yaml`: primary `openrouter` + nemotron (same model as rimbrain.plan); degraded path `[gemini:gemini-3.5-flash-lite, rules-only]`
- [x] T005 [P] Add `mutate:` config block to `components/rimbrain/packs/start-mode-v0/pack.yaml` (`goals_per_pass: 10`, `on_failure: true`, `near_failure` thresholds, `cooldown_polls`, `max_passes_per_run`, `max_ops`) and to `improve-v0/pack.yaml` — policy is pack data (Principle IX); extend `pack.schema.json` if it uses additionalProperties:false

## Phase 2: Foundational — ops engine + pass skeleton

- [x] T006 Create `components/runtime/src/runtime/packmut.py`: path resolver (dotted segments; a segment matching a list element's `id` descends into it) + `apply_ops(doc, ops)` implementing `set` (write dict key, intermediate dicts created), `append` (push onto list path), `remove` (drop addressed list element/dict key), `upsert` (replace list element by `value.id` else append); returns `True` iff the doc changed
- [x] T007 Refactor `components/runtime/src/runtime/improve.py` `_apply_ops`/`propose` to delegate to `packmut` (map legacy ops `set_cfg`→`set`, `append`→`append`, `drop_template`/`drop_rule`→`remove` by id); `test_improve.py` must stay green unchanged
- [x] T008 Create `components/runtime/src/runtime/mutate.py` skeleton: `PassState` (event ring buffer, terminal-goal counter, cooldown mark, passes run, last verdict), `mutation_event(type, payload, seq, clock)` envelope builder matching the dispatcher's canonical shape, and the `state/mutations.jsonl` lineage append/read helpers

## Phase 3: User Story 1 — Failure triggers a reflection pass (P1) 🎯 MVP

**Goal**: a goal failure or near-failure during a `--live-mutate` run produces a validated candidate pack without interrupting the run.

**Independent Test**: scripted live-mode run where a `govern.*` task fails → `mutation.triggered`/`proposed`/`candidate` events + `cand-mut-*.yaml` on disk; active pack file untouched (zero `dispatch.pack_drift`).

- [x] T009 [US1] `mutate.check_triggers(state: PassState, cfg: pack['mutate'], ledger, window)` — `on_failure`: any `task.transition`→`failed|expired` this window; `near_failure`: `requeued` count ≥ cfg, escalate-source dispatches, `action.refused` burst ≥ cfg, `blocked` dwell, and `improve.diagnose` defect hits over the sliding window; honor `cooldown_polls` + `max_passes_per_run`
- [x] T010 [US1] `mutate.build_digest(ledger, window, pack)` — bounded JSON (≤ ~8KB): failing/stuck goal ids + last reason + attempts + the goal's pack spec, recent `action.refused`/`failed` (template_id, error code), defect findings, pack id/hash, op vocabulary summary
- [x] T011 [US1] `mutate.reflect(digest, pack_loaded, resolver, chat)` — resolve `rimbrain.improve`, build prompt (system: output only MutationProposal JSON; user: digest + mutation op contract), `planning.extract_json`, validate against `mutation.schema.json`; `rules-only` resolution → `improve.diagnose` remediations applied via `packmut` (or `mutation.degraded` when nothing applies); named-error envelope on every failure
- [x] T012 [US1] `mutate.gate(proposal, pack_loaded, fair)` — schema ok → `base_revision` == active hash → ops non-vacuous after `packmut.apply_ops` on a deepcopy → `templates.validate_pack` + `policy.validate_policy` + `inventory_methods` + fair-class check; return `{ok, doc}` or violations
- [x] T013 [US1] `mutate.materialize(doc, pack_file)` — write `packs/candidates/cand-mut-<slug>-<hash8>.yaml` (flat candidate form), append pending lineage row (`state/mutations.jsonl`), emit `mutation.candidate`
- [x] T014 [US1] Wire `_run_start` (`components/runtime/src/runtime/startmode.py`): wrap sink → `PassState` ring buffer; after `mode.step()` call `mutate.maybe_trigger(...)`; a pass never raises into the loop (catch → `mutation.rejected`/`system.error` event)
- [x] T015 [US1] `runtime loop --live-mutate` flag in `components/runtime/src/runtime/loop.py`; pass `PassState`+cfg into `run_start` only when set (sim/scored never see it)
- [x] T016 [US1] `components/runtime/tests/test_mutate.py`: failure trigger fires on `failed` transition; near-failure on `requeued`; injectable chat returning a valid proposal → candidate written; bad proposal → `mutation.rejected`; no flag → zero `mutation.*` events; cooldown respected

## Phase 4: User Story 2 — Periodic improvement every N goals (P2)

**Goal**: every `goals_per_pass` (default 10) terminal goal transitions triggers a pass even on a clean run; `noop` outcomes are recorded.

**Independent Test**: drive 10 terminal transitions with no failures → exactly one `mutation.triggered` (`reason: cadence`); counter resets.

- [x] T017 [US2] `check_triggers` cadence branch — count `task.transition` to `succeeded|failed|expired` for `start.*`/`govern.*`/`combat.*` since last pass; fire at `goals_per_pass`; reset counter after any pass
- [x] T018 [US2] `mutation.noop` handling — model returns empty `mutations[]` (or rules-only finds nothing): emit `mutation.noop` with rationale, count the pass, reset cadence
- [x] T019 [US2] tests: cadence fires at exactly N terminals; noop resets counter; cadence doesn't double-fire inside cooldown

## Phase 5: User Story 3 — Boundary promotion + auto-revert (P1)

**Goal**: pending candidates install over the resolved pack path at next run start; regressed promotions restore the parent.

**Independent Test**: seed a pending lineage row + candidate → start a run → pack file updated, `mutation.promoted` emitted; seed regressed episode → next boundary restores parent, `mutation.reverted`.

- [x] T020 [US3] `mutate.boundary(pack_id, state_dir, store, fair)` — read newest `pending` lineage row for `target_pack`; re-validate candidate (gate checks, `boundary` violations on failure); backup resolved `pack_path(pack_id)` to `candidates/parent-<id>-<hash8>.yaml`; `write_atomic` candidate over target; append `promoted` lineage + emit `mutation.promoted` with `baseline_score`
- [x] T021 [US3] Regression check in `boundary`: `improve.score` over `events.jsonl` entries after the last `mutation.promoted` vs recorded `baseline_score`; strictly worse → restore parent file via `write_atomic`, emit `mutation.reverted`, mark lineage `reverted`; no lineage → no revert
- [x] T022 [US3] Wire `boundary` in `loop.main` before `dispatcher.load_pack` for `start`/`live` modes when `--live-mutate`; runs before any dispatch so `pack_drift` cannot interleave
- [x] T023 [US3] tests: pending candidate installs at boundary (folder-form pack resolved via `pack_path`); stale candidate rejected (`gate: boundary`); regressed episode reverts to parent hash; non-regressed stays; no pending → clean no-op

## Phase 6: User Story 4 — Mutation transparency (P3)

**Goal**: the loop is visible — feed narration + `planning.json` mutation block.

**Independent Test**: after a triggered pass, `feed.md` narrates it and `planning.json.mutation` shows pass count/verdict/pending candidate.

- [x] T024 [P] [US4] Extend `audit.py` `DECISION_TYPES` + `feed.py` narration templates for the 8 `mutation.*` types (plain-language: trigger reason, proposed change, gate outcome)
- [x] T025 [US4] `views.py` — `planning_snapshot` gains `mutation` block from `PassState` (last trigger reason, passes run, pending candidate id, last verdict, active lineage hash); render a section in `planning.md`
- [x] T026 [US4] tests: mutation block renders; feed entries exist for each emitted event type (ux.feed_coverage stays green)

## Phase 7: Polish & cross-cutting

- [x] T027 `rimbrain.py` default `run` args gain `--live-mutate`
- [x] T028 Update `components/rimbrain/CUSTOMIZE.md` (mutation surface + how candidates promote/revert) and `AGENTS.md` phase note (016 entry, `--live-mutate`, suite count)
- [x] T029 Full suite `python -m pytest components/runtime/tests -q` green; contract corpus runner green; `python rimbrain.py run --mode sim` unchanged bit-for-bit sanity
- [ ] T030 Live smoke: `python rimbrain.py run` against the bridge; confirm a pass fires and narrates; record evidence in spec Status

## Dependencies & Execution Order

- Phase 1 ↔ Phase 2 parallelizable; both block all stories.
- US1 (Phase 3) is the MVP — digest→reflect→gate→candidate must land first.
- US2 depends on US1's `check_triggers`/`PassState`.
- US3 depends on US1's candidate + lineage record.
- US4 depends on US1's events; [P] within its phase.
- Polish last.

## Parallel Opportunities

- T001/T002/T004/T005 — different files, independent.
- T006 + T008 — `packmut` engine and `mutate` skeleton are separate files.
- T024 ∥ T025 — feed/audit vs views.

## Implementation Strategy

MVP = Phases 1–3 (US1): a failing goal produces a validated candidate mid-run. US2 adds cadence, US3 closes the promote/revert loop, US4 surfaces it. Each phase leaves the suite green.
