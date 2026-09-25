# Feature Specification: Combat Capability

**Feature Branch**: `feature/019-combat-capability`

**Created**: 2026-09-24

**Status**: Draft

**Input**: `specs/019-combat-capability/research.md` — RimWorld combat mechanics extracted against the bridge/Steward surface; "per-pawn list of actions for fastbrain optimizing per-pawn combat strategy based on skills and gear vs enemy type, number, and threat level."

**Constitution hooks**: Principle IX (all tactics/thresholds/rules are pack data; runtime ships capability primitives only), II (single writer; model picks from bounded lists, never free calls), I (deterministic fallback = best-fit option before model authority), VI (shadow→trial→authority evidence gates apply to combat picks).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Colony defends itself without scripting (Priority: P1)

A raid arrives during a fair live run. The brain detects hostiles, classifies them (engage vs watch), drafts every combat-capable pawn, positions them at cover-aware rally cells, orders attacks when the enemy closes (overrun), and stands everyone down after a hostile-free hysteresis window — all from pack-declared rules and per-pawn options, with zero dev-class tooling and zero human orders.

**Why this priority**: "Defend or die" is the precondition for every other colony capability. The current draft-all→attack-nearest rules are the MVP to beat; this story is the baseline the rest tune.

**Independent Test**: Dev-harness spawn (`dev-lab-v0` combat phase) or a natural raid in sim/live: hostiles die or flee, colonists survive at a strictly better rate than the existing draft-all rule, and all pawns stand down + restore areas afterwards.

**Acceptance Scenarios**:

1. **Given** living hostiles inside the Home area or within the pack's engage radius, **When** a poll runs, **Then** every eligible fighter is drafted and assigned a distinct rally cell — and no ineligible pawn (downed, juvenile, incapable-of-violence, prisoner, low-health) is drafted.
2. **Given** only distant/staging hostiles (siege camp, sleeping, outside engage radius), **When** a poll runs, **Then** no pawn is drafted — the colony watches instead of engaging.
3. **Given** a hostile inside the overrun radius or Home, **When** a poll runs, **Then** every armed fighter attacks its nearest living hostile — downed and dead hostiles are never targeted.
4. **Given** the map has been hostile-free for the pack's release window, **When** a poll runs, **Then** drafted pawns undraft, non-fighter area restrictions lift, and the release is recorded as a decision/event.
5. **Given** a fight lasting past the pack's prolonged threshold, **When** it ends, **Then** evidence records the engagement duration for the improvement loop.

---

### User Story 2 - Per-pawn combat action lists through the decide stage (Priority: P2)

Each poll, the action-list compiler offers every colonist a small set of combat options whose eligibility and priority already encode that pawn's skills, weapon, and the enemy's type/count/threat — the selector picks one option per pawn, and the deterministic `priority_head` fallback is itself the best-fit choice when the model is shadowed or down.

**Why this priority**: This is the fastbrain integration the feature exists for — per-pawn optimization lives in compile-time `when` gates + `priority` scores, so fallback quality equals model-pick quality in the common case.

**Independent Test**: A scripted fight with a mixed squad (a strong-melee pawn, a good shooter, a non-fighter): the shooter is offered/assigned ranged-hold or kite options, the brawler melee-block or attack, the non-fighter shelter — and disabling the endpoint produces the same assignments via fallback.

**Acceptance Scenarios**:

1. **Given** N colonists each with ≥1 eligible combat option, **When** the action list compiles, **Then** each `q.pawn.<id>` question offers only options whose gates pass for that pawn (no option a pawn is ineligible for), and colony+pawn candidates together respect the ≤20 hard bound.
2. **Given** a ranged pawn who outranges the nearest hostile and a retreat lane, **When** options compile, **Then** a kite/reposition option is offered; given a pawn who is outranged AND outrun, **Then** retreat ranks above attack.
3. **Given** a pawn whose food or rest drops below the relief floor while no hostile is near, **When** options compile, **Then** a relieve option is offered — and is suppressed entirely while the colony is overrun.
4. **Given** the select endpoint unreachable or returning an out-of-set pick, **When** the pick applies, **Then** each pawn receives the highest-priority offered option and the degradation is recorded.
5. **Given** a pawn with an active manual touch from another writer, **When** options compile, **Then** that pawn is excluded from combat candidate generation for the touch window.

