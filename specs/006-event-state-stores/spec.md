# Feature Specification: Canonical Event and State Stores

**Feature Branch**: `006-event-state-stores`

**Created**: 2026-09-23

**Status**: Draft

**Input**: WP-101 (UR-RUN-004, UR-DAT-001..003/007) — durable JSONL event log, atomic snapshots, migrations, recovery markers, bus projection. The dispatcher and plan loop currently emit canonical envelopes to in-memory sinks only; nothing survives a process exit.

## Purpose

Give the runtime a durable, crash-safe evidence spine: an append-only canonical JSONL event log, atomic snapshot writes, torn-tail recovery, and a deterministic bus projection that folds events into a replayable state view. Flat-file canonical records are authoritative; the projection is disposable.

## User Stories *(mandatory)*

### User Story 1 - Durable Append-Only Event Log (Priority: P1)

Every emitted canonical event (action.*, plan.*, retry.*) can be appended to `state/events.jsonl` — one canonical-JSON envelope per line. The store survives process exit and reload replays every event in sequence order.

**Why this priority**: evidence is the product; in-memory sinks lose everything on exit.

**Independent Test**: emit events through a dispatcher wired to the store, restart (new store instance), `load()` returns all envelopes in order.

**Acceptance Scenarios**:

1. **Given** a dispatcher with a store sink, **When** actions dispatch, **Then** `events.jsonl` gains one canonical JSON line per event and a fresh store loads them all.
2. **Given** an existing log, **When** a new store opens it, **Then** appends continue without rewriting prior bytes.

### User Story 2 - Torn-Tail Recovery (Priority: P1)

A crash mid-write leaves a truncated final line. On open, the store detects a partial tail (no trailing newline / unparseable last line), truncates it, marks a recovery record, and resumes clean appends — never silently parsing garbage.

**Why this priority**: UR-DAT integrity — a torn tail must not corrupt the log or crash the store.

**Independent Test**: write valid lines + a partial line; reopen; partial line is gone, valid lines intact, `state/recovery.jsonl` records the salvage.

**Acceptance Scenarios**:

1. **Given** a log ending in a truncated JSON line, **When** the store opens, **Then** the tail is truncated to the last complete line and a recovery marker is written.
2. **Given** a log whose final line is complete but unterminated, **When** opened, **Then** it is preserved (a missing newline is not corruption).

### User Story 3 - Atomic Snapshots (Priority: P2)

State snapshots (e.g., projection, run manifests) write via temp-file + `os.replace` — readers never see a partial file; Windows-safe (no symlinks).

**Why this priority**: snapshots must be all-or-nothing under crash (UR-DAT-002).

**Independent Test**: `write_atomic` produces the target file with no leftover temp files; a crash simulation (kill between write and rename) leaves either old or new, never partial.

### User Story 4 - Bus Projection (Priority: P2)

A deterministic fold replays `events.jsonl` into `state/projection.json`: counts per event_type, last action outcome, last plan verdict, event span (first/last sequence). Rebuilt from scratch on demand; a disposable index, never authoritative.

**Why this priority**: replay/debugging needs a cheap "where are we" view without scanning raw lines.

**Independent Test**: two projections over the same log are byte-identical; adding events then re-projecting reflects them.

### User Story 5 - Wiring (Priority: P3)

`loop`/`plan` CLIs and the dispatcher accept a store-backed sink so every emitted event persists automatically under `state/` (or `RIMBRAIN_STATE_DIR`).

**Why this priority**: adoption — evidence capture should be on by default in sim runs.

## Edge Cases

- Log path missing/empty → store opens clean, first append creates it.
- Mid-file corruption (line N unparseable, not the tail) → `load()` reports `corrupt_lines` count and skips them; tail truncation only ever touches the last line.
- Snapshot target dir missing → created.
- Two stores appending concurrently → per-append lock via `msvcrt`/O_APPEND writes; sequence gaps flagged on load.
- `RIMBRAIN_STATE_DIR` env override → all store paths honor it (tests isolate).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-501**: `EventStore` appends canonical envelopes as one-JSON-per-line to `<state_dir>/events.jsonl`; `load()` returns every parseable line in file order with a `corrupt_lines` count.
- **FR-502**: Open performs torn-tail recovery: unparseable final line truncated to the last `\n`, recovery recorded to `<state_dir>/recovery.jsonl`; a complete-but-unterminated final line is preserved.
- **FR-503**: `write_atomic(path, bytes)` writes via `<path>.tmp` + `os.replace`; no partial target is ever visible.
- **FR-504**: `project(events)` folds envelopes deterministically into `{counts_by_type, last_action, last_plan, first_seq, last_seq, total}`; `rebuild()` writes it atomically to `<state_dir>/projection.json`.
- **FR-505**: Dispatcher/planloop sinks can bind the store so every emitted event persists; CLI `--no-store` disables.
- **FR-506**: Sequence gaps or duplicate `sequence` values are reported by `load()` (never silently renumbered).
- **FR-507**: All paths honor `RIMBRAIN_STATE_DIR`; no symlinks (Windows junction-free).

## Success Criteria *(mandatory)*

- **SC-501**: Restart round-trip preserves every event in order.
- **SC-502**: Truncated-tail fixture: valid lines survive, partial tail removed, recovery marker written.
- **SC-503**: No `.tmp` files remain after `write_atomic`; kill-safety is structural.
- **SC-504**: Two projections over one log are byte-identical; projection is rebuildable from the log alone.
- **SC-505**: A sim `loop`/`plan` run persists all its events to disk.

## Assumptions

- Stores live in `components/runtime` (runtime owns evidence persistence for now; lab reads the files, never writes).
- One process per store file in v0; cross-process concurrent append is best-effort via O_APPEND, gaps flagged not prevented.
- No schema/migration system yet — envelopes carry `schema_version` for when one lands.

## Out of Scope

- Objective/task/lock model (WP-102), shadow controller (WP-104), observation shadow (WP-103).
- Lab export formats, redaction, checksums (WP-500).
- Snapshot rotation/compaction policies.
