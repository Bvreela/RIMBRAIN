# Implementation Plan: Combat Capability

**Branch**: `feature/019-combat-capability` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-combat-capability/spec.md`; mechanics extract in `research.md`.

**ADR dependency**: combat-writer authority split (delegate model — spec resolution) should be recorded as an ADR before code lands, per AGENTS "architectural changes require an ADR before code changes". The standing order ↔ pack interaction contract lives in `contracts/combat-capability.md`.

## Summary

Ship combat as pack data on the landed decide-stage machinery. The Steward `combat` standing order remains the base executor (draft → rally → hold → overrun → release); the pack steers it through `steward.orders.*` (rally rect, enable/disable, force-run) and exposes order state into observation. On top, `decide.select.pawn_scope` compiles per-pawn combat options — gated by skills/gear/enemy composition, priority-scored so `priority_head` fallback equals the best deterministic assignment — which dispatch as surgical overrides the order honors via manual-touch windows. Fair-class only; the dev harness (`dev-lab-v0` spawn/heal) is unchanged test tooling.

## Technical Context

**Language/Version**: Python 3.13 runtime; YAML packs (schema v1); no C# bridge changes for v1 (LOS/cover RPC deferred; a `[bridge-gap]` on order-state/touch surfaces degrades the dependent options fail-closed and becomes a follow-up spec — never in-feature scope growth)

**Primary Dependencies**: `policy.py` fn/selector registry, `select.py` `compile_actions`/`pawn_scope`, `phase.py` PhaseEngine standing-goal drive, `dispatch.py` single writer, `tasks.py` TaskLedger, bridge `steward.orders.*`/`ui.*`/`state.threats`/`state.pawn`/`map.*`/`defs.get` surface

**Storage**: pack files (`packs/<id>/pack.yaml`); `state/select_authority.json`, `state/decisions.jsonl`, canonical event log — no new stores

**Testing**: pytest (`components/runtime/tests/`); `test_combat.py` harness conventions; SimGame scripted raids; stubbed select callers per `test_select.py`

**Target Platform**: Windows dev loop; live via RimBridge :8765; sim via `SimGame`

**Project Type**: runtime capability extension + pack content — no new components

**Performance Goals**: one batched select call/poll; combat option compile ≤ few ms; ≤20 hard bound respected via gate pruning

**Constraints**: fair-class packs only (no `dev.*`); manual-touch interlock respected; decision records per decide-stage contract; order-state is read-only observation

**Scale/Scope**: ~15 new policy fns/selectors, ~12 new catalog templates, one combat cfg block + pawn-option vocabulary, one combat pack (`packs/combat-defense-v0` or into `start-mode-v0` rules), contract + pack-schema delta

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| I. Deterministic before probabilistic | ✅ | Eligibility gates + priority scores are deterministic; model picks among offered options; fallback = deterministic best |
| II. One writer, bounded authority | ✅ | All game writes via dispatcher templates; selector picks member IDs only; order delegation via `steward.orders.*` RPCs through the writer |
| III. Spec-first | ✅ | research → spec → plan → contracts → tasks; FR-1900s stable IDs; ADR for authority split precedes code |
| IV. Explicit compatibility | ✅ | Pack-schema v1 extension documented in contract; dev harness untouched; `state.threats`/`steward.orders.*` are sealed-inventory methods |
| V. Evidence immutable | ✅ | Decision records + engagement lifecycle events append to existing stores |
| VI. Staged promotion | ✅ | Combat picks ride the existing shadow→trial→authority registry; no special-casing |
| VII. Build for diagnosis | ✅ | `combat_engaged`/`overrun`/`released` events + per-pawn offered/pick rows |
| IX. Policy is data | ✅ | Modes, radii, duties, hysteresis, fitness weights, option vocabulary — all pack cfg/rules; runtime adds generic fns/templates only |
| X. Brain lifecycle | ✅ | Combat surface migrates with pack swap; no persisted brain-side combat state beyond existing rule_state |

**Verdict**: PASS — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/019-combat-capability/
├── spec.md               # FR-1901..1910, SC-1901..1906
├── plan.md               # this file
├── research.md           # mechanics + capability inventory (pre-existing; Decisions appended)
├── data-model.md         # combat mode machine, threat row, eligibility, option, rally
├── contracts/
│   └── combat-capability.md   # pack cfg + option vocabulary + fns + order-delegation surface
└── quickstart.md         # sim/dev-harness validation scenarios
```

### Source Code (repository root)

```text
components/runtime/src/runtime/
├── policy.py             # + combat fns/selectors (engaged_hostiles, draftable,
│                         #   rally_cell, weapon_stats, outranges, combat_mode, …)
├── select.py             # unchanged — pawn_scope machinery already lands options
└── observe.py            # + steward order-state projection into obs (orders.*)

components/rimbrain/
├── capability-catalog.yaml   # + combat template/fn/selector entries (gap→implemented)
└── packs/
    ├── dev-lab-v0/pack.yaml      # combat harness stays dev-class (unchanged)
    └── combat-defense-v0/pack.yaml  # NEW fair-class defense pack (cfg + rules + pawn options)

components/contracts/schemas/runtime/
└── pack.schema.json      # + `combat:` cfg block (pawn_scope rides the permissive v1 `decide` block)
```

**Structure Decision**: single-package extension; pack content is folder-per-pack per existing convention. No new component, no bridge change in v1.

## Complexity Tracking

No constitution violations — section intentionally empty.