---

### User Story 3 - Adaptive tactics by pawn build and enemy composition (Priority: P3)

The same pack produces different behavior against different threats: melee-heavy raids draw blockers into a choke while shooters hold cover; outranged defenders fall back; fast melee targets trigger door/choke responses instead of futile kiting; fleeing humans get chased by the best melee runner while mechanoids are fought to destruction.

**Why this priority**: Where the capability stops being a draft script and becomes tactics — but it's strictly additive over US1/US2.

**Independent Test**: Parameterized enemy compositions (melee animals, ranged raiders, mechanoids, mixed) each produce the matching option mix in candidate lists and the correct per-pawn assignments.

**Acceptance Scenarios**:

1. **Given** hostiles that are majority melee-capable and a defensible choke exists, **When** options compile, **Then** top-melee-fit pawns are offered blocking cells and ranged pawns covered firing cells.
2. **Given** a hostile whose weapon range exceeds the defender's, **When** options compile, **Then** hold/kite options are suppressed for that pawn against that target.
3. **Given** hostiles in the fleeing set, **When** options compile, **Then** chase options appear only for pawns meeting the pack's chase criteria (melee fit, speed).
4. **Given** a bleeding-out or sub-floor-health fighter, **When** options compile, **Then** retreat outranks every combat option for that pawn.

---

### User Story 4 - Post-combat recovery (Priority: P3)

After release, the colony converts the aftermath: downed hostiles are stripped or captured before they die, downed colonists are rescued, and the engagement's outcome is logged for the improvement loop.

**Why this priority**: Loot and captured-recruit value is where raids pay for themselves; rescue is already partly covered by existing rules.

**Independent Test**: A scripted raid leaving downed hostiles and one downed colonist: hostiles get strip designations (or capture orders per pack config), the colonist gets rescued, and `combat_released`-equivalent evidence exists.

**Acceptance Scenarios**:

1. **Given** downed hostiles at release, **When** cleanup runs, **Then** strip designations land per pack policy and capture options appear only when capacity (free beds/prison space) exists.
2. **Given** a downed colonist mid-fight, **When** options compile, **Then** a rescue option is offered to a pawn whose route is safe per pack criteria.
3. **Given** the engagement ends, **When** evidence is written, **Then** duration, hostiles handled, and any downed/colonist losses are recorded for improvement metrics.

---

### Edge Cases

