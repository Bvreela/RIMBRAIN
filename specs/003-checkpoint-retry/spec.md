# Feature Specification: Checkpoint-Reload Retry Loops (Debug/Eval Mode)

**Feature Branch**: `003-checkpoint-retry`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "add a debug feature to allow the game to reload save game checkpoints
and retry increments of game time. Retry/continue loops configurable by amount of game time and
number of retries; allow the AI to continue early if it thinks it succeeded before the retries are
met; each loop mutates and improves the plans and matrices."

## Purpose

A bounded **checkpoint-retry harness** for development and evaluation: snapshot the game, advance a
configured increment of game time, score the outcome against the active plan's falsifiable
predicates, and — on failure — reload the checkpoint, mutate plan/matrix parameters, and retry.
Iterations stop early when the success gate passes. Every iteration records its verdict and the
mutation applied, producing a causal chain of plan variants.

This is a **debug/eval-mode capability**. It is explicitly forbidden during scored episodes —
constitution forbids mutating policy mid-episode; retry loops exist to *produce* better candidate
packs/matrix revisions, not to edit live authority.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Checkpoint Window Replay (Priority: P1)

A developer configures a retry loop: checkpoint save name, game-time increment (e.g. 2 game-hours),
max retries (e.g. 4), and a success gate. The system saves a checkpoint, advances the increment at
a chosen speed, evaluates the gate, and either proceeds to the next increment or reloads and retries
with a mutated plan — up to the retry cap.

**Why this priority**: This is the core loop everything else depends on. Without reliable
save→advance→evaluate→reload, no iteration machinery is trustworthy.

**Independent Test**: With a test colony, run a loop with `window=1h, max_retries=2`; verify the
game returns to the checkpoint tick on each reload and the run log records each iteration.

**Acceptance Scenarios**:

1. **Given** a running game and a retry config, **When** the loop starts, **Then** a named
   checkpoint save is created and each iteration begins from an identical game state (same
   `game.status` tick/day after load).
2. **Given** a failed gate evaluation, **When** retries remain, **Then** the checkpoint reloads and
   a mutated plan/matrix revision is applied before the next increment.

---

### User Story 2 - Early-Exit Success Gate (Priority: P1)

The AI evaluates the success gate after each increment. When the gate passes — the plan's
falsifiable predicates hold against observed state — remaining retries are skipped and the run
continues to the next increment (or completes).

**Why this priority**: The user's explicit ask — don't burn retries on plans that already worked.
Early exit keeps loops cheap and makes the gate the single source of "did it work".

**Independent Test**: Configure a gate that trivially passes on iteration 1 with `max_retries=4`;
verify exactly one increment ran and the loop reported `early_exit`.

**Acceptance Scenarios**:

1. **Given** a gate that passes on iteration N < max_retries, **When** the increment ends,
   **Then** the loop records `early_exit` at iteration N and does not reload.
2. **Given** a gate that never passes, **When** max_retries is reached, **Then** the loop reports
   `exhausted` with per-iteration verdicts and stops — it never loops forever.

---

### User Story 3 - Plan/Matrix Mutation per Iteration (Priority: P2)

Each retry applies a declared mutation to the candidate plan or action-matrix row set — e.g.
reorder priorities, adjust a scalar parameter, swap a selector option — drawn from a bounded,
declared mutation space. Every iteration records `{iteration, checkpoint, mutation, verdict,
gate_detail}` as canonical events, so the retry chain is replayable and auditable.

**Why this priority**: Mutation-with-provenance is what turns "try again" into *learning* — each
loop must produce an attributable improvement, not random retry noise.

**Independent Test**: Run 3 iterations with a stubbed always-fail gate; verify each iteration's
record contains a distinct mutation and the mutation log diffs cleanly.

**Acceptance Scenarios**:

1. **Given** a declared mutation space, **When** a retry begins, **Then** exactly one mutation from
   the space is applied and recorded; unmutated retries are forbidden (retrying identical state is
   meaningless).
2. **Given** a mutation that fails contract validation, **When** the iteration starts, **Then** it
   is rejected with a structured error and the loop falls back to the last valid revision (never
   runs an invalid plan).

---

### User Story 4 - Retry-Chain Evidence and Fixture Export (Priority: P3)

Each retry loop emits a portable fixture per the US5 fixture-package contract: checkpoint
identifier, iteration records, mutations, gate verdicts, and final outcome — replayable offline and
diffable across runs.

**Why this priority**: Retry chains are evaluation data; making them fixtures lets Lab compare
"did this mutation actually help" across model/pack revisions without live games.

**Acceptance Scenarios**:

1. **Given** a completed retry loop, **When** the fixture is exported, **Then** it contains every
   iteration's record plus provenance linking to the baseline bundle and the pack revision under
   test.
2. **Given** two identical retry configs on identical checkpoints, **When** a deterministic
   mutation policy is used, **Then** iteration records are identical (same mutations, same order).

---

### Edge Cases

- **Load failure or game crash mid-window**: detect via `game.status` polling; fail closed, mark
  the iteration `aborted`, and never leave the game in a half-loaded state. The last good
  checkpoint remains authoritative.
- **Checkpoint collision**: checkpoint names are namespaced (`retry/<run_id>/cp-<n>`) and isolated
  from user saves (TE-024 save hygiene); `game.list_saves` is used to verify isolation.
