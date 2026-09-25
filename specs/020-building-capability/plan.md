# Implementation Plan: Building / Room Capability

**Branch**: `feature/020-building-capability` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-building-capability/spec.md`; mechanics extract in `research.md`.

## Summary

Make rooms declarative. Packs carry **archetypes** — footprint, wall/door/floor defs, furnishing lists with placement rules, stat targets — and the runtime compiles an archetype + rect into `ui.build_many` ops and verifies the built room by observed role + stats. A **space-tier profile** (vanilla or Realistic Rooms Rewritten's six thresholds + filth toggle) resolves from live `defs.get` `scoreStages` data, so tier-gated sizing stays correct with or without the mod. Housing becomes a standing goal driven by bed demand; support rooms (dining/hospital/kitchen/workshop) trigger off observed need signals.

## Technical Context

**Language/Version**: Python 3.13 runtime; YAML packs (schema v1); no bridge changes for v1 (space/wealth estimation client-side; `room.stat` RPC is optional follow-up)

**Primary Dependencies**: `policy.py` fns (`enclosed_at`, `find_defs_in`, `rect`/`cell` math), `templates.py`/`pack.schema.json` v1 surface, `phase.py` standing-goal machinery, bridge `ui.build_many`/`ui.designate`/`state.rooms`/`map.cell`/`defs.get`

**Storage**: pack files; anchors in `runstate.json` vars; no new stores

**Testing**: pytest (`components/runtime/tests/`); SimGame with scripted room fixtures; pack-validation tests

**Target Platform**: Windows dev loop; live via RimBridge :8765; sim via `SimGame`

**Project Type**: runtime capability extension + pack content — no new components

**Performance Goals**: layout compile ≤ trivial per goal; `state.rooms` poll cost unchanged (already observed)

**Constraints**: verifier-only success (role + stats, never blueprint placement); mod detection reads live def data, vanilla profile is the fail-safe; ≤36-region room bound enforced at compile

**Scale/Scope**: one layout compiler fn (`plan_room`), ~8 fns/selectors, `rooms:`/`mods:` cfg blocks, archetype catalog in pack data, contract + quickstart

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| I. Deterministic before probabilistic | ✅ | Archetype→ops compile is deterministic; verification is observed-state predicates |
| II. One writer, bounded authority | ✅ | All placements via `ui.build_many`/`ui.designate` through dispatcher |
| III. Spec-first | ✅ | research → spec → plan → contract → tasks; FR-2000s stable IDs |
| IV. Explicit compatibility | ✅ | Mod profile is explicit cfg + live-detection; vanilla is the fail-safe; additive pack-schema extension |
| V. Evidence immutable | ✅ | Build/verify outcomes ride existing action/decision records |
| VII. Build for diagnosis | ✅ | Effect predicates record which stat failed; `blueprints_in`/`enclosed_at` distinguish build-wait vs. never-finished |
| IX. Policy is data | ✅ | Sizes, furniture, targets, tier tables, trigger conditions — all pack cfg/archetypes; runtime ships compiler + stat fns only |
| X. Brain lifecycle | ✅ | Archetypes migrate with pack; no runtime-persisted room state beyond existing anchors/vars |

**Verdict**: PASS — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/020-building-capability/
├── spec.md                  # FR-2001..2009, SC-2001..2006
├── plan.md                  # this file
├── research.md              # room-stat math, roles, archetypes, RR-Rewritten profile
├── data-model.md            # archetype, tier profile, room observation, furnishing rule
├── contracts/
│   └── room-archetypes.md   # archetype schema + rooms:/mods: cfg + fn signatures
└── quickstart.md            # sim validation scenarios
```

### Source Code (repository root)

```text
components/runtime/src/runtime/
├── policy.py               # + space_score, space_tier/target, room_at, room_stat,
│                           #   bed_demand, pawns_with_thought, plan_room compiler
└── (no other runtime changes — phase/select machinery reused)

components/rimbrain/
├── capability-catalog.yaml    # + new fn/template entries
└── packs/start-mode-v0/pack.yaml  # rooms: cfg + archetypes replace hardcoded
                                   #   shelter/expansion geometry (7x7 → archetype)

components/contracts/schemas/runtime/
└── pack.schema.json        # + `rooms:`/`mods:` blocks + archetype object schema
```

**Structure Decision**: single-package extension; archetype catalog lives in pack data (folder-per-pack). No new component, no bridge change in v1.

## Complexity Tracking

No constitution violations — section intentionally empty.
