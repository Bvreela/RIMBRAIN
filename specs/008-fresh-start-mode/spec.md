# Feature Specification: Fresh-Start Mode (Start Mode)

**Feature Branch**: `008-fresh-start-mode`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User directive — a dedicated "fresh start" policy for the uniquely demanding first days of a run. Starting from nothing creates a brief critical window where the colony must reach baseline stability through a deliberate bootstrap sequence, then plan/prioritize until every colonist has enclosed shelter, a bed, a replenishable food source, and basic recreation — at which point Start Mode ends. Exists as its own configurable module in the brain.

## Purpose

A dedicated `start-mode` policy module (its own pack + objective workflow) that takes a brand-new colony from scattered drop pods to a stable baseline. It executes a fixed deterministic bootstrap — site selection, roofed storage zone over the starting items, unforbid, shelter construction, haul-in — then transitions to prioritized task execution until the declared exit conditions hold. Completion is a handoff, not an exit: on a held run the pack's `govern` standing goals take over — sustainment objectives that re-arm on regression and long-horizon objectives (tech-tree progression, mission offers) that engage once the colony is stable. Non-held callers (cycle phases, tests) still stop cleanly at `start.completed`.

## User Stories *(mandatory)*

### User Story 1 - Bootstrap Sequence (Priority: P1)

On a fresh map, the agent identifies an efficient nearby build site (open ground near the starting items and home center), creates a storage zone there, roofs it (enclosing walls or mountain adjacency as the map allows), unforbids all starting items, designates shelter construction at the selected spot, and directs hauling of everything into the zone.

**Why this priority**: the drop-pile decay window is the sharpest deadline in the game; this sequence is deterministic survival work, not a model judgment call.

**Independent Test**: sim fixture with a starting pile and open ground — the sequence emits zone-create, roof/wall designations, unforbid designations, build blueprints, and haul designations in the declared order, all through the single writer.

**Acceptance Scenarios**:

1. **Given** a fresh map, **When** Start Mode begins, **Then** a site-selection result (anchor cell + rect) is chosen deterministically from observed open rects ranked by declared criteria (distance to items, buildability, threat avoidance).
2. **Given** a selected site, **When** the storage zone step runs, **Then** a stockpile is created covering the starting items when they fit the zone rect, else the nearest viable rect.
3. **Given** the storage zone exists, **When** the unforbid step runs, **Then** every observed starting item is unforbidden.
4. **Given** site + zone, **When** the shelter step runs, **Then** wall/door/bed blueprints are placed at the selected spot — never on top of items, water, or existing buildings.
5. **Given** the zone and unforbidden items, **When** the haul step runs, **Then** all loose starting items are haul-designated to the zone.

### User Story 2 - Objective Graph Execution (Priority: P1)

Start Mode is expressed as an ordered objective graph of tasks in the ledger (feature 007): each phase is a task with declared resources, effect spec, lease, and attempts. Progression is verifier-gated — a phase completes only when its effect is observed (zone exists, items unforbidden, blueprints placed, items stored), never on dispatch `ok` alone.

**Why this priority**: UR-RUN-002/003 — the bootstrap must survive verify-failure and restart without skipping or double-applying phases.

**Independent Test**: run the graph against the sim; interrupt mid-graph; restart; the ledger resumes the correct phase without re-executing completed ones.

**Acceptance Scenarios**:

1. **Given** a phase whose effect is not yet observed, **When** the graph advances, **Then** it waits/retries within its attempts budget rather than marking success.
2. **Given** a process restart mid-graph, **When** the ledger reloads, **Then** completed phases stay completed and the in-flight phase re-verifies against observed state.

### User Story 3 - Baseline Completion (Priority: P1)

After the bootstrap, the agent plans and prioritizes until every colonist has: (a) enclosed shelter (a room with roof and door, no unroofed/no-door problems), (b) an owned/available bed inside a room, (c) a replenishable food source (growing zone planted OR a steward stock job targeting food OR equivalent observed mechanism), and (d) a basic recreation object (horseshoes pin or equivalent declared def). When all conditions hold for all colonists, Start Mode emits `start.completed` and stops proposing start-phase work. A held run then evaluates the pack's `govern.goals` — standing objectives declared in the pack (sustainment that re-arms when its effect lapses, then gated ambitions like research and mission acceptance) — instead of terminating.

**Why this priority**: "baseline of stability" is the user's explicit exit contract — it must be observable, all-or-nothing per colonist, and it marks the handoff from scripted bootstrap to self-directed play.

**Independent Test**: fixture states satisfying/violating each condition — the mode exits exactly when all four hold for every colonist.

**Acceptance Scenarios**:

1. **Given** 3 colonists and 2 enclosed bedrooms with beds, **When** conditions are evaluated, **Then** Start Mode remains active and the missing-bed task is prioritized.
2. **Given** all colonists sheltered+bedded, food source present, recreation built, **When** evaluated, **Then** Start Mode emits completion and disengages.

### User Story 4 - Configurability (Priority: P2)

