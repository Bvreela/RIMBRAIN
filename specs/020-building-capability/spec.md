# Feature Specification: Building / Room Capability

**Feature Branch**: `feature/020-building-capability`

**Created**: 2026-09-24

**Status**: Draft

**Input**: `specs/020-building-capability/research.md` — RimWorld room-stat/role mechanics + Realistic Rooms Rewritten settings; "a building primitive to define optimal room size and furnishings — inform and improve our build primitives for rooms, including settings for the mod Realistic Rooms Rewritten."

**Constitution hooks**: Principle IX (room archetypes, sizes, furnishing lists, stat targets are pack data; runtime ships the layout compiler + stat fns only), I (verifier-checked effects: a room goal completes only when observed stats/role satisfy the declared predicate), IV (mod profile is explicit cfg, detected, never assumed).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Declarative room archetypes (Priority: P1)

A pack declares a named room archetype — footprint, wall/door/floor defs, and a furnishing list with placement rules — and the runtime compiles it into a build layout and verifies the finished room (enclosed, correct role, stat targets). Adding or editing a room type is a pack edit, never a code change.

**Why this priority**: This is the primitive itself. Today's packs hand-encode per-op cell math (wall rects, door cell, furniture cells) per room — one archetype compiled to a layout replaces all of it and makes room design pack-authorable.

**Independent Test**: A pack declaring a `bedroom` archetype, applied to a fresh site rect in sim, produces a walled, doored, floored, furnished room that verifies as role `Bedroom` at the declared stat target — driven entirely by archetype data.

**Acceptance Scenarios**:

1. **Given** an archetype with footprint + furnishings, **When** the goal's steps run, **Then** one layout call places walls (outline), door(s), floor (fill), and each furnishing at a rule-conforming cell, and the room verifies enclosed.
2. **Given** a furnishing with a link/adjacency rule (dresser to bed, vitals monitor to hospital bed, tool cabinet to benches), **When** the layout compiles, **Then** the furnishing lands inside the required radius of its linked item.
3. **Given** a rect too small for the archetype footprint, **When** the layout compiles, **Then** the step fails predictably (not a partial room) and the failure is recorded.
4. **Given** a pack edit changing the archetype's footprint or furniture list, **When** the next goal re-arms, **Then** the new shape builds with no code change.

---

### User Story 2 - Right-sized bedrooms on demand (Priority: P2)

The colony maintains one valid private bedroom per resident (couples share) — building right-sized rooms per the active space-tier profile instead of today's blanket 7×7 — converting the early barracks as capacity grows, and never wasting labor on over-provisioned rooms.

**Why this priority**: The immediate, measurable win: current packs build ~49-cell rooms where a ~24-cell furnished room reaches the same mood band — ~40% wall/labor savings per bedroom and faster colony bootstrap.

**Independent Test**: Sim colony of 4 colonists from barracks: private-bedroom demand resolves to 4 compact bedrooms at the declared stat target; build materials consumed drop measurably vs the existing 7×7 expansion path.

**Acceptance Scenarios**:

1. **Given** colonists exceeding valid-bedroom count, **When** the housing goal evaluates, **Then** it proposes bedrooms sized to the active tier profile (e.g. 4×6 vanilla / 3×4 under the mod profile) and verifies role `Bedroom` per room.
2. **Given** a furnished bedroom, **When** stats are checked, **Then** it reaches at least the pack's impressiveness target for its tier (default "decent") — no room ships below target.
3. **Given** a loving couple, **When** demand counts, **Then** they consume one bedroom, not two.
4. **Given** the early barracks once private rooms exist, **When** the conversion step runs, **Then** beds reassign without leaving anyone bedless mid-transition.

---

### User Story 3 - Mod-aware space tiers (Realistic Rooms Rewritten) (Priority: P2)

Room sizing decisions read the *live* space-tier thresholds: when Realistic Rooms Rewritten is loaded, its configured tier values apply (defaults 6.5/16.5/28.5/49.5/84.5/174.5); vanilla values otherwise. Tier-gated requirements (e.g. title room minimums) size against whichever table is in force.

**Why this priority**: The user runs the mod; building to vanilla thresholds under it wastes space, and building to modded thresholds without it fails requirements. Detection must be real, not assumed.

**Independent Test**: Two runs — one vanilla-profiled, one with modded scoreStages — size a tier-targeted room differently and both verify against the actual observed thresholds.

**Acceptance Scenarios**:

1. **Given** the mod loaded at defaults, **When** the tier profile resolves, **Then** "average-sized" targets ≥16.5 space, not 29.
2. **Given** no mod, **When** the profile resolves, **Then** vanilla thresholds apply — and a room sized to modded tiers would NOT have been emitted.
3. **Given** detection cannot run, **When** the profile resolves, **Then** the vanilla profile applies (fail-safe to the stricter table).
4. **Given** custom (non-default) mod values, **When** the live scoreStages are read, **Then** the pack honors the live values, not baked-in mod defaults.

---

### User Story 4 - Stat-driven support rooms (Priority: P3)

Support rooms appear when colony needs demand them: a dining hall once pawns eat without tables, a hospital once casualties/recurring wounds justify it, a kitchen separate from the workshop once food-poisoning risk matters — each targeting the stat that drives its role (impressiveness for mood rooms, cleanliness for hospital/kitchen/lab).

**Why this priority**: These rooms compound mood and health outcomes but aren't survival-critical — they schedule after shelter/beds/food.

**Independent Test**: A sim colony emitting "ate without table" thoughts gets a dining hall whose observed stats meet the pack target; a colony with recurring injuries gets a floored, monitored hospital.

