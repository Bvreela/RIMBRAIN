# rimbrainagent-runtime

Future `rimbrainagent-runtime` submodule — one dispatcher, models emit typed proposals. Build specification: [Runtime](../../specs/20-submodules/RUNTIME.md).

Current contents: the **model endpoint registry layer** (feature 002, `specs/002-model-endpoints`): named endpoints + per-role bindings over `profiles/*.yaml` (authoritative, hand-editable).

```powershell
$env:PYTHONPATH = "components/runtime/src;components/contracts/src"
uv run --with pyyaml,jsonschema python -m runtime list
uv run --with pyyaml,jsonschema python -m runtime probe local-laya
uv run --with pyyaml,jsonschema python -m runtime discover
uv run --with pyyaml,jsonschema python -m runtime resolve rimbrain.select --live
uv run --with pyyaml,jsonschema python -m runtime bind rimbrain.plan openrouter nvidia/nemotron-3-ultra-550b-a55b:free
```

Modules: `registry.py` (load/validate/CRUD — schema-checked, fail-closed on unknown endpoint refs), `secrets.py` (`env:`/`config:` key refs, call-time only), `probe.py` (TCP → models/decide → capabilities; transient vs hard classification), `discover.py` (local port scan), `bindings.py` (role resolution + capability gates + ordered degraded paths), `client.py` (openai-compat chat/embeddings honoring `strict`, systemone decisions), `provenance.py` (per-role episode manifest).

Secrets are `api_key_ref` refs only — never inline, logged, or serialized.


## Dispatcher loop (feature 004)

```powershell
$env:PYTHONPATH = "components/runtime/src;components/contracts/src"
uv run --with pyyaml,jsonschema python -m runtime loop --mode sim --iterations 5
```

Sim mode is deterministic (SimGame, fixed clock) � five runs are bit-identical. The dispatcher is the single writer: templates come from `components/rimbrain/packs/core-survival-v0.yaml`, every method is cross-checked against the sealed bridge inventory, and pack edits mid-run refuse with `dispatch.pack_drift`. Live mode (`--mode live --live`) is operator smoke only. NOTE: never point a sim run at the real bridge � the dispatcher's writer target is the SimGame in sim mode.

## Planner/review loop (feature 005)

```powershell
$env:PYTHONPATH = "components/runtime/src;components/contracts/src"
uv run --with pyyaml,jsonschema python -m runtime plan --mode sim --iterations 1
```

One round: state -> `rimbrain.plan` proposal (schema-validated JSON) -> deterministic review gate + optional `rimbrain.review` critique -> accepted plans dispatch `actions[]` through the single writer and materialize `policy_mutations[]` as candidate packs under `components/rimbrain/packs/candidates/`. The gate is code � a model cannot approve a violating plan. `rimbrain.plan` resolving to `rules-only` emits the pack's `fallback_plan` (degraded provenance). Sim mode uses a canned planner + SimGame; live needs `--live-flag`.

## Event/state stores (feature 006)

`store.py`: `EventStore` appends every emitted canonical envelope to `state/events.jsonl` (one canonical-JSON line each). Opening a log salvages a torn final line and records it in `recovery.jsonl`; `load()` replays in order with `corrupt_lines`/`sequence_gaps` counts. `write_atomic()` = tmp + `os.replace`. `project.py`: `rebuild(store)` folds the log into `state/projection.json` (counts, last action/plan, span). `loop`/`plan` persist by default; `--no-store` opts out. `RIMBRAIN_STATE_DIR` overrides the root.

## Task ledger (feature 007)

`tasks.py`: `TaskLedger` manages work through a declared lifecycle (`proposed -> locked -> dispatched -> verifying -> succeeded | failed | expired`, `requeued` loops to `proposed`). Only `verify()` can mark `succeeded`, and only when the task's `{field, op, value}` effect spec holds against observed state — dispatch `ok` is never proof. `acquire()` takes all declared `resources` or none; leases expire by game tick. Every transition appends a `task.transition` envelope to `state/tasks.jsonl`; a fresh ledger folds the log to rebuild. `reconcile(observed, tick)` re-verifies open tasks past lease before retry (succeeded / requeued / failed) and stamps `cursor.json`. `run_loop(..., ledger=...)` reconciles before attend each poll.

## Start mode (feature 008)

`startmode.py` drives the fresh-start bootstrap as ledger tasks: `site -> zone -> unforbid -> shelter -> roof -> haul -> beds/food/recreation -> start.completed`. Every phase's effect is verified against observed state; an already-established colony skips with zero designations. Site choice is deterministic scoring of `map.open_rects` by pack-declared weights, persisted via `anchor.set` + `startmode.json` (restart-safe). Beds dispatch one build per poll until `beds >= colonists`. Engage via `python -m runtime loop --mode start --live` (live-gated — sims need the start rpc surface). `start.completed` emits only when `exit_eval` verifies shelter + per-colonist beds + food source + recreation.

## Self-improvement + thought feed (feature 009)

`improve.py` runs bounded improvement cycles over canonical evidence (`python -m runtime loop --mode improve` — read-only, no `--live` needed): diagnose pack-declared defect patterns → propose a rules-only candidate pack → audit gates (`audit.py`: code/policy/ux, each a canonical `audit.verdict`) → weighted-score metrics validation (`metrics.py`) → promote at episode boundary only, else reject/defer with reasons. `--feed` composes with any mode to narrate every emitted event into `state/feed.md` (deterministic templates; feed failure never fatal). Brain customization is documented in `components/rimbrain/CUSTOMIZE.md`.
