# Tasks: Combat Capability

**Input**: Design documents from `specs/019-combat-capability/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/combat-capability.md

**Tests**: Included — project convention requires traceability-linked passing evidence per feature.

**Hard prerequisite**: Feature 017 (`specs/017-unified-phase-engine`) US1+US2 must be landed — `select.py` `pawn_scope` machinery + decide stage in the loop are the executor this feature hangs off.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Verify 017 US2 landed: `components/runtime/tests/test_select.py` green, `decide.select.pawn_scope` compiles per-pawn candidates, `engine.step(select_out=)` consumed in `components/runtime/src/runtime/loop.py` — do not proceed if open
- [ ] T002 Create branch `feature/019-combat-capability` from the 017 merge point
- [ ] T003 [P] Record baseline: `cd components/runtime && uv run pytest -q` — save pass count for regression comparison
- [ ] T004 [P] Draft ADR for combat-writer authority (delegate model per spec Edge Cases resolution) in `specs/90-decisions/ADR-0XX-combat-authority.md` — order is base executor, pack steers via `steward.orders.*`, pawn options are surgical overrides via manual-touch

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: pack schema + threat/eligibility fns + order-state observation every story consumes

**⚠ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Extend `components/contracts/schemas/runtime/pack.schema.json` with the optional `combat:` cfg block per `contracts/combat-capability.md` — positive-int radii (`engage_radius`, `overrun_radius`, `near_hostile`), tick windows (`release_ticks`, `prolonged_ticks`), `min_health` percent, `relief` {food,rest,recover}, `assault_duties`/`watch_lords`/`manhunter_mental` string lists, `delegate_order` string|null
- [ ] T006 [P] Implement threat classification fns in `components/runtime/src/runtime/policy.py`: `engaged_hostiles()`/`watching_hostiles()` per `research.md` §6 (in-Home via `map.cell`/`state.areas`, ≤`engage_radius` of rally, `lord` ∈ `assault_duties`, `mental` == `manhunter_mental` only while a colonist is outside Home, structures only when near); hostile exclusions: dead/downed/fogged/player-faction/berserk-colonist/slave-rebellion/prison-break/animal
- [ ] T007 [P] Implement eligibility fns in `components/runtime/src/runtime/policy.py`: `draftable(id)`/`fighters()` per data-model — spawned ∧ ¬dead ∧ ¬downed ∧ ¬prisoner ∧ ¬slave ∧ ¬juvenile ∧ violence-capable ∧ has-drafter ∧ health ≥ `@cfg:combat.min_health` ∧ (armed ∨ cfg `allow_unarmed`)
- [ ] T008 [P] Project steward order state into obs in `components/runtime/src/runtime/observe.py` + `order_state(order)` fn in `policy.py` — `{enabled, engaged, overrun, last}` from `steward.status`/`steward.orders.explain`; verify the surface exposes enough, else mark `[bridge-gap]` and return the explain summary verbatim
- [ ] T009 Register combat templates in `components/rimbrain/capability-catalog.yaml` per contract: `move-pawn`→`ui.goto`, `cancel-job`→`ui.cancel_job`, `set-area`/`set-hostility`→`ui.set_policies`, `field-tend`/`capture`/`ingest-drug`→`ui.job`, `order-pawn`→`ui.order`, `press-gizmo`→`ui.press`, `animal-guard`→`ui.animal`, `rally-set`→`steward.orders.rally`, `order-run`→`steward.orders.run`, `combat-release`→`steward.orders.release` — all `status: implemented`, sealed methods only

**Checkpoint**: fns resolve over fixture obs; pack with `combat:` block validates; catalog audit diff shows only new entries

---

## Phase 3: User Story 1 — Colony defends itself without scripting (P1) 🎯 MVP

**Goal**: delegate-mode defense — pack enables/steers the standing combat order, shelters non-fighters, releases on hysteresis; nothing dev-class

**Independent Test**: sim scripted raid → `combat_engaged` → fighters drafted at rally → `combat_released` after hostile-free window; zero writes on downed/fogged/friendly

### Tests for User Story 1

- [ ] T010 [P] [US1] Write `components/runtime/tests/test_combat_capability.py` — engaged/watch classification fixtures (in-Home, radius, assault duties, siege-watch, manhunter-conditional), `draftable` gates, no downed/dead/fogged/friendly targets
- [ ] T011 [P] [US1] Write release-hysteresis tests in `components/runtime/tests/test_combat_capability.py` — hostile-free streak < `release_ticks` holds draft; ≥ fires `combat-release`; non-fighter areas restore via the order

### Implementation for User Story 1

- [ ] T012 [US1] Implement `combat_mode()` + `ticks_since_hostile()` in `components/runtime/src/runtime/policy.py` — `watch|engage|overrun|hold` from T006 classification + `overrun_radius`/Home check; `ticks_since_hostile` over obs history (runstate)
- [ ] T013 [US1] Implement `hostiles_in_home()`/`hostiles_within(cell,r)`/`nearest_fleeing(p)`/`safe_cell(p)` in `components/runtime/src/runtime/policy.py`
- [ ] T014 [US1] Create `components/rimbrain/packs/combat-defense-v0/pack.yaml` — `class: fair`, `combat:` cfg defaults from contract, `capabilities.templates` for the T009 set + existing `draft-pawn`/`attack-target`/`strip-pawn`, rules: `enable-order` (steward.orders.set combat on + `rally-set` to anchor), `shelter-noncombatants` (`set-area` Home), `stand-down` (`ticks_since_hostile ≥ release_ticks` → `combat-release`), `chase-fleeing` (port existing universal rule)
- [ ] T015 [US1] Wire `order_state` into the pack's `senses`/obs section and add rules gating on `order_state(combat).engaged` — pack reacts to the order's own lifecycle instead of duplicating it
- [ ] T016 [US1] Verify engagement lifecycle events: `combat_engaged`/`combat_released` come from the steward ledger `[have]`; emit `combat.overrun`/`combat.prolonged` via pack rules reading `order_state` transitions (no new event machinery)

**Checkpoint**: `python -m runtime loop --pack combat-defense-v0 --mode run --game sim` scripted raid passes lifecycle assertions; suite green vs T003 baseline

---

## Phase 4: User Story 2 — Per-pawn combat action lists (P2)

**Goal**: pawn-scope options gated by pawn fit × enemy mix × mode; `priority_head` fallback = deterministic best assignment

**Independent Test**: mixed squad (brawler/shooter/non-fighter) → shooter offered ranged options, brawler melee options, non-fighter shelter only; endpoint-down produces identical assignments via fallback

### Tests for User Story 2

- [ ] T017 [P] [US2] Extend `components/runtime/tests/test_combat_capability.py` — option-compile fixtures: per-pawn gates prune (non-fighter sees only `shelter`), `q.pawn.<id>` criteria contain only eligible options, ≤20 bound at 15 colonists
- [ ] T018 [P] [US2] Fallback-equality test in `components/runtime/tests/test_combat_capability.py` — endpoint-down poll applies `priority_head` per pawn; invalid pick → `select.invalid` + fallback

### Implementation for User Story 2

- [ ] T019 [US2] Implement pawn-fit fns in `components/runtime/src/runtime/policy.py`: `skill_of(id,skill)`, `weapon_stats(def|thing)`→`{class,range,dps,warmup,cooldown,burst}` (via `defs.get`, cached), `health_of(id)`, `need_of(id,need)`, `speed_of(id)` (Moving capacity × 4.6 approx)
- [ ] T020 [US2] Implement threat-comparison fns in `components/runtime/src/runtime/policy.py`: `outranges(p,h)`/`outranged_by(p)`/`outrun_by(p)`/`in_range(p,h)`/`kite_cell(p)`/`block_cell(p)` — defs.get miss → null → gates false (conservative per contract)
- [ ] T021 [US2] Implement `rally_cell(pawn)` in `components/runtime/src/runtime/policy.py` — distinct cover-preferring cells in rally rect (cover from `map.cell` things, spread cap 4, center bias 0.05 per OrderLogic), assignment state in `runstate.rule_state`
- [ ] T022 [US2] Add `decide.select.pawn_scope` combat options to `combat-defense-v0/pack.yaml` per contract vocabulary — `retreat`/`relieve`/`shelter`/`hold-rally`/`attack-nearest`/`kite-step`/`melee-block`/`chase-fleeing` with `when` gates on `@fn:combat_mode()` + fit fns and `priority` = fit score
- [ ] T023 [US2] Exclude manually-touched pawns from combat candidates — read touch state via `steward.orders` explain/status surface (T008); if no per-pawn surface exists, add `touched` to `steward.pawn`/status `[bridge-gap]` and gate options on it

**Checkpoint**: `pawn_scope` combat options compile in sim; fallback assignments match expected best-fit; bound holds

---

## Phase 5: User Story 3 — Adaptive tactics (P3)

**Goal**: composition-aware behavior — blockers vs melee-heavy raids, suppression vs outranging enemies, chase only fleeing humans, mechanoids fought to destruction

**Independent Test**: parameterized enemy compositions (melee animals, ranged raiders, mechanoids, mixed) each produce the matching option mix

### Tests for User Story 3

- [ ] T024 [P] [US3] Extend `components/runtime/tests/test_combat_capability.py` — `enemy_mix`/`enemy_max_range`/`threat_power` fixtures; kite suppressed when outranged-or-outrun; chase only for cfg-eligible melee pawns

### Implementation for User Story 3

- [ ] T025 [US3] Implement `enemy_mix()`/`enemy_max_range()`/`threat_power()`/`manhunters()` in `components/runtime/src/runtime/policy.py` — weapon def → melee/ranged class via `defs.get`; combat-power table in pack cfg (`combat.power_overrides`), wiki defaults
- [ ] T026 [US3] Wire `threat_power` odds ratio into `combat_mode()` — unwinnable ⇒ `watch`/`shelter` instead of engage (cfg `engage_odds_floor`)
- [ ] T027 [US3] Extend `combat-defense-v0` pawn options: `melee-block` gated on enemy melee majority + choke present; `kite-step` on range/speed advantage; `chase-fleeing` on `fleeing_ids` + `chase_skill` cfg; priority expressions carry `@cfg:combat.option_weights`

**Checkpoint**: composition fixtures produce expected option mixes; no kite offered to outranged pawns

---

## Phase 6: User Story 4 — Post-combat recovery (P3)

**Goal**: strip/capture downed hostiles, rescue downed colonists, engagement evidence for improve metrics

**Independent Test**: scripted raid leaving downed hostile + downed colonist → strip designation + rescue dispatch after release

### Tests for User Story 4

- [ ] T028 [P] [US4] Extend `components/runtime/tests/test_combat_capability.py` — post-release rules: strip fires on `downed_ids`, capture gated on free prison capacity fn, rescue offered for reachable downed colonist

### Implementation for User Story 4

- [ ] T029 [US4] Implement `free_beds(medical?)`/`casualty_ids()`/`pawns_needing_tend()` in `components/runtime/src/runtime/policy.py`; add `strip-downed`/`capture`/`rescue`/`field-tend` rules + options to `combat-defense-v0` with capacity gates
- [ ] T030 [US4] Add engagement evidence — pack rule on release records duration/hostiles-handled/losses via decision rows (verify `improve`/`evolve` digest picks up the event types)

**Checkpoint**: dev-harness raid leaves stripped hostiles + rescued colonists; evidence rows present in `decisions.jsonl`

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Update `components/rimbrain/capability-catalog.yaml` audit baseline + `tools/capability_audit.py` expected diff for new entries
- [ ] T032 [P] Update `AGENTS.md` (019 status) and `components/rimbrain/CUSTOMIZE.md` (combat cfg + option vocabulary)
- [ ] T033 Update `specs/40-work-packages/TRACEABILITY.md` rows for FR-1901..1910/SC-1901..1906 linking test evidence
- [ ] T034 Run all `quickstart.md` scenarios — green; live smoke deferred to bridge availability
- [ ] T035 Full-suite regression `uv run pytest -q` — all green vs T003 baseline + new coverage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: **017 US1+US2 landed first** (T001 gate)
- **Foundational (Phase 2)**: after Setup — BLOCKS all stories
- **US1 (Phase 3)**: after Foundational — MVP
- **US2 (Phase 4)**: after US1 (pack skeleton + delegate path exist)
- **US3/US4 (Phases 5-6)**: after US2 (option machinery in place)
- **Polish (Phase 7)**: all stories

### Parallel Opportunities

- T003∥T004 (baseline ∥ ADR)
- T006∥T007∥T008∥T009 — independent fns/catalog files
- T010∥T011, T017∥T018, T024, T028 — test files can land together
- US3 ∥ US4 once US2 is done (different fns/rules)

## Parallel Example: Foundational

```bash
Task: "Implement threat classification fns in policy.py"      # T006
Task: "Implement eligibility fns in policy.py"                # T007
Task: "Project steward order state into obs + order_state fn" # T008
Task: "Register combat templates in capability-catalog.yaml"  # T009
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup + Foundational
2. US1: delegate-mode defense pack repels a sim raid via the standing order
3. **STOP and VALIDATE**: lifecycle events + no friendly/downed targets

### Incremental Delivery

1. US1 → defense parity with proven order (MVP)
2. US2 → fastbrain per-pawn overrides (the feature's headline)
3. US3 → composition-aware tactics
4. US4 → recovery + evidence