Start Mode is its own pack (`start-mode-v0`) with tunable thresholds: zone size caps, site-ranking weights, shelter dimensions, recreation def list, food-source policy preference (growing vs steward stock job), and exit-condition definitions. It engages only when explicitly selected (`--start` mode or pack binding) — never auto-fires on a loaded save.

**Why this priority**: "configurable module in the brain" — the policy is reviewable data, and accidental activation on an established colony would be destructive.

**Independent Test**: pack edits change behavior (zone size, recreation choice) without code changes; loading the module against a non-fresh colony does nothing unless explicitly invoked.

## Edge Cases

- **No viable open rect near items**: degrade to the nearest viable rect; if none within the search radius, emit a `start.blocked` outcome and hold — never place into water/rock/buildings.
- **Items scattered beyond one zone rect**: zone covers the densest cluster; remaining items still get unforbidden + hauled.
- **Insufficient materials for the full shelter**: build the largest feasible shelter first (or sleeping spots as a degraded fallback per pack config); material shortage is observed, not assumed.
- **Roof impossible** (unsupported span, no walls yet): order walls first; roof designation follows their completion; a storage zone may function unroofed meanwhile — decay risk is recorded, not ignored.
- **Colonist count changes** (new recruit/loss mid-mode): exit conditions re-evaluate against the live roster each poll.
- **Start Mode invoked on an established colony**: the bootstrap steps detect their effects already hold (zone/rooms exist) and skip straight to condition evaluation — no duplicate designations.
- **Threats during bootstrap**: emergency reflexes retain precedence (emergencies never wait); start-mode tasks yield and resume.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-701**: a `start-mode-v0` pack declares the bootstrap templates (site-select output, zone-create, roof/wall/door/bed blueprint ops, unforbid, haul, growing/stock fallback, recreation build) as reviewable data; every template method exists in the sealed RPC inventory (inventory cross-check as in feature 004).
- **FR-702**: deterministic site selection ranks `map.open_rects` results by declared criteria (proximity to starting items, distance to home center, buildability) and anchors the choice via `anchor.set` for downstream steps and evidence.
- **FR-703**: bootstrap steps execute in declared order as ledger tasks with effect specs verified against observation (`state.storage`/`state.base`/`map.find`/`state.stocks`), all through the single writer.
- **FR-704**: unforbid covers every observed starting item (`map.find` forbidden items near home); haul designates all loose items to the zone.
- **FR-705**: exit-condition evaluator checks per-colonist shelter (enclosed room), bed-in-room, replenishable food, and recreation presence; Start Mode emits `start.completed` when all hold. Whether the run ends there is the caller's `hold` flag — held runs continue into the pack's `govern.goals` standing objectives (UR-RUN-009), bounded callers (cycle) still stop at completion.
- **FR-706**: the mode engages only via explicit selection (`--start`/`pack start-mode-v0`); auto-detection of "fresh game" is out of scope — an established colony invoked into the mode must produce zero redundant designations (effects already hold).
- **FR-707**: new event types as needed (e.g. `start.phase`, `start.completed`) registered native in event-map + schemas + corpus; transitions continue to use `task.transition`.
- **FR-708**: emergencies retain precedence — reflexes evaluate before start-mode task progression each poll.
- **FR-709**: all start-mode work is ledger tasks — surviving restart, reconciling observed effects before retry (UR-RUN-001..004).

### Success Criteria

- **SC-701**: sim fixture — a fresh-start scenario reaches the completion event with the full ordered evidence trace (site → zone → unforbid → shelter → haul → conditions) and zero refusals.
- **SC-702**: forced restart mid-graph resumes at the correct phase; no phase executes twice, no completed phase re-dispatches.
- **SC-703**: established-colony invocation produces zero designations (skip-to-evaluate).
- **SC-704**: exit evaluation is correct per colonist — partial coverage (2/3 bedded) keeps the mode active and prioritizes the gap.
- **SC-705**: pack edits (zone size, recreation def, food policy) change behavior without code changes.

## Constraints

- Single writer preserved: all game writes via the Dispatcher; the start-mode planner/proposer never calls the bridge.
- Deterministic bootstrap: site selection, sequencing, and effect verification are code/data — models may only inform post-bootstrap prioritization, never place structures directly.
- Fail-closed: no viable site or missing materials blocks with a recorded outcome; never place on water/rock/buildings/items.
- Real-colony-data-only rule applies: site/item/colonist decisions come from observation, never assumptions.
- Pack is reviewable data (validated like core-survival-v0); the mode is opt-in only.
- Fair-mode: `start-mode-v0` is `class: fair` — zero `dev.*` methods end to end (UR-BRN-018). Spawn/heal test tooling and the scripted combat section live in `dev-lab-v0` (`class: dev`), refused at load under `--fair`.
- Post-start goals are pack data (`govern.goals`): ordered standing objectives with `when` engagement gates and verifier-checked `effect`s; terminal goals re-arm only while the observed effect has lapsed. Mission completion beyond accepting an offer is emergent play — out of scope for v0.
