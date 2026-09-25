# Quickstart: Unified Phase Engine validation

**Feature**: 017 | **Prereq**: feature 016 landed; `components/runtime` venv; PYTHONPATH=`components/runtime/src;components/contracts/src`

## 1. Sim end-to-end (deterministic)

```powershell
cd components/runtime
uv run python -m runtime loop --pack start-mode-v0 --mode run --iterations 60
```

Expected: init phase completes its contract → standing goals engage → `state/planning.json` shows current phase, action list, active plan. Event stream identical on repeat runs. Zero endpoint calls (assert in tests).

## 2. Action-list bound + validation (unit)

```powershell
uv run pytest tests/test_select.py -q
```

Covers: >20 eligibles truncate to 20 by priority; pick ∉ offered → fallback + `select.invalid`; endpoint down → fallback + `select.degraded`; pawn questions batched in one request; shadow mode logs pick but executes fallback.

## 3. v0→v1 pack migration (unit)

```powershell
uv run pytest tests/test_pack_migration.py -q
```

`start-mode-v0` file (v0 shape) loads into normalized v1 doc; `@cfg:start.*`/`@cfg:govern.*` aliases resolve; `emergency` rules fire in `policy.check` dialect; normalized hash stable.

## 4. Planner cadence (sim clock)

Sim run with `decide.plan.cadence_s: 150`: plan request fires at cadence; stubbed accepted plan reorders next action-list priorities; stubbed failure leaves prior plan in force; no blocked polls during outage.

## 5. Reflect round-trip on phases

Trigger a reflection pass proposing `set phases.init.steps.5.params.rect ...` → gate validates → candidate written → next-run boundary installs → init executes mutated step. Regression path reverts via lineage.

## 6. Live smoke (bridge :8765 up, RimWorld running)

```powershell
python rimbrain.py run   # --mode run default, --live-mutate per 016
```

Expected: `state/decisions.jsonl` grows with `{offered, pick, applied}` rows; `planning.json` shows phase/action list/plan; init completes; standing goals hold; first planner round within ~150s; shadow→trial→authority per `decide.select` config.
