# Tasks: Strategic Planner / Review Loop (005)

**Inputs**: `spec.md`, `plan.md` | **Feature**: `specs/005-planner-review`

## Phase 1: Contracts

- [x] T091 [P] Create `components/contracts/schemas/runtime/plan.schema.json` — PlanProposal: `{schema_version, plan_id, base_revision, horizon_ticks, actions[{template_id, params}], policy_mutations[{op, target, patch}], rationale}` where op is `add_template|edit_decision_map|add_emergency` (FR-402)
- [x] T092 [P] Create `schemas/events/types/plan.{proposed,reviewed,accepted,rejected}.schema.json` — payloads carry `{plan_id, pack_revision, endpoint_id, model, usage{prompt_tokens, completion_tokens}, verdict?, violations?}`; register all four in `registry/event-map.yaml` (FR-405)
- [x] T093 [P] Corpus: `plan.valid.01` + `plan.invalid.01` (unknown action template shape), `plan.invalid.02` (bad mutation op), `plan.invalid.03` (missing base_revision) + valid/invalid plan.* event payloads

## Phase 2: Planning core

- [x] T094 Implement `components/runtime/src/runtime/planning.py`: deterministic prompt builder (state digest + pack templates digest), chat call via `resolve_role("rimbrain.plan")` + `build_client`, JSON extractor (fenced ```json then bare object), schema validation -> PlanProposal or `plan.malformed`; `rules-only` sentinel yields pack `fallback_plan` with `degraded` provenance (FR-401/402/408)
- [x] T095 Add `fallback_plan:` block to `components/rimbrain/packs/core-survival-v0.yaml` — deterministic rules-only plan (work priorities + haul designation) so degraded mode is pack-authored data (FR-408)

## Phase 3: Review gate

- [x] T096 Implement `components/runtime/src/runtime/review.py`: deterministic gate — every `actions[].template_id` exists in pack, params validate against params_schema, mutations are legal ops on existing ids; then optional `rimbrain.review` chat critique (failure -> `model_unavailable`, verdict still deterministic); verdict requires gate pass (FR-403)

## Phase 4: Loop + candidates

- [x] T097 Implement `components/runtime/src/runtime/planloop.py`: status -> plan -> review -> on accept write candidate pack `packs/candidates/<pack_id>-<sha8>.yaml` (re-validated through templates.load_pack) + dispatch plan `actions[]` via Dispatcher; emit plan.* canonical events with usage; refuse while scored episode active (`plan.scored_episode_active`) (FR-404/405/406/409)
- [x] T098 Add `plan` subcommand to `runtime/__main__.py`: `python -m runtime plan --mode sim|live [--pack core-survival-v0] [--iterations N] [--no-dispatch]` — live needs `--live` flag (FR-407)

## Phase 5: Tests + polish

- [x] T099 [P] `tests/test_planning.py`: extractor (fenced/bare/malformed), stub-decider proposal, rules-only fallback provenance, zero writes on malformed (SC-402)
- [x] T100 [P] `tests/test_review.py`: deterministic gate rejects unknown template even when stub reviewer approves (SC-401); model-unavailable still yields deterministic verdict
- [x] T101 [P] `tests/test_planloop.py`: accepted plan writes loadable candidate (SC-404), five runs bit-identical (SC-403), degraded path completes (SC-405), plan actions dispatch only via Dispatcher
- [x] T102 Polish: INDEX row 005, runtime README planner section, candidates/.gitkeep, AGENTS.md phase note, validate_components

## Phase 6: Convergence

- [x] T103 Thread model provenance + usage through all four plan.* event payloads (endpoint_id, model on plan.reviewed/accepted/rejected; usage on accepted/rejected) and update the three corresponding event schemas per FR-405 (partial)
- [x] T104 Re-poll `game.status` each iteration in planloop.main (stale-state bug for --iterations N>1) and stamp event `game_tick` from `state.tick` per FR-407 (partial)
- [x] T105 Instantiate a UsageTracker in planloop.main, pass it through run_plan, and include `usage` snapshot in the CLI result per FR-405/US4 (partial)

## Phase 7: Convergence (live-smoke findings)

- [x] T106 Enrich `planning.build_prompt` state digest with the real colonist roster (ids + names + downed status from observed state.members) and require the planner to reference only observed entities � no invented pawns (per FR-401 + live smoke finding; missing)
- [x] T107 Add entity-existence validation to `review.deterministic_check` (signature gains `state`): `pawn` params must resolve to an observed colonist id/name, rescue `target` to the observed downed id; invented entities = gate violation (per FR-403; missing)
- [x] T108 Encode "planner acts on observed colony state only � never invented entities" as a normative rule in AGENTS.md architectural invariants (missing)

## Phase 8: Convergence (final audit)

- [x] T109 Extend `tests/contract/corpus_runner.py` so event-payload corpus cases can address dotted event types (e.g. `ev__plan.proposed.valid.01.json` -> `schemas/events/types/plan.proposed.schema.json`), and add corpus cases for plan.* and action.* payloads per T093 + feature 004 T078 (partial)
- [x] T110 Add a test asserting emitted `plan.*` envelopes validate against `schemas/events/envelope.schema.json` + their payload schemas per US4 independent test (partial)
