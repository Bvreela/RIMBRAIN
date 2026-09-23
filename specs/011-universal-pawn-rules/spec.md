# Feature Specification: Universal Pawn Rules & Start Mode v2

**Feature Branch**: `011-universal-pawn-rules`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User directive — pawns are never idle (idle time is a planning failure to be corrected immediately); combat prioritizes efficiency (stop attacking downed enemies, switch targets, melee/fast pawns chase fleeing enemies); post-combat strips downed enemies for untainted gear before they die. Start Mode must additionally arm colonists by skill (shooters→guns, melee→close weapons+armor), place recreation beside the shelter, run a campfire with a meal buffer above daily consumption, sow rice on the most fertile soil near the shelter, and create a second roofed overflow storage zone outside the shelter (interior reserved for food/medicine/critical).

## Purpose

Two layers:

1. **Universal rules** (`universal` pack config) — invariants that hold in every mode and every phase of the game: zero idle colonists, efficient target discipline during combat, and post-combat stripping. These run inside the normal loop/combat/start steps as a mandatory pass, not a separate mode.
2. **Start Mode v2** — extends the existing bootstrap with arming, campfire + meal buffer, fertile-soil rice sowing, and a second overflow stockpile, so day-one colonies reach a genuinely playable baseline.

## User Stories *(mandatory)*

### User Story 1 - No Idle Colonists (Priority: P1)

Every poll, the runtime checks each colonist's current job. Any colonist observed idle (no current job / idle job) gets an immediate corrective assignment from the pack's idle-fallback work list — never a silent stall.

**Acceptance Scenarios**:

1. **Given** a colonist with no active job, **When** any mode polls, **Then** a work assignment is dispatched the same iteration and an `action.issued` event records it.
2. **Given** all colonists busy, **When** polling, **Then** the idle check costs zero writes.
3. **Given** idle assignments are themselves refused/failing, **When** they repeat, **Then** the defect lands in evidence for the improve pass — not an infinite spam loop.

### User Story 2 - Efficient Combat Discipline (Priority: P1)

During combat, downed hostiles are never attacked again; attack orders switch to the next living hostile. Fleeing hostiles are chased by the fastest/melee-capable colonist rather than left to wander.

**Acceptance Scenarios**:

1. **Given** a hostile whose health/downed state reads as downed, **When** combat targets are chosen, **Then** that hostile is excluded from attack orders.
2. **Given** a hostile moving away from home (dist_home rising / lord=null fleeing), **When** a melee-capable colonist is available, **Then** a melee chase order is issued to that colonist.
3. **Given** a downed-but-alive hostile after combat clears, **When** the round ends, **Then** a `strip` designation is dispatched on it before the checkpoint restore — gear recovered untainted.

### User Story 3 - Arming on Day One (Priority: P2)

Start Mode arms colonists before/while building: best shooting skill gets the best gun, best melee skill gets a melee weapon, available armor goes on front-line pawns — all via `ui.job Equip`/`Wear` on observed map items.

**Acceptance Scenarios**:

1. **Given** weapons on the map and colonists with known skills, **When** start mode runs, **Then** equip orders route gun→best-shooter, melee→best-melee, armor→front-liner.
2. **Given** no weapons on the map, **When** the phase runs, **Then** it verifies `effect_absent` honestly and records it — no fabricated arming.

### User Story 4 - Campfire, Meals Buffer, Rice, Overflow Storage (Priority: P2)

Start Mode builds a campfire (`CookingSpot`) immediately, sets a `CookMealSimple` bill with `TargetCount` = colonists×meals_per_day + pack buffer, sows `Plant_Rice` on the most fertile open soil near the shelter, and creates a second roofed stockpile outside the shelter whose settings disallow food/medicine (reserved for the interior zone).

**Acceptance Scenarios**:

