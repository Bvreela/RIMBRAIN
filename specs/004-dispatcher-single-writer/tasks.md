# Tasks: Dispatcher (Single Writer) + Core-Survival Pack v0 (feature 004)

IDs continue from the global maximum across features (feature 002 ended at T076), so feature 004 starts at T077. Feature 003's Phase 4 convergence tasks (T056 speed/pause restore, T057 GameCtl.pause) stay in `specs/003-checkpoint-retry/tasks.md` and are implemented inline in this pass before feature 004 work.

## Phase 0: 003 convergence (inline)

- [x] T056 Capture pre-run `game.status` (speed/pause) at loop start and restore on every exit path (early_exit, exhausted, aborted, bridge error) per spec edge cases + US1/AC1 (missing)
- [x] T057 Add `GameCtl.pause()` (LiveBridge -> `game.pause`, SimBridge -> paused state) per FR-201 and the bridge inventory (partial)

## Phase 1: Contracts

- [x] T077 [P] Create `components/contracts/schemas/runtime/pack.schema.json` — PolicyPack contract: schema_version, pack_id, revision, templates[{id, method, params_schema, require, description}], jobs[], decision_map[{question, choice|score|noul, action:{template_id, params}}], emergency[{id, condition, priority, action}] per FR-302/FR-305/FR-308
- [x] T078 [P] Create `schemas/events/types/action.*.schema.json` for the five FR-307 event kinds (issued, completed, failed, refused, emergency) carrying {pack_revision, decision_id?, template_id, params, outcome}; register as native types in `registry/event-map.yaml` (feature 001 pattern)
- [x] T079 [P] Corpus cases: valid pack + invalid packs (unknown template method, missing require param, decision without action), valid/invalid action.* event payloads; add to contracts corpus + drift suite

## Phase 2: Pack + templates

- [x] T080 Create `components/rimbrain/packs/core-survival-v0.yaml` — v0 data: 5 templates (prioritize-work, forbid-item, unforbid-item, rescue, firefight), jobs (food, emergency), decision_map (forbid/haul/rescue/firefight/none), emergency rules (downed → rescue, fire → firefight)
- [x] T081 Implement `runtime/templates.py`: pack load + schema validation, template.method cross-check against `baselines/upstream-85cb050/rpc-inventory.json` (reject pack on unknown method), canonical-JSON pack hash (contracts.canonical), drift check (loaded hash vs current file hash)

## Phase 3: Dispatcher core

- [x] T082 Implement `runtime/dispatch.py`: single writer `dispatch(action_id, params, decision_id=None)` — template lookup, params validation, in-process + file lock (dispatch.locked), RPC via bridgeclient, evidence events (issued/completed/failed/refused); pack-drift guard refuses with dispatch.pack_drift
- [x] T083 Implement `runtime/bridgeclient.py`: thin HTTP RPC client (POST /rpc {method, params} -> {ok, result|error}) with structured errors and timeout; surface subset used by v0 templates

## Phase 4: Reflex + decisions

- [x] T084 Implement `runtime/reflex.py`: deterministic emergency rules (state predicate evaluator over status dict, priority order) — returns matched action list with zero model calls per FR-308
- [x] T085 Implement decision pipeline: systemone answer (choice/score/noul) → decision_map lookup → dispatch; unmapped → action.refused dispatch.decision_unmapped per FR-303/FR-304

## Phase 5: Loop + SimGame

- [x] T086 Implement `runtime/simgame.py`: deterministic in-memory game stub (status/prioritize-work/forbid/unforbid/rescue/firefight subset) with seeded evolution so 5 runs are bit-identical
- [x] T087 Implement `runtime/loop.py`: poll loop — status → reflex (before model) → select (systemone via runtime client) → dispatch; CLI `python -m runtime loop --mode sim|live [--bridge URL] [--pack core-survival-v0] [--iterations N]`; live mode is operator-only (default refused without --live)

## Phase 6: Tests + polish

- [x] T088 [P] Tests `test_templates.py` + `test_dispatch.py`: pack validation, inventory cross-check rejection, hash stability/drift, fail-closed matrix (unknown action, invalid params, unmapped decision, lock conflict, pack drift) — zero bridge calls on every refusal (SC-302)
- [x] T089 [P] Tests `test_reflex.py` + `test_loop.py`: emergency fires with zero client calls (SC-305), event-stream ≡ write-stream audit (SC-301), five consecutive sim runs bit-identical (SC-303), pack immutability across loads (SC-304)
- [x] T090 Polish: runtime README notes, specs INDEX rows (004 implemented artifacts), `state/` in .gitignore, validate_components unchanged (runtime validator already runs full suite); optional live smoke note (operator-only)
