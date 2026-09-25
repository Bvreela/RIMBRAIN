# Quickstart: Building / Room Capability validation

Prereqs: repo root `rimbrainagent/`; `PYTHONPATH=components/runtime/src;components/contracts/src`; `uv` available.

## 1. Unit (fns + compiler)

```
cd components/runtime && uv run pytest tests/test_rooms.py -q
```

Expect: `space_score` formula vs fixture cells; `space_tier` vanilla vs modded profile; `plan_room` compiles every shipped archetype (link radii, door perimeter, unfit→null); `bed_demand` couples-aware.

## 2. Contract round-trip

```
uv run pytest tests/test_room_contract.py -q
```

Expect: `rooms:`/`mods:` blocks validate; archetype referencing an unknown def fails at load; `effect` predicates using room stats resolve.

## 3. Sim build-and-verify

```
python -m runtime loop --pack start-mode-v0 --mode run --game sim --iterations 300
```

Expect: init completes; expansion goals emit archetype-compiled ops (not hand cell-math); `state.rooms`-equivalent obs verifies role `Bedroom` + impressiveness ≥ target; re-run of a completed goal dispatches zero ops.

## 4. Right-sizing delta

Compare wall-material consumption of the archetype path vs the old 7×7 expansion path in the sim fixture — expect ≥30% less per colonist at equal mood band (SC-2002).

## 5. Mod profile matrix

Two fixture runs: live `scoreStages` = vanilla table vs RR-Rewritten defaults → a tier-targeted archetype sizes differently in each; both verify against the live table. Detection-failure fixture falls back to vanilla.

## 6. Live smoke (manual gate)

Bridge :8765 up; `--mode run --game live --live-brain --fair`. Confirm `defs.get(Space)` returns `scoreStages` live (the detection path); one bedroom archetype builds and verifies in-game.
