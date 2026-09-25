# Quickstart: Combat Capability validation

Prereqs: repo root `rimbrainagent/`; `PYTHONPATH=components/runtime/src;components/contracts/src`; `uv` available.

## 1. Unit (fn + compile correctness)

```
cd components/runtime && uv run pytest tests/test_combat_capability.py tests/test_select.py -q
```

Expect: engaged/watch classification fixtures, `draftable`/`rally_cell` distinctness, `outranges` sign, ≤20 bound at 15 pawns, fallback equals deterministic best.

## 2. Contract round-trip

```
uv run pytest tests/test_pack_combat_contract.py -q
```

Expect: a pack with `combat:` cfg + `pawn_scope` combat options loads/validates; `delegate_order` bogus id rejects at load; options compile to `pawn.<id>.<oid>` candidates.

## 3. Sim raid lifecycle

```
python -m runtime loop --pack combat-defense-v0 --mode run --game sim --iterations 200
```

Expect event stream: `combat.engaged` → fighters drafted → `combat.released` after the hostile-free window; **zero** dispatches targeting downed/fogged/friendly rows; stand-down restores areas.

## 4. Endpoint-down determinism (sim = no endpoint)

Sim run issues every combat write via `priority_head` fallback; repeated runs produce identical event streams (per US5 determinism contract).

## 5. Dev-harness raid (optional, --dev)

```
python -m runtime loop --pack dev-lab-v0 --mode cycle --dev --iterations 300
```

Expect: spawned hostiles repelled, colonist injuries ≤ baseline draft-all rule, cleanup (strip/rescue/heal) fires, checkpoint restored.

## 6. Live smoke (manual gate, not CI)

Bridge :8765 up; `--mode run --game live --live-brain --fair`. Watch `state/decisions.jsonl` for pawn-scope combat rows and `state/select_authority.json` rung transitions; confirm order skips touched pawns (order explain reports them).
