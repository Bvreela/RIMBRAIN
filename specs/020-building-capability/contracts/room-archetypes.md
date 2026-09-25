# Room archetypes contract

**Status:** DRAFT
**Contract ID/version:** room-archetypes/v0
**Provider:** runtime policy (`plan_room`, stat fns) + RimBridge (`ui.build_many`, `ui.designate`, `state.rooms`, `map.cell`, `defs.get`)
**Consumers:** RimBrain packs (`start-mode-v0` expansion, future `colony-build-*` packs)
**Requirement IDs:** FR-2001..2009, SC-2001..2006

## Purpose

Pack-facing schema for declarative rooms: the `rooms:` cfg block (archetypes + tier profile), `mods:` cfg for mod-aware thresholds, and the fn surface used by goals' `when`/`effect`/`steps`.

## Operations/events/artifacts

**Cfg blocks** (pack schema v1 extension):

```yaml
rooms:
  tier_table: auto                 # auto | vanilla | realistic_rooms_rewritten
  archetypes:
    <id>: <RoomArchetype>          # per data-model.md
mods:
  realistic_rooms_rewritten:
    package_id: Lucifer.RealisticRooms
    settings: {minSpaceRatherTight: 6.5, minSpaceAverageSized: 16.5,
               minSpaceSomewhatSpacious: 28.5, minSpaceQuiteSpacious: 49.5,
               minSpaceVerySpacious: 84.5, minSpaceExtremelySpacious: 174.5,
               filthTweakEnabled: true}   # informational in v1 — no client-side consumer yet
```

**Fns** (all resolve via `policy.resolve`; string `@fn:name(args)` form):

- `plan_room(rect, archetype_id)` → ops list for `build-layout`, or `null` if the rect can't fit. Deterministic; pure function of rect + archetype + def sizes.
- `space_score(rect)` → `1.4·standable + 0.5·passable` estimate from `map.cell` rows.
- `space_tier(score)` / `space_target(tier)` → tier label / minScore under the resolved profile.
- `room_at(cell)` → room row or null; `room_role_at(cell)` → role defName or null; `rooms_matching({role, min_cells, min_impressiveness})` → rows.
- `room_stat(room_id_or_cell, stat)` → impressiveness/beauty/cleanliness/temp.
- `bed_demand()` → int deficit.
- `pawns_with_thought(def_name)` → count (need triggers: `AteWithoutTable`, awful-bedroom, disturbed-sleep).
- `pawns_wounded()` → count of colonists with bleeding/unhealed/incapacitating health conditions (hospital need trigger).
- `enclosed_at(rect, min_cells)` `[have]`; `blueprints_in(rect, defs)` `[have]` — step gating between wall and furnish ops.

**Effect predicates** (goal `effect:` specs):

```yaml
effect: {all: [{field: "@fn:room_role_at(@var:r.min)", op: eq, value: Bedroom},
               {field: "@fn:room_stat(@var:r.min, impressiveness)", op: gte, value: 40}]}
```

## Request/input schema

- `plan_room` inputs: `rect` [x,z,w,h] interior; `archetype_id` resolvable in `rooms.archetypes`.
- Furnishing entries validate against `defs.get` (exists, has `size`, placeable).
- `tier_table: auto` = live `defs.get(Space).scoreStages` → mod profile match → vanilla.

## Result/output schema

- `plan_room` → `{ops: [...], warnings: [...]}` compatible with `ui.build_many` `{ops, stop_on_error}`; `null` on unfit rect (goal fails predictably, not partial).
- `space_score` → float; `space_tier` → label string.

## Ordering and consistency

Step order inside a room goal is pack-declared (`walls → floor → furniture → assign`); blueprint-aware `when` gates between steps prevent furnishing into open walls. Re-issued ops skip existing blueprints/things (`blueprints_in`/`find_defs_in`).

## Timeouts, cancellation, and retries

Construction rides the existing `lease_ticks`/`attempts`/`escalate` machinery — real build time is game-time, not polls.

## Idempotency

`ui.build_many` ops are idempotent per cell (existing blueprint or built thing = satisfied). Archetype re-application on an already-verified room is a no-op (goal effect already holds).

## Error/failure semantics

- Unfit rect → `plan_room` null → step records `blocked`, never partial walls.
- Missing def → load-time validation error (def must resolve via `defs.buildable`).
- Stat target unreachable (archetype physically can't hit it) → detected at plan time when estimable, else after `attempts` the goal escalates per standing-goal rules.
- Detection failure for tier profile → vanilla table (strictest), recorded once per run.

## Security and privacy classification

Fair-class; no secrets, no `dev.*`.

## Compatibility/versioning

v0; additive to pack schema v1. Packs without `rooms:`/`mods:` are unaffected. A future bridge `room.stat` RPC is additive (richer `room_stat`, no signature change).

## Canonical valid examples

```yaml
- id: private-bedrooms
  when: {field: "@fn:bed_demand()", op: gt, value: 0}
  effect: {field: "@fn:rooms_matching({role: Bedroom, min_impressiveness: 40})", op: not_empty}
  steps:
    - {template: build-layout, params: {ops: "@fn:plan_room(@var:site.rect, bedroom)", stop_on_error: false}}
    - {template: roof-rect, params: {designator: Designator_AreaBuildRoof, rect: "@var:site.rect"}}
```

## Canonical invalid examples

- `effect` on `enclosed_at` only → rejected by contract lint (blueprints satisfy enclosure but not role).
- `linked_to: VitalsMonitor` where the archetype lacks the linked def and no existing thing resolves → plan-time failure.
- `tier_table: realistic_rooms_rewritten` on a save without the mod → profile resolves vanilla anyway (auto-detect wins over cfg claim).

## Provider tests

- `space_score` over fixture cells matches the formula; `space_tier` honors vanilla vs modded tables.
- `plan_room` compiles each shipped archetype to ops respecting sizes/links; unfit rects return null.
- `bed_demand` couple-aware counting; `pawns_with_thought` over fixture thoughts.

## Consumer tests

- Pack archetype builds in sim → `state.rooms` row verifies role + stat predicate.
- Vanilla vs modded profile fixtures size the same tier target differently; both verify against live thresholds.
- Re-running a completed goal dispatches zero ops (idempotent).

## Migration

Additive. Existing `start.shelter`/`govern.expansion` geometry blocks migrate to archetype equivalents; old cfg keys remain readable (v0-path rewrite already exists for other surfaces).
