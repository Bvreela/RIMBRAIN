# Tasks: Building / Room Capability

**Input**: Design documents from `specs/020-building-capability/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/room-archetypes.md

**Tests**: Included — project convention requires traceability-linked passing evidence per feature.

**Hard prerequisite**: Feature 017's pack-schema v1 surface (`templates.py` v0→v1, `pack.schema.json`) must be landed — `rooms:`/`mods:` extend it.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Verify 017 schema surface landed: `pack.schema.json` accepts v1 blocks (`phases`/`decide`/`action_list`), `templates.py` migrates v0 docs — do not proceed if open
- [X] T002 Create branch `feature/020-building-capability` from the 017 merge point
- [X] T003 [P] Record baseline: `cd components/runtime && uv run pytest -q` — save pass count for regression comparison

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schema surface + room observation + def-stat access + tier-profile resolution every story consumes

**⚠ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Extend `components/contracts/schemas/runtime/pack.schema.json` with optional `rooms:` block (`tier_table`, `archetypes` map) and `mods:` block (per-mod `package_id` + free-form `settings`) per `contracts/room-archetypes.md`; archetype validates `size`/`tier_target`/`stat_target`/`furniture` fields (`count`, `anchor`∈{wall,corner,center,free}, `linked_to`, `adjacent_to`, `separate`, `optional`, `links`, `at`)
- [X] T005 [P] Filter `obs.rooms` rows in `components/runtime/src/runtime/observe.py` — `state.rooms` is already projected (role/cells/impressiveness/beauty/cleanliness/temp/owners/at); add the >4000-cell/edge-touching skip to match bridge semantics
- [X] T006 [P] Implement `def_stats(def)` in `components/runtime/src/runtime/policy.py` — `defs.get` wrapper with per-poll cache exposing `size`, `cost`/`marketValue`, `beauty`, `linkableRange`, `coverEffectiveness` when present
- [X] T007 [P] Implement tier-profile resolution in `components/runtime/src/runtime/policy.py`: read live `defs.get(Space).scoreStages` → match to `mods.realistic_rooms_rewritten.settings` or vanilla → resolved `{rather_tight..extremely}` thresholds; inconclusive → vanilla + one logged `rooms.profile_fallback` event per run
- [X] T008 Register new fns/templates in `components/rimbrain/capability-catalog.yaml` — `space_score`, `space_tier`, `space_target`, `room_at`, `room_role_at`, `rooms_matching`, `room_stat`, `bed_demand`, `pawns_with_thought`, `pawns_wounded`, `plan_room`, `def_stats`; mark `state.rooms` space/wealth as `gap` with note

- [X] T034 Implement contract lint in `components/runtime/src/runtime/templates.py::validate_pack` — scoped to goals referencing `rooms.archetypes`/`plan_room` ops: a room goal whose `effect` predicates on `enclosed_at` alone (no role/stat predicate) is a load-time violation per `contracts/room-archetypes.md` error semantics; non-room `enclosed_at` goals are unaffected

**Checkpoint**: `rooms:`/`mods:` cfg validates; obs carries room rows; tier profile resolves vanilla under fixture defs

---

## Phase 3: User Story 1 — Declarative room archetypes (P1) 🎯 MVP

**Goal**: archetype + rect → compiled ops → built room verified by role + stats; archetype edits are pack edits only

**Independent Test**: pack-declared `bedroom` archetype on a fresh site rect in sim → walled/doored/floored/furnished room verifying role `Bedroom` + impressiveness target — zero hand-written op coordinates

### Tests for User Story 1

- [X] T009 [P] [US1] Write `components/runtime/tests/test_rooms.py` — `plan_room` compiles the bedroom archetype (walls outline, perimeter door, floor fill, furniture cells); `linked_to` lands within link radius; unfit rect → null; `optional` furnishings skip without failing
- [X] T010 [P] [US1] Write contract tests in `components/runtime/tests/test_room_contract.py` — archetype schema validation (unknown def → load error, bad rule field → violation); effect predicates using `room_stat`/`rooms_matching`/`room_role_at` resolve over fixture obs; an `enclosed_at`-only room-goal `effect` is rejected by lint (SC-2004); a synthetic archetype absent from shipped packs loads and compiles data-only (SC-2005)

### Implementation for User Story 1

- [X] T011 [US1] Implement `space_score(rect)` in `components/runtime/src/runtime/policy.py` — `1.4·standable + 0.5·passable` over `map.cell` rows (non-standable furnishings −0.9 each); cache per poll
- [X] T012 [US1] Implement `room_at(cell)`/`room_role_at(cell)`/`rooms_matching({role,min_cells,min_impressiveness})`/`room_stat(room,stat)` in `components/runtime/src/runtime/policy.py` over `obs.rooms`
- [X] T013 [US1] Implement `plan_room(rect, archetype_id)` in `components/runtime/src/runtime/policy.py` — compile walls outline + door + floor fill + furniture cells honoring `count`/`anchor`/`linked_to` (radius via `def_stats`)/`adjacent_to`/`separate`/`optional`; return `{ops, warnings}` or null on unfit; ≤36-region bound checked; existing-structure aware — impassable cells on the wall line count as placed, rect overlapping a different room's interior → null + warning (merge/split edge case)
- [X] T014 [US1] Add `rooms:` cfg + `bedroom` archetype to `components/rimbrain/packs/start-mode-v0/pack.yaml` — 4×6 footprint, wall/door/floor defs from existing `start.shelter` cfg, furniture `[Bed, Dresser(linked), EndTable(linked), StandingLamp, PlantPot(optional)]`, `stat_target.impressiveness: 40`
- [X] T015 [US1] Convert the `shelter`/`private-bedrooms` build steps in `packs/start-mode-v0/pack.yaml` to `build-layout` with `ops: "@fn:plan_room(...)"` + effect predicates on `rooms_matching` role+stat (replacing `enclosed_at`-only effects)

**Checkpoint**: sim builds the archetype bedroom and verifies role+impressiveness; suite green vs T003 baseline

---

## Phase 4: User Story 2 — Right-sized bedrooms on demand (P2)

**Goal**: one valid private bedroom per resident (couples share), sized to the active tier profile, replacing the 7×7 uniform expansion

**Independent Test**: 4-colonist sim from barracks → 4 compact bedrooms verify role+target; wall-material consumption ≥30% below the old path

### Tests for User Story 2

- [X] T016 [P] [US2] Extend `components/runtime/tests/test_rooms.py` — `bed_demand()` counts residents−couples−valid bedrooms; goal `when` gates fire on deficit; completed goal re-arms zero ops; barracks→private conversion fixture asserts zero bedless ticks mid-transition
- [X] T017 [P] [US2] Material-delta test in `components/runtime/tests/test_rooms.py` — sum ops footprint of archetype path vs legacy `govern.expansion` geometry; assert ≥30% reduction; both paths' built bedrooms reach the declared impressiveness band in the fixture (equal mood outcome, SC-2002)

### Implementation for User Story 2

- [X] T018 [US2] Implement `bed_demand()` in `components/runtime/src/runtime/policy.py` — colonist rows + `state.pawn` bed assignment/partner fields vs `rooms_matching(role:Bedroom)` count; share the per-poll pawn-detail cache with `pawns_wounded`/`pawns_with_thought`
- [X] T019 [US2] Rewrite `private-bedrooms`/`expansion` goals in `packs/start-mode-v0/pack.yaml` — `when` on `bed_demand() > 0`, footprint from archetype, effect on role+stats; keep barracks-first ordering (early shared room → later private conversion)

- [X] T035 [US2] Implement the barracks→private-bedroom conversion path in `packs/start-mode-v0/pack.yaml` — `plan_room` over the partitioned footprint + `assign-job` bed reassignment ordered target-bed-first so no colonist is bedless mid-transition (spec US2 acc.4)
- [X] T020 [US2] Migrate `govern.expansion`/`start.shelter` geometry cfg in `packs/start-mode-v0/pack.yaml` to archetype references; keep old keys readable via the existing v0-path rewrite (no breaking change)

**Checkpoint**: material-delta + demand tests green; sim bedroom count matches colonist demand

---

## Phase 5: User Story 3 — Mod-aware space tiers (P2)

**Goal**: tier-targeted sizing reads the live scoreStages — RR-Rewritten defaults under the mod, vanilla otherwise, vanilla on any doubt

**Independent Test**: two fixture profiles (vanilla vs modded scoreStages) size the same tier target differently; both verify against the live table

### Tests for User Story 3

- [X] T021 [P] [US3] Extend `components/runtime/tests/test_rooms.py` — `space_tier`/`space_target` under vanilla vs RR-default scoreStages; cfg override honored; detection-failure → vanilla + single fallback event

### Implementation for User Story 3

- [X] T022 [US3] Implement `space_tier(score)`/`space_target(tier)` in `components/runtime/src/runtime/policy.py` against the T007 resolved profile
- [X] T023 [US3] Add `mods.realistic_rooms_rewritten` cfg (package_id `Lucifer.RealisticRooms`, six thresholds + `filthTweakEnabled`) to `packs/start-mode-v0/pack.yaml`; wire `rooms.tier_table: auto` resolution order live→cfg→vanilla
- [X] T024 [US3] Apply tier targets in archetypes — bedroom carries `tier_target: average` so modded saves emit compact footprints (3×4-class) and vanilla emits 4×6-class for the same declared tier

**Checkpoint**: profile matrix tests green; tier-targeted archetype sizes differ correctly across fixture states

---

## Phase 6: User Story 4 — Stat-driven support rooms (P3)

**Goal**: dining/hospital/kitchen/workshop appear on observed need signals, targeting each role's driving stat

**Independent Test**: sim emitting `AteWithoutTable` thoughts → dining hall builds + verifies role `DiningRoom`/`RecRoom` + stat target; casualty fixture → hospital verifies role + cleanliness floor

### Tests for User Story 4

- [X] T025 [P] [US4] Extend `components/runtime/tests/test_rooms.py` — `pawns_with_thought` counts over fixture thoughts; support-room goals fire on need signals and verify role+stat (hospital: `Hospital` + cleanliness; kitchen: separate butcher placement)

### Implementation for User Story 4

- [X] T026 [US4] Implement `pawns_with_thought(def)` in `components/runtime/src/runtime/policy.py` over `state.pawn` thoughts via the shared per-poll pawn-detail cache
- [X] T036 [US4] Implement `pawns_wounded()` in `components/runtime/src/runtime/policy.py` — count colonists with bleeding/unhealed/incapacitating health conditions from `state.pawn` detail (exact health field names pinned at impl against live RPC shape; shared per-poll cache); backs the hospital `when` gate
- [X] T027 [US4] Add `dining_hall`/`hospital`/`kitchen`/`workshop` archetypes to `packs/start-mode-v0/pack.yaml` per research §6 (tables+chairs space-free, sterile floor + vitals-linked hospital, separated butcher in kitchen, tool-cabinet `links: 2` + `at: each_bench` seating in workshop — canonical fields per data-model.md, not the research §9 sketch names)
- [X] T028 [US4] Add standing goals/`options` for support rooms in `packs/start-mode-v0/pack.yaml` — `when` on `pawns_with_thought(AteWithoutTable)` / `pawns_wounded()` ≥ cfg threshold / kitchen need; `effect` on role+stat predicates

**Checkpoint**: need-driven room goals fire in sim and verify on stats, not enclosure

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] Update `components/rimbrain/capability-catalog.yaml` audit baseline + `tools/capability_audit.py` expected diff
- [X] T030 [P] Update `AGENTS.md` (020 status) and `components/rimbrain/CUSTOMIZE.md` (archetype authoring + mod profiles)
- [X] T031 Update `specs/40-work-packages/TRACEABILITY.md` rows for FR-2001..2009/SC-2001..2006 linking test evidence
- [X] T032 Run all `quickstart.md` scenarios — green; live smoke (`defs.get(Space).scoreStages` serialization check) deferred to bridge availability
- [X] T033 Full-suite regression `uv run pytest -q` — all green vs T003 baseline + new coverage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: **017 schema surface landed** (T001 gate)
- **Foundational (Phase 2)**: after Setup — BLOCKS all stories
- **US1 (Phase 3)**: after Foundational — MVP (compiler + bedroom)
- **US2 (Phase 4)**: after US1 (archetype machinery exists)
- **US3 (Phase 5)**: after Foundational (T007 profile) + US1 (tier_target field) — can parallel US2
- **US4 (Phase 6)**: after US1 — independent of US2/US3
- **Polish (Phase 7)**: all stories

### Parallel Opportunities

- T005∥T006∥T007∥T008 — obs plumbing ∥ def-stats ∥ profile ∥ catalog
- T009∥T010, T016∥T017, T021, T025 — test files in parallel
- US2 ∥ US3 ∥ US4 after US1 — different fns/goals; only `pack.yaml` edits need merge care

## Parallel Example: Foundational

```bash
Task: "Project state.rooms into obs"          # T005 observe.py
Task: "Implement def_stats fn"                # T006 policy.py
Task: "Implement tier-profile resolution"     # T007 policy.py
Task: "Register new fns in catalog"           # T008 capability-catalog.yaml
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup + Foundational
2. US1: bedroom archetype compiles, builds, verifies in sim
3. **STOP and VALIDATE**: role+stat predicates hold; archetype change requires no code edit (SC-2005)

### Incremental Delivery

1. US1 → archetype machinery (MVP)
2. US2 → right-sized bedrooms on demand (the material win)
3. US3 → mod-aware tiers (the user's mod)
4. US4 → need-driven support rooms