- **Mixed raid timing**: a second raid lands during cleanup of the first — release must not fire while new living hostiles exist; hysteresis window restarts.
- **Manhunter conditional**: manhunters engage only while a colonist is outside Home; everyone-sheltered means watch, not attack.
- **Friendly/neutral in threat list**: berserk colonists, rebelling slaves, prison-breakers, and colony animals must never be engaged as hostiles.
- **Fogged hostiles**: targets hidden by fog are excluded from engagement until revealed.
- **Two combat writers**: pack-driven pawn orders are manual touches — while they stand, the in-mod standing combat order skips those pawns; a pack must declare whether it delegates to or owns the order. **Resolved: delegate — the order is the base-layer executor (pack sets rally/enables via standing-order calls), while order state feeds observation so fastbrain pawn options act as informed surgical overrides the order then honors via the touch window.**
- **Downed-but-armed hostile**: stripping a downed hostile while others fight must not pull a fighter off the line; cleanup waits for release or safe windows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-1901**: The capability catalog MUST expose pack-callable combat actions covering: draft/undraft, move-to-cell, attack-target (ranged/melee inference), cancel/interrupt job, restrict-to-area, set hostility response, field-tend, rescue, capture, ingest combat drug, designate strip/hunt, animal guard/release, rally-rect set, standing-order run/release.
- **FR-1902**: Packs MUST be able to express threat classification as data — predicates over hostile kind/faction/position/lord-duty/mental-state/fogged/downed, Home-area membership, and configurable radii (engage, overrun, near-hostile) — with zero runtime constants.
- **FR-1903**: The runtime MUST provide selectors/fns for: living hostiles, downed hostiles, fleeing hostiles, engaged-vs-watching classification, hostiles-inside-Home, hostiles-within-radius, draftable pawns, pawn combat fitness (skill/weapon/gear/speed), weapon range/class by def, and outranging/outrunning comparisons between a pawn and a hostile.
- **FR-1904**: The per-pawn decide surface MUST support pack-declared combat options per pawn (eligibility gates + priority expressions + resolved params) such that the deterministic fallback order equals best deterministic assignment — every combat mode reachable without a model call.
- **FR-1905**: The combat posture MUST be pack-data colony modes — `watch`, `engage`, `hold`, `overrun` — plus the `release` event and per-pawn side-paths (`relieve`, `retreat`); hysteresis applies (release only after a hostile-free window; relief only below need-floor AND clear of nearby hostiles AND not overrun; re-draft only above recover threshold).
- **FR-1906**: All combat rules and per-pawn options MUST be expressible in fair-class packs — no `dev.*` dependency; dev-class spawn/heal harness stays in `dev-lab-v0` unchanged.
- **FR-1907**: Manual-touch interlock MUST be honored — pawns under another writer's active touch are excluded from combat candidates. The default authority split is **delegate**: the standing combat order owns draft/rally/hold/release (pack controls it via order calls only), order state is exposed into observation, and per-pawn options serve as surgical overrides (retreat, focus-fire, block) that the order respects through the touch window.
- **FR-1908**: Combat decisions MUST emit decision/evidence records consistent with the existing decide-stage contract (offered/pick/applied/fallback/shadow) plus engagement lifecycle events (engaged, overrun, released, prolonged).
- **FR-1909**: Rally-cell assignment MUST produce distinct cover-preferring positions per fighter — same fighter never assigned two cells, two fighters never one cell.
- **FR-1910**: Retreat MUST be winnable-or-safe evaluated per pawn — retreat options suppress when no safe destination exists; kite options suppress when the pawn lacks a range or speed advantage.

### Key Entities

- **Combat mode**: colony-level state (`watch`/`engage`/`overrun`/`hold`) derived per poll from hostile classification; gates which per-pawn options compile.
- **Threat row**: hostile observation (position, def, faction, lord duty, mental state, weapon def, health, dist-to-home, fogged) — unit of classification.
- **Fighter eligibility**: per-pawn predicate set (spawned, not downed/prisoner/slave/juvenile, violence-capable, armed or pack-permitted-unarmed, health above floor, needs above relief floor, untouched).
- **Combat option**: pack-declared candidate (`id`, `template`, `when`, `needs`, `params`, `priority`) resolving to one dispatch per pawn per pick.
- **Rally**: pack-configured rect whose assignable cells are scored by cover and spacing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-1901**: In the dev-harness raid scenario, the combat pack repels the spawned raid with zero human/agent manual orders and strictly ≤ the colonist-injury count of the existing draft-all rule at equal colony size.
- **SC-1902**: 100% of hostile engagements produce a recorded classify→engage→release lifecycle with no attacks on downed/dead/fogged hostiles.
- **SC-1903**: With the selector endpoint offline or returning invalid picks, the applied option equals the highest-priority offered option on every poll — the deterministic fallback IS the compile-time best (sim-verified; shadow-mode agreement is tracked as a live-trial metric, not a gate).
- **SC-1904**: Candidate lists never exceed the 20-item bound even at 15 colonists × full option vocabulary (compile-time pruning verified).
- **SC-1905**: Stand-down completes within the pack's release window of the last living hostile and restores pre-combat area restrictions for every restricted pawn.
- **SC-1906**: Siege/staging/far threats cause zero drafts across a multi-day watch scenario (no false engagement).

## Assumptions

- The decide stage (feature 017 US2) and `pawn_scope` option machinery are landed dependencies, not part of this feature.
- Fair-class combat is the scored target; the dev harness exists only to exercise it.
- Enemy weapon range is resolved from hostile `weapon` def via def metadata; enemy speed is approximated until a richer pawn-stats surface exists — kite checks remain conservative.
- LOS/exact cover score are not required for v1 — rally/firing cells approximate cover from cell contents; a bridge-side LOS/cover surface is a possible follow-up, not a blocker.
- Combat-evidence feeds the existing improvement loop; no new evidence pipeline is introduced.
