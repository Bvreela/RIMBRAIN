# Feature Specification: Agent Transparency Views — Planning & Goals + Quick-Action Matrix

**Feature Branch**: `013-agent-transparency-views`

**Created**: 2026-09-23

**Status**: Draft

**Input**: The system must provide the user a clear, real-time view of the AI agent's planning, goals, and internal reasoning — both long-term strategic intent and short-term action selection — through two synchronized views: a Planning & Goals View (high-level objectives, priorities, long-horizon reasoning) and a Quick-Action Matrix View (moment-to-moment tactical decisions, including which capability primitives are invoked and why).

## Purpose

Feature 009 shipped a narrative thought feed (`state/feed.md`) — prose summaries of canonical events. It does not answer "what is the agent trying to achieve right now, in what order, and why" or "what did the engine just decide this poll." This feature adds two structured, always-current views rendered from canonical state every poll:

1. **Planning & Goals View** (`state/planning.md` + canonical `state/planning.json`) — active mode, ordered phase goals with satisfaction state, exit-condition evaluation, current blockers, and the latest long-horizon planner proposal when one exists.
2. **Quick-Action Matrix** (`state/actions.md` + canonical `state/decisions.jsonl`) — one row per dispatched capability this poll: tick, source (phase id or rule id), template invoked, resolved params, outcome, and the pack-declared reason chain (`when`/`needs` gate identity).

Both views are derived artifacts: canonical JSONL/JSON records stay authoritative; the markdown is a disposable render. Views expose reasoning *surfaces* (which rule fired, which predicate gated it, which params resolved) — never private model chain-of-thought (UR-EXP-008).

## User Stories *(mandatory)*

### User Story 1 - Planning & Goals View (Priority: P1)

Every poll, the runtime writes a Planning & Goals view that a user can open to see: the active mode, the ordered goal list (pack phase ids in execution order), each goal's current state (pending/dispatched/verifying/satisfied/failed) and its effect predicate's live truth value, the exit-condition eval block, and blockers (latest transition reason per goal). When a planner proposal exists in canonical events, its summary (goal text + proposed phase list, not CoT) appears as the long-horizon section.

**Acceptance Scenarios**:

1. **Given** start mode mid-run with beds verifying, **When** `state/planning.md` is read, **Then** it shows phases in pack order with per-phase state, `beds` marked verifying, and exit conditions with per-condition truth values.
2. **Given** a pack with phases reordered, **When** the view renders, **Then** goal order follows the pack order — the view never invents ordering.
3. **Given** a failed phase (attempts exhausted), **When** the view renders, **Then** that goal shows `failed` with the ledger's terminal reason as the blocker.

### User Story 2 - Quick-Action Matrix (Priority: P1)

Every dispatch through `run_steps`/`run_rules` appends a decision record: `{tick, poll, source, template, params, ok}`. The matrix view renders the most recent window as a table; `decisions.jsonl` is the canonical append-only record. Each row's `source` names the pack element responsible (e.g. `rule:idle-work`, `phase:cookstation`) — that is the "why" trail a user can trace back to the YAML line.

**Acceptance Scenarios**:

1. **Given** the idle rule fires on a wandering pawn, **When** the matrix renders, **Then** a row shows `rule:idle-work`, template `assign-job`, resolved pawn/target params, and `ok`.
2. **Given** a step skipped by `when`/`needs`, **When** the matrix renders, **Then** no row exists for it — the matrix records decisions taken, not silence.
3. **Given** 200 polls, **When** `decisions.jsonl` is inspected, **Then** it contains every dispatched action in tick order and `actions.md` shows only the configured trailing window.

### User Story 3 - Synchronization and Provenance (Priority: P1)

Both views render from the same poll's data — the planning snapshot and the decision rows are written together after `run_rules`/`mode.step` each iteration. Views carry `pack_revision` so a user can correlate behavior with the exact pack hash.

**Acceptance Scenarios**:

1. **Given** a single poll, **When** views are written, **Then** `planning.json` and the poll's `decisions.jsonl` rows share the same `tick`/`poll` stamp.
2. **Given** a pack edit between runs, **When** the view renders, **Then** `pack_revision` differs — provenance is honest.

## Requirements *(mandatory)*

- **FR-1101**: `policy.py` `Ctx` gains a `decisions` sink; `run_steps` and `run_rules` append `{tick, poll, source, template, params, ok}` for every dispatch. Source is the phase id or rule id supplied by the caller.
- **FR-1102**: `runtime/views.py` renders `state/planning.md` + `state/planning.json` (mode, ordered goals w/ state+effect truth, exit eval, blockers, planner summary if present) and `state/actions.md` (trailing-window table) from canonical inputs.
- **FR-1103**: `_run_start`, `run_combat`, `run_cycle`, and `run_loop` write both views each poll; render failure must not interrupt control (fail-open on views, fail-closed on control).
- **FR-1104**: `decisions.jsonl` is append-only canonical; `planning.md`/`actions.md` are disposable renders rebuildable from canonical records (UR-DAT-007).
- **FR-1105**: Views never include model chain-of-thought or secrets; planner summaries cite the `plan.proposed` event's declared goal/plan fields only.

## Success Criteria *(mandatory)*

- **SC-1101**: During a sim start-mode run, `state/planning.md` shows pack-ordered goals and `state/actions.md` shows rows matching the poll's dispatches.
- **SC-1102**: Editing the pack (remove/reorder a phase) changes the rendered goal list without code changes.
- **SC-1103**: `decisions.jsonl` rows carry source ids traceable to pack YAML elements.
- **SC-1104**: Live run writes both views with real tick/poll stamps.
- **SC-1105**: Suite, corpus, validators green; a render exception during a poll does not abort the run (covered by test).
