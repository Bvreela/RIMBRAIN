---

description: "Task list for feature 021 fast-evolve play mode"
---

# Tasks: Fast-Evolve Play Mode

**Input**: Design documents from `/specs/021-fast-evolve/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/fastevolve.md

**Tests**: Included — this project requires failing-test-first per AGENTS.md workflow; quickstart.md defines the validation scenarios.

**Organization**: Tasks grouped by user story (US1/US2 are both P1; US2 is small and lands second so the mode flag can wrap the working loop).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Create `specs/90-decisions/ADR-020-fast-evolve-midrun.md` — constitution Principle III gate: mid-run candidate promotion + scoped `allow_save_load` grant in an unscored play mode; documents deviation from ADR-018 boundary-only promotion and UR-CTL-009 save/load refusal; must be accepted before any code task starts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared mechanics every story builds on — no story work until these land.

- [x] T002 Add `allow_save_load: bool = False` ctor flag to `Dispatcher` in `components/runtime/src/runtime/dispatch.py` — bypasses only the `game.save`/`game.load` half of the `dispatch.fair_mode` refusal; `dev.*` refusal, params validation, and `action.*` evidence unchanged
- [x] T003 Factor the install half of `boundary()` in `components/runtime/src/runtime/evolve.py` into `promote_candidate(candidate_path, pack_id, state_dir, *, mid_run=False, emit, clock)` — re-validate via `validate_candidate`, write `packs/candidates/parent-<id>-<hash>.yaml` backup, `write_atomic` over the pack file, append `promoted` lineage row with `mid_run` marker; `boundary()` calls it for the episode path unchanged
- [x] T004 Add `game.save` / `game.load` / `game.list_saves` to `SimGame` in `components/runtime/src/runtime/simgame.py` — named `deepcopy` state snapshots; `list_saves` returns `{saves: [{name}, ...]}` including configurable autosave rows; keeps deterministic advance semantics
- [x] T005 Create `components/runtime/src/runtime/fastevolve.py` skeleton — `DayState` dataclass + `load`/`save` against `state/fastevolve.json` via `store.write_atomic` (fields per data-model.md: `schema_version`, `day`, `anchor`, `anchor_day`, `reloads_used`, `exhausted`, `attempts[]`), and `fe_event()` envelope builder (`source: rimbrainagent.runtime.fastevolve`)

**Checkpoint**: dispatcher grant + shared promote + sim save/load + session persistence compile and unit-test clean.

---

## Phase 3: User Story 1 - Retry a failing day with an evolved brain (Priority: P1) 🎯 MVP

**Goal**: day-failure trigger → pause → reflect → mid-run promote → reload day-start autosave → reinit → resume; ≤2 reloads/day; exhausted days evolve-only.

**Independent Test**: scripted SimGame where a trigger trips mid-day — assert the reload/reinit/attempt sequence and exhaustion behavior from canonical events.

### Tests for User Story 1

- [x] T006 [P] [US1] `test_fastevolve.py` — day rollover resets `reloads_used` and re-resolves anchor; `fastevolve.day_start` emitted with `{day, anchor}`
- [x] T007 [P] [US1] `test_fastevolve.py` — trigger with budget: pause → reflect (injected chat) → `promote_candidate` → `load_pack` rebind (hash changes, no drift refusal) → `load-game` anchor → reinit (`rs.reset` + `ledger.reset_ns`) → `fastevolve.reloaded` with `reloads_used=1`
- [x] T008 [P] [US1] `test_fastevolve.py` — trigger on final attempt: evolve still runs, no `load-game` dispatch, `fastevolve.exhausted`, last promoted pack stays active
- [x] T009 [P] [US1] `test_fastevolve.py` — missing/stale anchor: `fastevolve.anchor_missing`, evolve runs, no reload, attempt not spent; `max_anchor_age_days` honored
- [x] T010 [P] [US1] `test_fastevolve.py` — failed `load-game` dispatch spends the attempt (`reloaded: false` row) and play continues; restart mid-day resumes recorded `reloads_used` from `fastevolve.json`

### Implementation for User Story 1

- [x] T011 [US1] `fastevolve.py` — `AutosaveTracker`: throttled `game.list_saves` (`saves_poll_every`), `autosave_pattern` match, anchor = match whose `modified` is nearest the session's `day_start_wall` (prefer at-or-after; mid-day run start falls back to newest match) per data-model selection rule, stale-flag via `max_anchor_age_days`
- [x] T012 [US1] `fastevolve.py` — `check_day_triggers(obs, day_ps, pack)`: `fail_when`/`near_when` via `policy.check` over obs plus `evolve.check_triggers` on a day-scoped `PassState` when `triggers.use_mutate` — PassState cfg = `mutate:` with `max_passes_per_run := fastevolve.max_passes_per_day`, `cooldown_polls := 0` (per data-model); returns `(reason, evidence)` with reasons `day_failure`/`day_near_failure`
- [x] T013 [US1] `fastevolve.py` — `evolve_and_reload(...)`: `game.pause` → `evolve.maybe_trigger(reason=day_failure, force-as-needed)` → on candidate `promote_candidate(mid_run=True)` → `dispatcher.load_pack` rebind → `dispatch("load-game", {name: anchor})` → `_wait_playing` → restore speed → return reinit signal; attempt row appended to DayState either way
- [x] T014 [US1] `loop.py` — `run(..., fast_evolve: bool = False)` param; per-poll call to `fastevolve.tick` after the reflect stage; **in fast-evolve the generic per-poll `maybe_trigger` call is bypassed** — only `fastevolve.tick` invokes the pass so cadence triggers can't fire (FR-2112); on reload signal perform the brain-reset reinit (unlink runstate/startmode files, `ledger.reset_ns`, `rs.reset`, fresh `PhaseEngine` + day-scoped `PassState` seeded with cumulative day evidence); day rollover handling
- [x] T015 [US1] `fastevolve.py` — exhaustion + rollover paths: trigger on final attempt → `fastevolve.exhausted`, evolve-only; day change → fresh `DayState`, anchor re-resolution, budget reset; per-day `max_passes_per_day` reflection budget enforced

**Checkpoint**: US1 independently testable — sim run retries a failing day exactly twice then advances.

---

## Phase 4: User Story 2 - Fast-evolve is a declared play option (Priority: P1)

**Goal**: `--mode fastevolve` launches the mode; invalid combinations refuse at launch; never default; scored runs excluded.

**Independent Test**: CLI invocations — valid combo runs, invalid combos exit 2 with named errors; `dev.*` dispatch still refused mid-run.

### Tests for User Story 2

- [x] T016 [P] [US2] `test_fastevolve.py` — `loop.main` arg validation: `--mode fastevolve --game live` without `--live` → `loop.live_requires_confirmation`; mode + scored/fair-scored context → `loop.fastevolve_scored` exit 2
- [x] T017 [P] [US2] `test_fastevolve.py` — dispatcher grant: `Dispatcher(fair=True, allow_save_load=True)` dispatches `save-game`/`load-game` and still refuses a `dev.*` template with `dispatch.fair_mode`; `allow_save_load=False` (all other modes) still refuses save/load

### Implementation for User Story 2

- [x] T018 [US2] `loop.py` `main()` — add `fastevolve` to `--mode` choices; validation block (needs `--live` unless sim; implies reflect wiring; never implied by other flags); extend the existing `live_mutate` mode check (`loop.py` ~line 415) so `--live-mutate` is accepted under `--mode fastevolve` too; construct `Dispatcher(..., fair=args.fair, allow_save_load=True)`; pass `fast_evolve=True` into `run()`
- [x] T019 [US2] `rimbrain.py` — verify pass-through works (`rimbrain run --mode fastevolve ...`); no new launcher code needed — spec-018's declarative parameter spec (updated FR-002) auto-enumerates the new mode when 018 ships

**Checkpoint**: US2 independently testable — mode selectable and guarded.

---

## Phase 5: User Story 3 - Day failure triggers are pack policy (Priority: P2)

**Goal**: the `fastevolve:` pack section owns every retry-policy knob; invalid predicates fail pack load.

**Independent Test**: pack-data-only edit adds a `fail_when` predicate and changes `max_reloads_per_day`; behavior changes with zero code edits.

### Tests for User Story 3

- [x] T020 [P] [US3] `test_fastevolve.py` — pack edit adds `fail_when` predicate (e.g. `food_days` below value) → trigger fires; `use_mutate: false` → goal failures don't trigger; budget/`autosave_pattern`/`saves_poll_every` honored
- [x] T021 [P] [US3] `test_fastevolve.py` — invalid `fail_when` predicate fails pack load (`pack.invalid`); `max_reloads_per_day: 0` runs evolve-only

### Implementation for User Story 3

- [x] T022 [US3] `templates.py` (or pack validation path) — validate `fastevolve:` section at pack load: predicate shape check via `policy.check` grammar, numeric clamps, unknown-key warning; absent section → documented defaults
- [x] T023 [US3] `components/rimbrain/packs/start-mode-v0/pack.yaml` — add `fastevolve:` section with the data-model defaults + starter `fail_when`/`near_when` predicates (colonist downed/dead, food runway)

**Checkpoint**: US3 independently testable — policy tuning is pure pack data.

---

## Phase 6: User Story 4 - Retry transparency (Priority: P3)

**Goal**: `fastevolve.*` events narrated to feed; `planning.json` shows day/anchor/budget.

**Independent Test**: after a retry, `feed.md` narrates the sequence and `planning.json` carries the `fastevolve` block.

### Tests for User Story 4

- [x] T024 [P] [US4] `test_fastevolve.py` — all six `fastevolve.*` events appear in canonical order for a triggered retry; `planning.json` `fastevolve` block shows `{day, anchor, reloads_used, max_reloads, exhausted}`

### Implementation for User Story 4

- [x] T025 [P] [US4] `feed.py` — narration lines for the six `fastevolve.*` events
- [x] T026 [P] [US4] `views.py` — `fastevolve` block in `phase_snapshot`; `audit.py` event-type list += `fastevolve.*`; overlay `overlay.py` extra-tag line for day/attempts (mirrors the existing `reflect:` tag pattern)

**Checkpoint**: full evidence trail visible.

---

## Phase 7: Polish & Cross-Cutting

- [x] T027 [P] Update `specs/00-foundation/UNIFIED-REQUIREMENTS.md` + `specs/40-work-packages/TRACEABILITY.md` rows for FR-2101..FR-2112 linking test evidence
- [x] T028 [P] Update `AGENTS.md` (021 phase note), `components/rimbrain/CUSTOMIZE.md` (`fastevolve:` section + mode description)
- [x] T029 Run quickstart.md scenarios 1–3 (sim deterministic + launch guards); live smoke deferred to bridge availability
- [x] T030 Full-suite regression `uv run pytest -q` — all green including existing `test_evolve.py`/`test_brain_reset.py` (shared promote/reinit paths)

---

## Dependencies & Execution Order

- **Phase 1 (ADR-020)**: blocks everything — constitution gate.
- **Phase 2**: T002–T005 independent of each other ([P]-safe in practice: separate files except none shared); all block Phase 3.
- **US1 (Phase 3)** depends on Phase 2; internally T011/T012 parallel, T013 depends on both, T014 on T013, T015 last.
- **US2 (Phase 4)** depends on US1's `run()` param existing (T014) but its tests are independent.
- **US3 (Phase 5)** depends on T012's predicate evaluation existing.
- **US4 (Phase 6)** depends on US1 events existing; T025/T026 parallel.
- **Phase 7** after all stories.

## Parallel Example

```bash
# Phase 2 (different files):
T002 dispatch.py | T003 evolve.py | T004 simgame.py | T005 fastevolve.py
# US1 tests (same file, sequential writes but logically parallel specs):
T006..T010
# US4 polish:
T025 feed.py | T026 views.py+overlay.py+audit.py
```

## Implementation Strategy

MVP = Phases 1–3 (ADR + foundations + US1). US2 then makes it launchable, US3 tunable, US4 observable. Feature 018 needs no 021-side work — its declarative mode enumeration picks `fastevolve` up automatically.
