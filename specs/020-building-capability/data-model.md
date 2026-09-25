# Data Model: Building / Room Capability

## Entities

### RoomArchetype (pack-declared recipe)

```yaml
id: bedroom                     # archetype name
size: {w: 4, h: 6}              # interior footprint (cells)
tier_target: average            # optional space-tier goal (profile-relative)
stat_target: {impressiveness: 40, cleanliness: null}  # effect predicate
wall: Wall                      # def; stuff via stuff_preference
door: Door                      # def + side/cell rule
floor: Carpet | null            # def; null = terrain
roof: true                      # roof-rect after walls
furniture:
  - {def: Bed, count: 1, anchor: wall}
  - {def: Dresser, linked_to: Bed}
  - {def: EndTable, linked_to: Bed}
  - {def: StandingLamp, count: 1}
  - {def: PlantPot, optional: true}
```

Furnishing rule fields: `count`, `anchor` (wall/corner/center/free), `linked_to` (def within link radius), `adjacent_to`, `separate` (must be own room/dirty zone), `optional` (skip on failure without failing the room).

### SpaceTierProfile (resolved cfg)

```
{rather_tight, average, somewhat, quite, very, extremely} : float thresholds
source: live defs.get(Space).scoreStages | mods.<id>.settings cfg | vanilla
```

Resolution order: live def values → pack cfg override → vanilla defaults. Detection failure → vanilla.

### RoomObservation (`state.rooms` row — verification unit)

| field | type | notes |
|---|---|---|
| id, role, cells | — | role defName e.g. `Bedroom` |
| outdoors, temp | — | psychologically-outdoors flag, °C |
| impressiveness, beauty, cleanliness | float | exposed stats |
| owners | [names] | bed assignments |
| at | [x,z] | anchor cell |
| space, wealth | — | **not exposed**; `space_score(rect)` estimates |

### BedDemand (goal trigger)

`colonists + pending guests − couples-shared − valid bedrooms` — valid = role `Bedroom`, assigned, stat target met.

### FurnishingRule → placement constraint kinds

| rule | meaning |
|---|---|
| `linked_to` | within the linked facility's radius of target def |
| `anchor: wall` | cell adjacent to room perimeter |
| `separate` | must not share the room with flagged-dirty/other items |
| `optional` | skip if no valid cell — never fails the archetype |

## Validation rules

- Footprint ≥ furniture minimum cells; ≤ ~36 map regions (≈50×50 bound checked at compile).
- `tier_target`/`stat_target` must reference resolvable tiers/stats.
- `linked_to` targets must exist in the same archetype or resolve to an existing thing.
- Door cells must sit on the room perimeter and remain reachable (`map.reachable`).
- A room goal's `effect` MUST predicate on role/stats — `enclosed_at` alone is insufficient (blueprint-vs-finished).

## State transitions (per room goal)

`proposed → ops-dispatched (blueprints) → constructing (lease window) → verifying (enclosed+role+stats) → succeeded | failed(retry/backoff)`
lapses: role lost (furniture removed/bed unassigned) → re-arm via standing-goal machinery.