**Acceptance Scenarios**:

1. **Given** pawns carrying the "ate without table" thought, **When** goals evaluate, **Then** a dining-room candidate outranks cosmetic work and builds at the declared target.
2. **Given** a hospital goal, **When** it completes, **Then** the room verifies role `Hospital`, cleanliness at the pack floor, and vitals-monitor linkage per archetype.
3. **Given** a kitchen goal, **When** it completes, **Then** the stove room is separate from the butcher/dirty production per archetype rules.
4. **Given** any support room, **When** it verifies, **Then** `state.rooms` shows the declared role and the stat predicate holds — not merely that walls exist.

---

### Edge Cases

- **Blueprint vs finished**: a goal's effect must not verify on blueprints — `enclosed_at` sees rooms only when walled; verification waits for construction completion, with blueprint-aware gating between steps.
- **Partial/aborted builds**: a failed furnish step must not leave a "bedroom" with the bed missing — effect predicates check contents, not just enclosure.
- **Room merge/split**: placing a door or removing a wall can merge rooms and change roles/stats — layout ops must consider existing structure, and effects re-verify post-build.
- **Max room size**: footprints beyond ~36 map regions degrade to non-room indoors — archetypes stay bounded; oversized requests fail predictably.
- **Vanilla-vs-mod mismatch**: building to modded tiers without the mod produces undersized rooms that fail tier-gated requirements — detection defaults to vanilla (strictest) on any doubt.
- **Temperature/light floors**: archetypes may carry optional climate/light entries; absence must not fail the room — they're pack-optional enrichments, not role requisites.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-2001**: Packs MUST be able to declare named room archetypes: footprint (w×h or cell count), wall/door/floor defs, and a furnishing list where each entry may carry placement rules (count, wall-anchored, linked-to with radius, adjacency, separate-room, optional).
- **FR-2002**: The runtime MUST provide a layout capability that compiles an archetype + target rect into an ordered build op list (wall outline, door cell, floor fill, furnishing cells) honoring footprint fit, furnishing sizes, link radii, and standability — failing predictably when the rect can't fit.
- **FR-2003**: Room verification MUST support predicates over observed rooms: enclosure, role, cell count, and the exposed stats (impressiveness, beauty, cleanliness, temperature) — goals verify on stats, not on blueprint placement.
- **FR-2004**: The runtime MUST provide fns for space-score estimation from cell data, space-tier lookup against the live tier table, room lookup by cell/rect, bed demand vs valid bedrooms, and per-thought pawn counts for need triggers.
- **FR-2005**: A mod profile MUST be pack-declared cfg with per-install values (Realistic Rooms Rewritten's six space-tier thresholds and filth-beauty toggle), and detection MUST read the live thresholds from def metadata rather than assuming defaults — vanilla applies whenever detection is inconclusive.
- **FR-2006**: Archetypes and thresholds MUST be pure pack data — adding a room type, changing a size, or swapping a furnishing list requires no runtime edit.
- **FR-2007**: Build steps MUST support idempotent re-issue — re-running a partially-built room's ops skips completed cells/blueprints instead of erroring (existing `stop_on_error: false` + blueprint-aware checks).
- **FR-2008**: Housing goals MUST be expressible as standing goals/goal options with `when` gates on need signals (bed deficit, mood thoughts, casualty recurrence) and `effect` predicates on room stats — scheduled after survival-critical phases per pack ordering.
- **FR-2009**: Room-related writes MUST go through the existing single-writer path and produce standard action/decision records; no new dispatch authority is introduced.

### Key Entities

- **Room archetype**: pack-declared recipe — footprint, materials, floor, furnishing rules, stat target, role expectation.
- **Space-tier profile**: the six tier thresholds in force (vanilla or modded), resolved from live def data with cfg override.
- **Room observation**: observed room row (role, cells, stats, owners) — the verification unit.
- **Furnishing rule**: per-item placement constraint (link, adjacency, separation, optionality) consumed by the layout compiler.
- **Bed demand**: residents minus valid bedrooms, couple-aware — the housing-goal trigger signal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-2001**: A pack-declared bedroom archetype builds and verifies end-to-end in sim with zero hand-written op coordinates in the pack (archetype data only).
- **SC-2002**: Private-bedroom construction consumes ≥30% less wall material per colonist than the existing uniform-size expansion path at equal mood outcome.
- **SC-2003**: Under the mod profile, tier-targeted rooms size to the modded thresholds; under vanilla, to vanilla — 100% correct profile selection across both fixture states.
- **SC-2004**: 100% of room goals verify against observed role + stat predicates (no goal completes on blueprint placement alone).
- **SC-2005**: Adding a new archetype to a pack requires only data edits — demonstrated by a test that introduces an archetype not present in shipped packs.
- **SC-2006**: Failed or undersized rects produce a recorded failure, never a silently partial room.

## Assumptions

- `state.rooms` (role, cells, impressiveness, beauty, cleanliness, temperature) is the verification surface; space and wealth are estimated client-side unless/until a bridge-side stat surface lands — estimation is sufficient for v1.
- Furniture stats (size, link radius, beauty, cost) resolve through existing def metadata; archetypes reference def names, not numbers.
- Mod detection via def metadata (`Space` scoreStages) is the designed path; if the field doesn't serialize live, a small bridge extension is the fallback — either way the pack contract is "read the live table."
- Right-sizing applies to new construction and pack-driven conversions; it does not mandate demolishing existing oversized rooms.
- Construction labor/material logistics stay with the existing Steward work/stock machinery; this feature owns only what to build and whether it verifies.
