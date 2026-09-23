# Implementation Plan: Canonical Event and State Stores

**Branch**: `006-event-state-stores` | **Spec**: `specs/006-event-state-stores/spec.md`

## Summary

Durable evidence spine: `EventStore` (append-only canonical JSONL with torn-tail recovery + recovery markers), `write_atomic` snapshots (tmp + `os.replace`), deterministic `project()` fold, and sink wiring so dispatcher/planloop events persist under `state/`.

## Technical Context

- Envelope shape already emitted by `Dispatcher._emit` and `planloop._Emitter` — sink callables accept `dict`; the store's `append` is a drop-in sink.
- `DEFAULT_STATE_DIR`/`RIMBRAIN_STATE_DIR` convention exists in `dispatch.py`.
- `contracts.canonical_bytes` gives canonical serialization per line.
- Windows: `os.replace` is atomic on same volume; no symlinks.

## Constitution Check — PASS

Flat-file canonical records authoritative; projection disposable. Runtime owns the store; lab consumes read-only later.

## Structure

```
components/runtime/src/runtime/store.py      EventStore + write_atomic + recovery
components/runtime/src/runtime/project.py    project() fold + rebuild()
components/runtime/tests/test_store.py       torn-tail, atomicity, round-trip, gaps
components/runtime/tests/test_project.py     determinism, rebuild
loop.py / planloop.py                        --store/--no-store wiring (default on)
```

## Phases

1. `store.py` — EventStore append/load/recovery + write_atomic.
2. `project.py` — deterministic fold + atomic rebuild.
3. Wiring — store sink for `runtime loop` and `runtime plan` (default on, `--no-store` opt-out).
4. Tests + polish (INDEX, README, AGENTS).

## Decisions

- **Canonical bytes per line**: `canonical_bytes(envelope)` + `\n` — log lines are the same canonical form used for hashing; replay is byte-stable.
- **Tail-only truncation**: recovery only ever removes bytes after the last newline; mid-file corruption is counted and skipped on load, never rewritten (append-only integrity).
- **Recovery is an event**: `recovery.jsonl` lines `{ts?, salvaged_bytes, reason}` — clock injectable for deterministic tests.
- **Projection is pure data**: `project(events)` is a pure function; `rebuild` reads the log and `write_atomic`s the result — no hidden state.