1. **Given** raw food available, **When** cookstation+meals phases run, **Then** the bill targets `colonists * daily_meals + buffer`, and a real meal is verified on the map.
2. **Given** multiple candidate cells, **When** the growing zone is placed, **Then** `map.cell` fertility is compared and the zone lands on the most fertile rect; plant is set to `Plant_Rice`.
3. **Given** the overflow phase, **When** it completes, **Then** a second labeled stockpile exists outside the shelter rect, roofed, with `ui.storage` filters reserving food/medicine/critical items for the interior zone.

## Requirements

- **FR-901** Universal rules module (`runtime/universal.py`): `apply(obs, dispatcher, phase)` runs inside every mode's poll loop (start, combat, loop, cycle); performs idle-pawn correction, combat target discipline, and post-combat strip checks through the dispatcher only.
- **FR-902** Idle rule: colonists with no/idle current job get an assignment from pack `universal.idle_jobs` (ordered JobDef list, e.g. `HaulToCell`, `Mine`, `CutPlant` with a map-derived target); repeated failures quarantine that fallback, not loop forever.
- **FR-903** Combat discipline: hostile list filters `downed`/`dead` before target selection; fleeing hostiles (pos receding / unlorded after spawn window) get a melee chase order from the fastest available colonist; attack re-issue respects the cooldown.
- **FR-904** Strip rule: after a combat round clears or times out, `ui.designate strip` is dispatched for every hostile that is downed-but-alive or a fresh corpse.
- **FR-905** Arming phase (`start.arm`): reads `state.pawn` skills per colonist, `map.find`/`state.stocks` weapons+apparel, dispatches `ui.job Equip|Wear` ordered gun→best Shooting, melee→best Melee, armor→highest Melee/shooting frontliner.
- **FR-906** Cooking: campfire preferred (`CookingSpot`, no power); bill mode `TargetCount` with `count = colonists × meals_per_day + buffer` from pack `cooking` config.
- **FR-907** Fertile growing zone: candidate cells sampled near the site via `map.cell` (`fertility` field); zone placed at max fertility; `ui.zone set_plant Plant_Rice`.
- **FR-908** Overflow storage: second stockpile via `ui.zone create_stockpile` outside the shelter rect, roofed (`Designator_AreaBuildRoof`), `ui.storage` disallow food/medicine categories so interior stays reserved.
- **FR-909** All writes through the single dispatcher as pack-declared templates (`equip-pawn`, `wear-apparel`, `assign-job`, `strip-pawn`, `set-plant`, `edit-storage`, `create-growing`); fail-closed on unknown/malformed.
- **FR-910** Bounded: idle correction and strip checks are per-poll O(pawns+hostiles); arming/armor phases bounded by attempts; universal rules never block emergency reflexes.

## Success Criteria

- **SC-901** Live: a deliberately idled colonist receives work within one poll; evidence shows `action.issued` for the assignment.
- **SC-902** Live combat: no `attack-target` dispatch hits a downed hostile; a fled hostile receives a chase order; strip designations appear after clear.
- **SC-903** Live start: armed colonists observed (gear via `state.pawn`), meal bill count = formula, rice zone on fertile cell, two zones with correct filters.
- **SC-904** Suite + corpus + validators green; new event types (`pawn.idle_assigned` optional) schema'd if emitted.
- **SC-905** Cycle iteration end-to-end with universal rules active: start→combat→improve completes; zero idle-pawn polls recorded.

## Boundaries / Non-Goals

- Universal rules are deterministic pack config — no model calls in the hot path.
- "Meaningful task" = pack-declared fallback jobs; tactical priorities still belong to the planner layer.
- Strip runs during test/combat restore windows; it does not violate the single-checkpoint restore contract.
- No new event types unless a rule genuinely needs one — prefer existing `action.*`.

## Assumptions

- `state.pawn` exposes skills + current job; `state.pawns` exposes enough to find idles cheaply (fallback: per-pawn `state.pawn` when the brief lacks job).
- `map.cell` returns `fertility` per cell; sampling a small grid near the site is cheap.
- `Plant_Rice` and `CookingSpot` need no research on this scenario.
- `ui.job Equip/Wear` accept `target` as a thing id from `map.find`/`state.stocks`.
