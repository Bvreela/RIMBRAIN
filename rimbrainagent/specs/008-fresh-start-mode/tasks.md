# Tasks: Fresh-Start Mode (008)

**Inputs**: `spec.md`, `plan.md` | **Feature**: `specs/008-fresh-start-mode`

## Phase 1: Contracts + Pack

- [x] T124 `task.transition`-style `start.completed` payload schema + event-map entry + corpus (valid + 2 invalid) (FR-707)
- [x] T125 `components/rimbrain/packs/start-mode-v0.yaml`: bootstrap templates (`site-select` internal step + `zone-create`, `unforbid-all`, `build-shelter`, `haul-all`, `build-beds`, `food-source`, `build-recreation`), site-ranking weights, exit-condition defs (shelter/bed/food/recreation per colonist), all methods cross-checked against sealed inventory (FR-701/702/705)

## Phase 2: Runtime

- [x] T126 `components/runtime/src/runtime/startmode.py`: deterministic site ranking over `map.open_rects` (pack weights; nearest-to-items/home; `anchor.set` the choice); bootstrap graph builder emitting ledger tasks with effect specs; exit-condition evaluator per colonist; established-colony skip (effect already holds -> succeeded, zero writes); `start.completed` emission + mode disengage (FR-702..706, 709)
- [x] T127 `loop.py`/`__main__.py`: `--mode start` wiring — start-mode graph drives polls (observe -> reconcile -> reflex -> start-phase -> verify), emergencies keep precedence (FR-706/708)

## Phase 3: Tests + Polish

- [x] T128 [P] `tests/test_startmode.py` + scripted `StartSim` stub (fresh-map rpc surface): full ordered trace to `start.completed` (SC-701), forced-restart resume (SC-702), established colony zero-designation skip (SC-703), partial coverage keeps mode active (SC-704), pack-edit behavior change (SC-705)
- [x] T129 Polish: INDEX row 008, runtime README start-mode section, AGENTS.md phase note, validate_components
