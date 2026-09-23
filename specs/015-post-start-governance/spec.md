# Feature Specification: Post-Start Governance — Standing Goals, Pack Classes, Goal Options

**Feature Branch**: `015-post-start-governance`

**Created**: 2026-09-23

**Status**: Draft

**Input**: `start.completed` must be a handoff, not an exit — after the bootstrap contract holds, the agent keeps running the colony under standing pack goals (UR-RUN-009). Dev/test tooling must never be loadable in a fair run (UR-BRN-018). And the planner needs an overarching strategy option space — what helps the colony survive longer, what investment each option needs, and its effect on colony wealth and raid threat — to choose objectives from.

## Purpose

Three coupled changes:

1. **Post-start governance** (UR-RUN-009): `run_start(hold=True)` continues past `start.completed`, evaluating the pack's `govern.goals` each poll — ordered standing objectives with `when` engagement gates, verifier-checked `effect`s, and re-arm-on-lapse sustainment. Bounded callers (`cycle`, `--no-hold`, tests) still stop at completion.
2. **Fair/dev pack classes** (UR-BRN-018): packs declare `class: fair|dev`; a fair pack carries zero `dev.*` methods end to end; `Dispatcher(fair=True)` refuses a dev-class pack at load (`pack.not_fair`). Spawn/heal/combat scripting moved to `dev-lab-v0` (`class: dev`); `start-mode-v0`, `core-survival-v0`, `improve-v0` are `class: fair`.
3. **Colony-goals option catalog** (`goal_options`): `packs/colony-goals-v0.yaml` holds 19 overarching strategy options annotated `{survival_benefit, investment, wealth_impact, raid_threat_impact, phase, prerequisites, sources}` over the wiki-verified raid-points economy; the same list is embedded in the gameplay packs so the planner weighs options against observed state and promotes a subset into `govern.goals` or plans. Options are data — never auto-executed.

The research/letters/quests capabilities the govern goals consume (`state.research`, `state.quests`, `state.letters`, `ui.set_research`, `steward.research`, `ui.letter` plus the matching `@fn:`s and templates) landed with this feature and flipped their capability-catalog entries `gap` → `implemented`.

## User Stories *(mandatory)*

### User Story 1 - Held Run Governs Past Completion (Priority: P1)

A `--mode start` run that reaches `start.completed` does not terminate: the interpreter evaluates `govern.goals` in declared order each poll. Sustainment goals (every colonist keeps a bed, the meal buffer never regresses) re-arm when their effect lapses; ambition goals (research bench → active research → mission offers) engage only when their `when` gate holds.

**Acceptance Scenarios**:

1. **Given** a completed start on a held run, **When** the next poll runs, **Then** the first unsatisfied govern goal proposes a `govern.<id>` ledger task and drives it through the normal lifecycle.
2. **Given** a terminal govern goal whose effect later lapses (a new mission letter arrives), **When** the effect check fails, **Then** the goal re-arms and dispatches its steps again.
3. **Given** `--no-hold` or a cycle's bounded start phase, **When** `start.completed` emits, **Then** the run/phase stops exactly as before.

### User Story 2 - Dev Tooling Cannot Enter a Fair Run (Priority: P1)

Every pack declares `class: fair|dev`. A fair run loads only packs with zero `dev.*` methods — the tooling is absent from the template registry entirely, so a dev action is `dispatch.unknown_action`, not a policy refusal. A dev-class pack is refused at load with `pack.not_fair`.

**Acceptance Scenarios**:

1. **Given** `Dispatcher(fair=True)` and `start-mode-v0`, **When** loaded, **Then** the pack loads cleanly and `spawn-hostile`/`heal-pawn` dispatch as unknown actions.
2. **Given** `dev-lab-v0`, **When** a fair dispatcher loads it, **Then** load raises `pack.not_fair` listing the dev methods — before any game write is possible.
3. **Given** `--mode combat`/`cycle`, **When** the pack loads, **Then** it is `dev-lab-v0` — scored paths never carry spawn/heal templates.

### User Story 3 - Planner Goal Option Space (Priority: P2)

The gameplay packs carry `goal_options`: 19 overarching colony goals spanning the survival arc (shelter → food → defense → stabilization → growth → wealth postures → endgame), each annotated with how it extends colony life, what it costs, and how it moves colony wealth and raid threat. The planner/model weighs them; committed objectives remain `govern.goals` or accepted plans.

**Acceptance Scenarios**:

1. **Given** any gameplay pack, **When** loaded, **Then** `pack.goal_options` lists the catalog goals with all annotation fields and resolvable prerequisite refs.
2. **Given** the wealth postures, **When** reviewed, **Then** `cap-idle-wealth` and `invest-wealth-in-defense` appear as distinct mutually-exclusive options, not merged policy.
3. **Given** `goal_options` data, **When** the interpreter runs, **Then** no goal executes — promotion into `govern.goals` or a reviewed plan is required first.

## Edge Cases

