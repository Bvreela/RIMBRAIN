# Feature Specification: Iterated Improvement Cycles

**Feature Branch**: `010-iterated-cycles`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User directive — run additional self-improvement loops using the save-game reload system; expand start criteria to include cooking and real food production during the early phase; add longer-run combat testing as the next progression step after Start Mode; build a test loop that incorporates these conditions, allows full save-reset cycling, and automatically fixes bugs and refines the interface on each iteration so the agent steadily improves stability, decision quality, and user experience.

## Purpose

A repeatable **cycle runner** that turns one-off validation into iterated training: snapshot a colony once, then loop — reload the checkpoint, run Start Mode (now with cooking/real meals in the exit criteria), run a bounded **combat test**, collect canonical evidence, run the improvement pass — and repeat. Each cycle is a clean experiment against the same world state, so improvements can be compared honestly across iterations.

## User Stories *(mandatory)*

### User Story 1 - Save-Reset Cycle Runner (Priority: P1)

The runtime can save a named checkpoint, run its phases, then reload that checkpoint to restore the exact world state for the next iteration — N times, unattended, with every write through the single dispatcher and every outcome in canonical evidence.

**Acceptance Scenarios**:

1. **Given** a live game and `--mode cycle --iterations N`, **When** the runner starts, **Then** it creates/loads the named checkpoint and repeats [reload → start → combat → improve] N times.
2. **Given** a crashed cycle, **When** restarted, **Then** the checkpoint save still exists and the cycle resumes cleanly.
3. **Given** `game.load` is async, **When** the runner reloads, **Then** it polls `game.status` until `playing` before proceeding — never acts on a half-loaded map.

### User Story 2 - Cooking and Real Food Production (Priority: P1)

Start Mode's exit criteria now require **real food production**: a cooking station built, a cook bill configured, and an actual meal observed on the map — not merely a growing zone. Pawns do the cooking; the agent builds and bills, then verifies.

**Acceptance Scenarios**:

1. **Given** a colony with a cooking station + cook bill + raw ingredients, **When** a meal exists (observed via `map.find`), **Then** the cooking condition holds.
2. **Given** no raw ingredients, **When** verify runs, **Then** the phase reports honest `effect_absent` (bounded by attempts, diagnosed by improve) rather than fabricating success.
3. **Given** an established colony with station+bill+meals, **When** start mode runs, **Then** the cooking phase skips with zero redundant writes.

### User Story 3 - Bounded Combat Test (Priority: P2)

After `start.completed`, the agent runs a combat exercise: snapshot the state, spawn a bounded hostile incident, defend (draft/attack through the dispatcher), verify hostiles cleared and colonists survived, then heal and restore. Longer-run = multiple rounds with escalating-but-bounded points.

**Acceptance Scenarios**:

1. **Given** `start.completed`, **When** combat mode runs, **Then** a `dev.incident RaidEnemy` at pack-bounded points fires, reflexes/defense engage, and `combat.completed` records rounds, hostiles cleared, casualties, ticks.
2. **Given** colonists cannot clear the threat within the tick budget, **When** the round times out, **Then** the round records `failed`, colonists are healed, and the checkpoint is restored — no half-fought map carries forward.
3. **Given** combat mode on a colony that never completed start, **When** invoked, **Then** it refuses (`combat.prereq`) — combat tests sit strictly after the baseline.

### User Story 4 - Improve Each Iteration (Priority: P2)

Every cycle ends with the existing improvement pass over accumulated evidence — diagnoses feed candidate packs; promotion still requires audits and happens only at the cycle boundary.

**Acceptance Scenarios**:

1. **Given** a cycle with verified defects (refusals, verify failures), **When** the cycle ends, **Then** `selfcheck.diagnosed` + audit verdicts + promotion/rejection land in evidence with reasons.
2. **Given** N cycles, **When** evidence is inspected, **Then** `cycle.completed` per iteration carries per-phase verdicts so cross-cycle trends are queryable.

## Requirements

- **FR-801** Save-reset: `game.save`/`game.load` via pack-declared templates through the single dispatcher; load polls `game.status` until playing; checkpoint name is pack config.
- **FR-802** Cooking: new start-mode baseline phases `cookstation` (build station + `ui.add_bill` recipe) and `meals` (verify `map.find` meal defs ≥1); exit eval gains the `meals` condition.
- **FR-803** Combat test: `--mode combat` — snapshot → bounded `dev.incident` raid → defend via draft/attack/jobs → verify cleared+survived → heal+restore → `combat.completed`. Requires prior `start.completed` (persisted mode flag or a fresh live completion).
- **FR-804** Cycle runner: `--mode cycle` — per iteration: load checkpoint → start → combat → improve; emits `cycle.completed` per iteration.
- **FR-805** All dev/test writes (save, load, incident, heal, spawn) are pack-declared templates dispatched through the single writer — never raw bridge calls.
- **FR-806** Boundedness: per-phase tick/attempt budgets; combat rounds and points bounded by pack config; cycles bounded by `--iterations`.
- **FR-807** Established colonies skip cooking when its effect already holds; restart mid-cycle resumes from ledger + mode state.

## Success Criteria

- **SC-801** Live cycle: save→load→start→combat→improve completes an iteration; `cycle.completed` recorded.
- **SC-802** Cooking phases verified against real game state (station + bill + meal) or honestly absent.
- **SC-803** Combat round clears spawned hostiles or records `failed`; post-state restored.
- **SC-804** Two+ cycles show stable or improving defect counts in evidence.
- **SC-805** Zero direct `game.rpc` writes for test control — all via dispatched templates.

## Boundaries / Non-Goals

- Not a difficulty-ranked curriculum — combat is a fixed bounded exercise, not adaptive scaling.
- `dev.*` calls mark the game "assisted" — acceptable for test cycles; scored episodes never enable combat/cycle modes.
- No new model tiers; improvement remains rules-only candidate packs.

## Assumptions

- `game.load` async completes in seconds; the runner polls.
- RaidEnemy at low points is survivable by a completed-start colony; failures are data, not disasters.
- `CookingSpot`/`FueledStove` are buildable without research; `CookMealSimple` needs no research.
