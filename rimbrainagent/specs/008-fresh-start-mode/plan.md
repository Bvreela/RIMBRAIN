# Implementation Plan: Fresh-Start Mode (Start Mode)

**Branch**: `008-fresh-start-mode` | **Spec**: `specs/008-fresh-start-mode/spec.md`

## Summary

`runtime/startmode.py` — deterministic bootstrap graph over the feature-007 ledger: site-select → storage zone → unforbid → shelter blueprints → haul → condition loop until exit. Driven by a new `start-mode-v0` pack (reviewable data: templates, ranking weights, exit-condition defs). Engages via `--mode start` / pack binding only; verifies every phase against observed state; disengages with a `start.completed` event.

## Technical Context

- Bridge surface (verified in inventory): `map.open_rects`, `ui.zone`, `ui.build`/`build_many` (dry_run), `ui.designate` (unforbid/haul/roof-by-classname), `anchor.set`, `map.find` (items/blueprints/beds, `forbidden` filter), `state.base`/`state.rooms`/`state.stocks`/`state.storage`, `defs.buildable`.
- `TaskLedger` gives phase tasks + locks + reconcile; `enrich()`/`observe()` give normalized live state; Dispatcher is the only writer.
- SimGame cannot model zones/buildings — tests use a scripted `StartSim` stub implementing the needed rpc surface (like `_LiveShapedGame`).

## Constitution Check — PASS

Single writer; deterministic bootstrap; opt-in pack data; fail-closed; canonical evidence.

## Structure

```
components/rimbrain/packs/start-mode-v0.yaml       policy data: templates, weights, exit conditions
components/runtime/src/runtime/startmode.py        site rank, bootstrap graph, exit evaluator
components/runtime/src/runtime/loop.py (or own CLI) --mode start wiring
contracts: start.phase/start.completed event types (or reuse task.transition only)
components/runtime/tests/test_startmode.py         graph/exit/skip-on-established/restart tests
```

## Decisions

- **Deterministic site scoring** in code with weights from the pack — a model never places structures.
- **Bootstrap phases are ledger tasks** — restart-safe, verifier-gated; each phase's effect spec checks real observation (e.g. zone → `state.storage`, unforbid → `map.find forbidden=0`, shelter → `map.find kind=building`, stocked → `state.stocks` delta).
- **Roof via classname designator** (`Designator_Roof` probe; fallback: walls+roof-support ordering) — probed live, not assumed.
- **Opt-in only**: `--mode start` CLI mode (parallel to sim/live), or `--pack start-mode-v0`; no auto-detection.
- **Established-colony skip**: each phase's effect check runs BEFORE dispatch — already-satisfied phases mark succeeded with zero writes (SC-703).
- **Event granularity**: reuse `task.transition` for the graph; add ONE `start.completed` event type for mode exit (completion is a distinct contract-worthy event).

## Phases

1. Probe + contracts: roof designator check; `start.completed` schema + corpus; `start-mode-v0` pack skeleton.
2. `startmode.py`: site ranking, bootstrap graph builder, exit-condition evaluator.
3. Wiring: `--mode start` in loop CLI; enrich() additions needed (alerts already merged? storage/rooms calls).
4. Tests (scripted StartSim stub: fresh map, established colony, mid-graph restart, partial-exit) + polish.
