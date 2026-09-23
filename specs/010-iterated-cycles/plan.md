# Implementation Plan: Iterated Improvement Cycles

## Technical Context

Extends feature 008 (start mode) + 009 (improve) — same spine: observe → reconcile → reflex → attend → verify. All new writes are pack-declared templates dispatched through the single writer (FR-805). New event types: `combat.completed`, `cycle.completed`.

## Design

### 1. Contracts

- `combat.completed` schema: `{rounds, hostiles_spawned, hostiles_cleared, colonist_casualties, ticks, verdict}`.
- `cycle.completed` schema: `{iteration, phases: {start, combat, improve}, ticks}`.
- Register both in `event-map.yaml`; corpus valid+invalid each.

### 2. Pack (`start-mode-v0.yaml`)

- Templates: `save-game` (game.save), `load-game` (game.load), `spawn-incident` (dev.incident), `draft-pawn` (ui.draft), `attack-target` (ui.attack), `heal-pawn` (dev.heal), `add-bill` (ui.add_bill).
- Config sections:
  - `start.cooking`: `{station_defs: [CookingSpot, FueledStove, ElectricStove], recipe: CookMealSimple, meal_defs: [MealSimple, MealFine]}`
  - `start.exit.meals`: `{field: meals_present, op: eq, value: true}`
  - `combat`: `{save_name, incident_def: RaidEnemy, points: 150, rounds: 2, tick_budget: 12000}`
  - `cycle`: `{checkpoint: rimbrain-cycle, order: [start, combat, improve]}`

### 3. Runtime

- `startmode.py`: BASELINE += `cookstation`, `meals` — cookstation dispatches `build-one` (station) then `add-bill` once station exists (needs its thing id via `map.find`); meals verifies `map.find` meal defs ≥1. Exit eval adds `meals`.
- `combatmode.py` (new): `run_combat(dispatcher, game, ledger, cfg, ...)` — prereq check (`startmode.json.completed` or live eval), snapshot via `save-game` template, per round: `spawn-incident` → poll/draft/attack until hostiles cleared or budget → heal → emit `combat.completed`.
- `cycle.py` (new): `run_cycle(dispatcher, game, cfg, iterations)` — ensure checkpoint (save once) → per iter: `load-game` + poll-until-playing → `run_start` → `run_combat` → `run_improve` → `cycle.completed`.
- `loop.py`/`__main__.py`: `--mode combat`, `--mode cycle` (live-only).

### 4. Tests

- Extend `StartSim`: cooking stations, bills, meals, `dev.*`/`game.save`/`game.load`/`ui.draft`/`ui.attack` stubs with hostile model.
- `test_combat.py`: prereq refusal, happy path (spawn→defend→clear→heal→completed), timeout → failed + restore.
- `test_cycle.py`: checkpoint created once, reload per iter, ordering start→combat→improve, crash-resume.
- Start-mode sim gains cooking → existing tests updated (exit now needs meals).

## Phases

1. Contracts (schemas + event-map + corpus)
2. Pack (templates + cooking/combat/cycle config)
3. `startmode.py` cooking phases + exit
4. `combatmode.py`
5. `cycle.py` + CLI
6. Tests + sims
7. Live cycle run + validation + docs

## Risks

- `game.load` mid-poll: poll `game.status` until `state=playing` before any RPC writes.
- Meal production depends on raw food availability — verifier waits; improve diagnoses stalls.
- `dev.incident` marks game assisted — cycle mode is test-only, never scored.
