# Plan: Dispatcher (Single Writer) + Core-Survival Pack v0

**Feature**: `004-dispatcher-single-writer` — builds the first real game-writing path: decisions → validated single-writer actions → canonical evidence, offline-verifiable.

## Architecture decisions

1. **Dispatcher lives in `components/runtime`** (`dispatch.py` + `bridgeclient.py` + `simgame.py` + `reflex.py` + `loop.py`). Runtime may depend on RimBridge/Steward protocols and contracts — it does not import lab or dashboard. Decision client is feature 002's `runtime/client.py` (systemone).
2. **Policy pack is validated data in `components/rimbrain`** (`packs/core-survival-v0.yaml` + pack schema in contracts). RimBrain depends only on contracts/schemas. Pack revision = canonical-JSON hash (feature 001 `contracts.canonical`), stable across loads, byte-sensitive.
3. **Templates are cross-checked against the sealed inventory** (`baselines/upstream-85cb050/rpc-inventory.json`) at pack load: template `method` must be in the inventory or the pack is rejected.
4. **Single-writer lock**: in-process threading lock + advisory file lock under a runtime state dir (`RIMBRAIN_STATE_DIR`, default gitignored `state/`). Second dispatcher gets `dispatch.locked`.
5. **Pack drift guard**: dispatch holds the loaded pack's hash; each dispatch re-hashes the file on disk — mismatch → `dispatch.pack_drift` refusal (constitution: scored runs reject dirty state).
6. **Emergency reflex precedes model decisions** in the poll loop (constitution MUST: emergencies never wait for a model). Reflex rules are pack data (state predicates, same evaluator style as feature 003 gate).
7. **Evidence**: five `action.*` event kinds registered as native types in `registry/event-map.yaml` (feature 001 pattern): `action.issued`, `action.completed`, `action.failed`, `action.refused`, `action.emergency`; payload schemas under `schemas/events/types/action.*`.
8. **Offline determinism**: `simgame.py` implements the exact RPC surface the v0 templates use (subset of inventory) as a deterministic state machine; the loop is a pure function of (state, pack, decisions). CI runs sim mode only; `--mode live` is operator smoke (003 T055 pattern).
9. **v0 survival jobs**: prioritize work (`prioritize-work`), forbid/unforbid (`forbid-item`/`unforbid-item`), rescue (`rescue`), firefight (`firefight`), haul (`haul`); decision-map maps select answers (`forbid`/`haul`/`rescue`/`firefight`/`none`) to templates. Emergency rules: downed colonist → rescue; fire → firefight.

## Files

| Path | Content |
|---|---|
| `components/contracts/schemas/runtime/pack.schema.json` | PolicyPack contract (templates/jobs/decision_map/emergency) |
| `components/contracts/schemas/events/types/action.*.schema.json` | 5 event payload schemas |
| `components/contracts/registry/event-map.yaml` | register `action.*` native types |
| `components/rimbrain/packs/core-survival-v0.yaml` | v0 pack data (templates, jobs, decision_map, emergency) |
| `components/runtime/src/runtime/bridgeclient.py` | thin HTTP RPC client (subset surface, structured errors) |
| `components/runtime/src/runtime/simgame.py` | deterministic in-memory game stub (same RPC subset) |
| `components/runtime/src/runtime/templates.py` | pack load + inventory cross-check + canonical hash + drift check |
| `components/runtime/src/runtime/dispatch.py` | single writer: validate → lock → RPC → evidence events |
| `components/runtime/src/runtime/reflex.py` | deterministic emergency rules (no model) |
| `components/runtime/src/runtime/loop.py` | poll loop: status → reflex → select (systemone) → dispatch; CLI `python -m runtime loop` |
| `components/runtime/tests/test_dispatch.py`, `test_reflex.py`, `test_loop.py`, `test_templates.py` | offline suites (stub HTTP + SimGame) |
| `specs/004-dispatcher-single-writer/tasks.md`, docs/INDEX update | traceability |

## Phases

1. **Contracts**: pack + action.* schemas, event-map registration, corpus cases (valid/invalid).
2. **Pack + templates**: `core-survival-v0.yaml`, loader with inventory cross-check + canonical hash + drift guard.
3. **Dispatcher**: single-writer core, lock, fail-closed envelopes, evidence events (issued/completed/failed/refused).
4. **Reflex + decisions**: emergency rules (no-model), systemone decision-map pipeline.
5. **Loop + SimGame**: deterministic poll loop, CLI, 5× bit-identical run test.
6. **Polish**: READMEs, INDEX rows, validate integration, live smoke opt-in note.

## Constraints

- No new component dependencies; runtime stays independent of lab/dashboard.
- All failures use the common/error envelope; all writes emit canonical events.
- Live mode is operator-only; CI is offline.