- **Established colony under hold**: sustainment effects already hold → goals skip-to-terminal with zero writes (same machinery as start phases).
- **Goal blocked on missing vars**: a goal with `requires:` entries that were never set reports `blocked` with the missing names, never dispatches.
- **Multiple lapsed goals**: declared order wins — the first active goal does work each poll.
- **Mission letter with no accept choice**: `for_each` filter finds no matching letter; the goal idles until its `when` gate or choices change.
- **Dev pack in a fair run via brain reset**: the reset path re-loads through the same dispatcher — `pack.not_fair` keeps the run fail-closed on the last valid pack.
- **Goal options vs govern drift**: `goal_options` is a catalog copy; divergence from `govern.goals` is expected (options ≠ commitments) and not an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-1301**: pack `govern.goals[]` — ordered `{id, when?, requires?, need?, effect, steps, repeat?}` evaluated in declared order every poll once the start exit contract holds and the run holds (UR-RUN-009). A terminal goal re-arms only while its observed `effect` has lapsed.
- **FR-1302**: `run_start(hold: bool)` — `--mode start` defaults `hold=True`; `--no-hold` opts out; `cycle.py` start phase passes `hold=False`. Govern tasks share the TaskLedger lifecycle (`govern.<id>` ids, verifier-only success, `task.transition` log) and emit decision rows sourced `govern:<id>`.
- **FR-1303**: `pack.schema.json` gains `class: fair|dev`; `Dispatcher(fair=True).load_pack` refuses packs declaring `dev.*` template methods (`pack.not_fair` listing the methods). `start-mode-v0`, `core-survival-v0`, `improve-v0` declare `class: fair`; `dev-lab-v0` declares `class: dev` and owns spawn/heal templates + `combat`/`cycle` scripting (UR-BRN-018).
- **FR-1304**: `--mode combat` and `--mode cycle` load `dev-lab-v0`; tests using combat scripting switch to it. Fair runs never carry debug tooling.
- **FR-1305**: capabilities — bridge `state.research`, `state.quests`, `state.letters`, `ui.set_research`, `steward.research`, `ui.letter`; policy fns `research()`, `research_current()`, `research_available()`, `quests()`, `letters(choice_only)`; templates `set-research`, `queue-research`, `answer-letter`; capability-catalog entries updated `gap` → `implemented`.
- **FR-1306**: `packs/colony-goals-v0.yaml` — standalone annotated catalog with the wiki raid-points mechanics baseline; `pack.schema.json` gains `goal_options` (array); the catalog list is embedded in `core-survival-v0`, `start-mode-v0`, `dev-lab-v0`.
- **FR-1307**: `views.py` goal rows cover `govern.<id>` goals after the start-phase rows, preserving pack order.
- **FR-1308**: `goal_options` are inert data — the interpreter never executes them; promotion into `govern.goals` or a reviewed plan is the only path to dispatch.

### Success Criteria

- **SC-1301**: `test_hold_governs_after_completed` — held sim run continues past `start.completed`; `govern.research-bench`, `govern.research-progress`, `govern.mission-offers` reach `succeeded`; a fresh letter re-arms the terminal goal on a subsequent held run.
- **SC-1302**: `--no-hold` and cycle bounded start stop at `start.completed` with no `govern.*` tasks.
- **SC-1303**: `test_fair_mode_denies_debug` — fair dispatcher loads `start-mode-v0`; dev templates return `dispatch.unknown_action`; save/load refused per-dispatch; `dev-lab-v0` raises `pack.not_fair` at load.
- **SC-1304**: all packs pass `load_pack` validation with `goal_options` present; `improve-v0` unaffected.
- **SC-1305**: `test_views` — planning goals list ends with `govern.*` ids in pack-declared order.
- **SC-1306**: colony-goals catalog — 19 goals, all `prerequisites` resolve to catalog ids, every entry cites guide/wiki sources; uncertain claims documented in `colony-goals-v0.notes.md`.

## Constraints

- Govern work is ledger tasks through the single writer — no new write path; `govern:` sources appear in `decisions.jsonl` like any other pack element (UR-VIEW).
- Fair class is load-time enforced, not dispatch-time advisory: the tooling is absent, not merely refused (UR-BRN-018).
- `goal_options` carry strategy annotations (benefit/cost/threat), not executable steps — the catalog schema stays out of the policy engine; promoting an option is planner work or human editing.
- All wealth/raid-threat claims trace to the wiki mechanics baseline in the catalog header or to cited guide timestamps; unverifiable claims are recorded in the notes file, not asserted.

## Risks and open questions

- `goal_options` duplication across 3 packs + the standalone catalog drifts unless the catalog stays the authoring source (documented in pack comments).
- No observation signal for colony wealth yet — `cap-idle-wealth`/`invest-wealth-in-defense` can't be gated on observed wealth until a `state.wealth`-class capability exists (notes.md open question).
- `phase`/`prerequisites` are prose-level gating; predicate-form conditions (`{field,op,value}`) would let the review gate machine-check option eligibility.

## Traceability evidence

- `components/runtime/src/runtime/startmode.py` — `_drive` shared driver + `_govern_step`; `run_start(hold=)`; `loop.py --no-hold`; `cycle.py hold=False`.
- `components/runtime/src/runtime/dispatch.py` — `load_pack` fair-class dev-method refusal (`pack.not_fair`).
- `components/runtime/src/runtime/policy.py` — `research*`/`quests`/`letters` fns; `validate_policy` govern.goals checks.
- `components/runtime/src/runtime/views.py` — `govern.*` goal rows.
- `components/rimbrain/packs/dev-lab-v0.yaml` (new, `class: dev`); `start-mode-v0`/`core-survival-v0`/`improve-v0` `class: fair`; `colony-goals-v0.yaml` + notes; `goal_options` embedded in the three gameplay packs.
- `components/contracts/schemas/runtime/pack.schema.json` — `class`, `govern`, `goal_options` properties.
- `components/rimbrain/capability-catalog.yaml` — research/quests/letters entries `implemented`.
- Tests: `test_startmode.py::test_hold_governs_after_completed`, `test_universal.py::test_fair_mode_denies_debug`, `test_views.py` govern ordering, `test_combat.py`/`test_cycle.py` dev-lab loading; StartSim research/letters stubs.
