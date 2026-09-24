# Implementation Plan: Unified Phase Engine

**Branch**: `feature/017-unified-phase-engine` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-unified-phase-engine/spec.md`
**ADR**: `specs/90-decisions/ADR-019-unified-phase-engine.md`

## Summary

Collapse six parallel loops and three mutation pipelines into one six-stage pipeline — **observe → reflex → decide → act → verify → reflect** — driven entirely by pack-declared `phases`. The old start-mode bootstrap becomes the prescriptive `init` phase; standing goals run every poll; Laya (`rimbrain.select`) executes per-poll from a ≤20-item action list spanning colony and pawn scopes; the planner (`rimbrain.plan`) strategizes on a ~150s cadence + phase boundaries + major events; one reflect pipeline (016 `mutate` machinery + `improve` evidence + `planloop` promotion) mutates every pack surface through `packmut` ops with boundary-only promotion. Legacy pack namespaces migrate in memory at load (schema v0→v1). Live determinism is dropped in favor of logged decision records; sim/CI stays fully deterministic.

## Technical Context

**Language/Version**: Python 3.13 (runtime), YAML packs (schema v0→v1)

**Primary Dependencies**: existing `policy.py` capability substrate, `tasks.py` TaskLedger, `dispatch.py` single writer, `packmut.py` ops engine, `client.py` systemone/openai-compat clients, `registry`/`bindings` role resolution

**Storage**: flat-file canonical records (`state/*.jsonl`, `state/*.json`), pack files (`packs/<id>/pack.yaml`), `packs/candidates/`

**Testing**: pytest (`components/runtime/tests/`); sim via `SimGame` + test `StartSim`; contract-style tests per feature

**Target Platform**: Windows dev loop; `rimbrain.py` launcher / frozen `dist\rimbrain.exe`; RimWorld bridge loopback :8765

**Project Type**: single-package runtime refactor + pack schema migration

**Performance Goals**: select call ≤1 batched request/poll; plan cadence ~150s (pack-tunable); zero planner-blocking polls

**Constraints**: fair runs refuse dev.* + dev-class packs; selector authority staged per Constitution VI (shadow → trial → live); boundary-only pack mutation; ≤20 action-list cap

**Scale/Scope**: ~9k LOC runtime; deletes `startmode.py` engine internals, `universal.py`, `loop.py` decider, duplicate gate/promote code; adds `phase.py`, `select.py`, `observe.py`, `evolve.py`, `runstate.py`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| I. Deterministic before probabilistic | ✅ | Code decides legality/membership/fallbacks; models only pick among enumerated options (unresolved tradeoffs) |
| II. One writer, bounded authority | ✅ | Selector picks offered option IDs only; planner emits proposals through review gate; all writes via dispatcher |
| III. Spec-first | ✅ | ADR-019 + spec + plan + tasks precede code; FR-1400s stable IDs |
| IV. Explicit compatibility | ✅ | Pack schema v1 declared; v0 packs migrate in memory at load; unknown newer schemas rejected |
| V. Evidence immutable; policy revisable | ✅ | decisions.jsonl append-only; boundary-only promotion; no self-promotion |
| VI. Staged qualification | ✅ | New action-list matrix starts shadow → bounded trial → live authority, per model/prompt/context |
| VII. Diagnosis | ✅ | Decision records carry offered set + inputs; degradation events on every fallback |
| VIII. Migration escape hatch | ✅ | Upstream untouched |
| IX. Policy is data | ✅ | Phases, priorities, action lists, cadences, fallbacks all pack-owned; runtime keeps primitives only |
| X. Residue-free lifecycle | ✅ | RunState consolidation + brain-reset reinit preserved; tombstones durable |

**No violations. No complexity justifications needed.**

## Project Structure

### Documentation (this feature)

```text
specs/017-unified-phase-engine/
├── plan.md              # This file
├── research.md          # Phase 0 output — resolved decisions
├── data-model.md        # Phase 1 output — entities + transitions
├── quickstart.md        # Phase 1 output — validation scenarios
├── contracts/           # Phase 1 output
│   ├── select-batch.md      # action-list → systemone questions contract
│   ├── plan-output.md       # planner short-term plan contract
│   └── pack-schema-v1.md    # pack restructure + v0→v1 migration map
└── tasks.md             # /speckit-tasks output
```

### Source Code (repository root)

```text
components/runtime/src/runtime/
├── phase.py          # NEW: PhaseEngine — ordered pack phases, init=prescriptive
├── select.py         # NEW: action-list compiler (≤20) + batched systemone + validation/fallback
├── observe.py        # NEW: canonical per-poll observation (observe_start+enrich+vitals merged)
├── evolve.py         # NEW: unified reflect — mutate triggers/gate/boundary + improve evidence
├── planstage.py      # NEW: planner scheduler + digest + gate + in-force plan
├── runstate.py       # NEW: vars/rule-state/pass-state/vitals-state in one owned object
├── combatmode.py     # DELETED — raid scenarios pack-ified into dev-class pack (FR-1429)
├── startmode.py      # DELETED after PhaseEngine port (temp shim during migration)
├── loop.py           # run_loop + _live_decider DELETED; keeps CLI plumbing → engine
├── universal.py      # DELETED (subsumed by policy.run_rules + reflex dialect)
├── dispatch.py       # _condition/_op_holds DELETED — reflexes via policy.check
├── improve.py        # diagnose/score kept as evidence fns; propose/gate/promote → evolve.py
├── mutate.py         # machinery absorbed into evolve.py (016 lands first)
├── planloop.py       # run_plan becomes stage entry; promotion machinery → evolve.py
├── packmut.py        # path whitelist += phases/action_list/decide/reflexes/rules
├── policy.py         # unchanged substrate (+ any fns new packs need)
├── tasks.py          # unchanged ledger
└── __main__.py       # --mode run (+start alias), --stage plan|reflect, --game sim|live, flag contract

components/rimbrain/packs/
├── start-mode-v0/pack.yaml   # restructured to schema v1 (phases/init/standing_goals/decide/...)
└── capability-catalog.yaml   # new fns catalogued

components/runtime/tests/
├── test_phase.py       # ported from test_startmode.py
├── test_select.py      # action-list bound, batching, validation, fallback, shadow
├── test_evolve.py      # ported test_mutate.py + improve pipeline tests
└── test_observe.py     # canonical observation contract
```

**Structure Decision**: single-package refactor inside `components/runtime` — no new components, no dependency-direction changes. Deletions outnumber additions.

## Phase 0: Research

All decisions resolved during design discussion — see `research.md`. No NEEDS CLARIFICATION items remain.

## Phase 1: Design

Artifacts: `data-model.md`, `contracts/select-batch.md`, `contracts/plan-output.md`, `contracts/pack-schema-v1.md`, `quickstart.md`.

Key design invariants locked by the spec:

1. **Stage order is fixed** — observe → reflex → decide → act → verify → reflect. Reflexes (old `emergency`) never wait on a model; they run in the same predicate dialect as all rules, before decide.
2. **≤20 is a hard engine bound** — compiler truncates by pack priority; the bound itself is not pack-editable (it's a model-context contract).
3. **Last plan stands** — planner failure never stalls the loop; staleness is visible in views.
4. **Boundary-only mutation** — promoted candidates can change phases/decide config/action lists, effective next run; mid-run semantics never shift under the active hash.
5. **Shadow first** — the action-list select matrix logs model picks while executing fallback until promoted per qualification ladder.
6. **v0→v1 pack migration at load** — `start.phases`→`phases[0].steps`, `exit`→`phases[0].complete`, `govern.goals`→`standing_goals`, `universal.rules`→`rules`, `emergency`→`reflexes`. Old packs keep loading; v1 is the documented form.

## Complexity Tracking

> No constitution violations — table omitted.
