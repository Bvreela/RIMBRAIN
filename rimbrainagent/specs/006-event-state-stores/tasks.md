# Tasks: Canonical Event and State Stores (006)

**Inputs**: `spec.md`, `plan.md` | **Feature**: `specs/006-event-state-stores`

## Phase 1: Store

- [x] T111 Implement `components/runtime/src/runtime/store.py`: `EventStore(path)` â€” `append(envelope)` writes canonical_bytes+`\n` (O_APPEND), `open()` torn-tail recovery (truncate after last newline when final line is unparseable; record `{salvaged_bytes, reason}` to `recovery.jsonl`), `load()` -> `{events, corrupt_lines, sequence_gaps}`; `write_atomic(path, bytes)` via `<path>.tmp` + `os.replace`; all paths honor `RIMBRAIN_STATE_DIR` (FR-501..503, FR-506/507)

## Phase 2: Projection

- [x] T112 Implement `components/runtime/src/runtime/project.py`: `project(events)` -> `{counts_by_type, last_action, last_plan, first_seq, last_seq, total}` pure/deterministic; `rebuild(store)` reads log + `write_atomic`s `projection.json` (FR-504)

## Phase 3: Wiring

- [x] T113 Wire store sinks: `runtime loop` and `runtime plan` default to persisting emitted events via `EventStore` under `state/` (`--no-store` opt-out); dispatcher sink signature already fits (FR-505)

## Phase 4: Tests + polish

- [x] T114 [P] `tests/test_store.py`: append/load round-trip across reopen (SC-501), torn-tail salvage + recovery marker (SC-502), complete-unterminated tail preserved, mid-file corruption counted not rewritten, sequence-gap reporting, no `.tmp` leftovers (SC-503), `RIMBRAIN_STATE_DIR` isolation
- [x] T115 [P] `tests/test_project.py`: projection determinism + rebuild-from-log-only (SC-504); loop/pplan run persists events to disk (SC-505)
- [x] T116 Polish: INDEX row 006, runtime README store section, AGENTS.md phase note, validate_components

## Phase 5: Convergence

- [x] T117 Add `msvcrt.locking` byte-range lock around `EventStore.append` (graceful fallback on non-Windows) per spec edge case "concurrent append" (partial)
- [x] T118 Merge `state.summary`/`state.threats` into the observed state in `loop.py` via `planloop.observe()` so live-mode reflexes see real `downed`/fire fields (live `game.status` lacks them) per FR-308 live viability (partial)