- **Non-deterministic game**: RimWorld has RNG; the gate must use state predicates robust to noise
  (e.g. "stock >= X", "no colonist dead"), not exact-event equality. Exact equality is only
  meaningful when a seed/determinism knob is in force.
- **Mutation budget exhaustion**: mutation space may declare a finite variant set; exhausting it
  ends the loop as `exhausted` even before `max_retries`.
- **Scored-episode guard**: attempting to start a retry loop while a scored episode is active is a
  hard rejection — retry loops never run inside scored evidence.
- **Human gate**: enabling retry mode is an operator action; a loop cannot self-extend its wall
  clock or retry budget beyond configured bounds.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-201**: The system MUST support a checkpoint-retry loop: `save checkpoint → advance
  game-time window → evaluate gate → on failure reload and retry`, using bridge save/load/status
  methods (`game.save`, `game.load`, `game.list_saves`, `game.status`, `game.speed`).
- **FR-202**: The retry configuration MUST declare: `window` (game-time increment, in ticks or
  hours), `max_retries` (hard cap), `speed`, `checkpoint_family` (namespaced save prefix), and the
  success gate reference — all recorded in the run manifest.
- **FR-203**: The gate MUST be evaluable mid-run and support **early exit**: a pass at iteration N
  ends retries for that increment. Gate evaluation uses falsifiable predicates over observed
  state (UR-MOD-009-style predicates bound to the active plan).
- **FR-204**: Each retry MUST apply exactly one recorded mutation from a declared mutation space;
  identical retries are forbidden; invalid mutations are rejected and the prior revision is kept.
- **FR-205**: Every iteration MUST emit canonical events (per the feature-001 envelope):
  `retry.checkpoint.saved`, `retry.window.started`, `retry.gate.evaluated`,
  `retry.mutation.applied`, `retry.iteration.completed` (verdict), `retry.loop.completed`
  (`early_exit` | `exhausted` | `aborted`), carrying checkpoint id, iteration index, mutation, and
  gate detail.
- **FR-206**: Checkpoint saves MUST be namespaced and isolated from user saves; the harness verifies
  isolation via `game.list_saves` before each loop.
- **FR-207**: The loop MUST enforce hard bounds: `max_retries`, a wall-clock budget per window, and
  a total-run budget; exceeding any bound aborts the loop with a named error.
- **FR-208**: Retry loops MUST refuse to start while a scored episode is active and MUST NOT be
  usable inside scored evidence (constitution: immutable policy during scored runs).
- **FR-209**: Retry-loop records MUST be exportable as a fixture package per the US5 contract —
  replayable and diffable offline.
- **FR-210**: On reload, the harness MUST verify the loaded state matches the checkpoint (same
  tick/day via `game.status`) before advancing; mismatch aborts with a named error.

### Key Entities

- **RetryConfig**: `{window_ticks|window_hours, max_retries, speed, checkpoint_family,
  gate_ref, mutation_space_ref, budgets{wall_clock_s, total_s}}` — declarative loop config.
- **Checkpoint**: a namespaced save `{family, index, tick, day}` capturing the state the loop
  returns to on failure.
- **Iteration record**: `{iteration, checkpoint_id, mutation, gate_verdict, gate_detail,
  window_ticks, events[]}` — one per window attempt.
- **Mutation space**: declared enumerable set of plan/matrix parameter edits the loop may apply —
  one per retry, recorded, never unbounded.
- **Gate verdict**: `{passed, predicates:[{id, expected, observed, met}], early_exit}` — the
  evaluate-step output driving continue/retry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-201**: A configured loop reliably returns the game to the checkpoint tick on every reload
  (verified via `game.status` before each window) — 0 state-drift failures across a test run.
- **SC-202**: Early exit fires correctly — a passing gate at iteration N stops retries at N; no
  wasted reloads.
- **SC-203**: Every iteration is attributable — the retry chain fixture lets a reviewer answer
  "which mutation produced this outcome" without re-running the game.
- **SC-204**: A retry loop cannot exceed its declared bounds (retries, wall-clock, window count);
  exceeding aborts with a named error, never a hang or infinite loop.
- **SC-205**: Retry loops never contaminate scored evidence — attempting one during a scored
  episode fails closed; mutation records never mutate an immutable pack (they produce new
  revisions).

## Assumptions

- The bridge exposes reliable `game.save`/`game.load`/`game.status`/`game.speed` (verified live
  2026-09-22 on zorrobyte RimBridge :8765 — 115-method surface).
- RimWorld RNG makes identical replays non-deterministic unless a determinism knob exists; gates
  therefore evaluate *state predicates*, not exact event equality.
- Retry loops are dev/eval machinery owned by Lab + runtime loop control — not part of scored
  episode evidence and not usable inside them.
- Mutation applies to candidate plan/matrix *revisions*, never in-place on an active immutable
  pack (constitution compliance).
- The game's autosave and user saves are untouched; checkpoints use a `retry/` namespaced family.

## Out of Scope

- Scored-episode integration (retry loops are explicitly excluded from scored evidence).
- Automatic synthesis of mutation spaces by an LLM (v1 uses declared spaces; learned mutation is a
  later ADR).
- Long-horizon N-day replays (v1 bounds to short increments; soak behavior is a separate feature).
