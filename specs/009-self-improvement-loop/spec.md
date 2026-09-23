# Feature Specification: Self-Improvement Loop

**Feature Branch**: `009-self-improvement`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User directive — embed a self-improvement loop into the spec so the brain can automatically fix bugs, refine the user experience, and enhance its own learning speed and quality. It operates as a long-horizon, fully autonomous task with no further user input, using self-checks and dedicated audit passes to validate code quality and UX. The brain package must be easy for users to customize so the AI genuinely learns to play, and the guided experience must feel engaging and transparent — users can see what the agent is planning and thinking as it runs.

## Purpose

A closed improvement cycle around the existing spine: the agent plays, records evidence, audits itself, proposes improvements, validates them against replayed evidence, and promotes the winners — all inside the existing safety invariants. Around that loop sit two user-facing surfaces: a **thought feed** (a human-readable stream of what the agent observes, plans, decides, and learns, as it runs) and a **customizable brain package** (policy packs + bindings + thresholds a user can read and edit without touching code).

## User Stories *(mandatory)*

### User Story 1 - Autonomous Improvement Cycle (Priority: P1)

On a declared cadence (per episode and per wall-clock interval), the agent runs a self-check pass: it replays recent canonical evidence, detects defects and regressions (refusals, verify-failures, failed phases, repeated identical action failures), generates improvement proposals through the existing planner/review pipeline, validates candidates against replay, and records promotion decisions. The cycle requires no user input and produces a full evidence trail of every decision.

**Why this priority**: this is the core of the directive — the brain improves itself, autonomously, inside the safety envelope.

**Independent Test**: scripted episode history containing a planted defect (e.g. a recurring refused action) — the loop emits a diagnosis event, produces a candidate fix, validates it, and records a promotion or rejection decision with reasons.

**Acceptance Scenarios**:

1. **Given** an episode history with a recurring defect, **When** a self-check cycle runs, **Then** a diagnosis is emitted naming the defect class, affected event span, and proposed remediation path.
2. **Given** a candidate improvement, **When** validated against replayed evidence, **Then** it is promoted only if it scores no worse on declared metrics; otherwise rejected with recorded reasons.
3. **Given** the loop has run N cycles, **When** evidence is inspected, **Then** every cycle produced a complete audit trail (diagnosis → proposal → validation → decision).

### User Story 2 - Dedicated Audit Passes (Priority: P1)

Independent audit checks evaluate each improvement cycle and the system as a whole: code-quality checks (test suite, corpus, component validators — fail-closed), policy-quality checks (pack diffs reviewed for invariant violations), and UX checks (thought feed emits at expected points, events are human-readable, error states are explained). Audit failures block promotion and are recorded — never silently skipped.

**Why this priority**: autonomy without audit is unaccountable; the user explicitly asked for dedicated audit validation of code quality and UX.

**Independent Test**: a candidate pack that violates an invariant (e.g. bypasses the dispatcher) is caught by audit and refused with a recorded reason; a clean candidate passes.

**Acceptance Scenarios**:

1. **Given** a candidate change that breaks tests or violates a schema, **When** audit runs, **Then** promotion is refused and the refusal names the failing check.
2. **Given** a candidate that weakens a safety invariant, **When** audit runs, **Then** it is refused regardless of performance improvement.
3. **Given** a healthy cycle, **When** audit runs, **Then** a recorded verdict (pass) is emitted as a canonical event.

### User Story 3 - Thought Feed (Priority: P1)

As the agent runs, it emits a human-readable thought feed: what it observed, what it is planning and why, what it decided, what it learned. The feed is a first-class output (file + optional UI surface) — the "handholding" experience: engaging, transparent, and legible to a non-developer. Every plan, reflex, task transition, diagnosis, and promotion decision has a feed entry.

**Why this priority**: "users should be able to see what the agent is planning and thinking as it runs" — transparency is a stated requirement, not a nicety.

**Independent Test**: run any loop — the feed contains an entry for every decision point, in plain language, in order, keyed to the canonical event it narrates.

**Acceptance Scenarios**:

1. **Given** a running loop, **When** a reflex fires, **Then** the feed explains what emergency was seen and what was done — before or alongside the action event.
2. **Given** a planning round, **When** a plan is proposed/reviewed/accepted, **Then** the feed narrates the intent, the critique verdict, and the outcome.
3. **Given** a self-improvement cycle, **When** a decision is made, **Then** the feed explains what was learned and what changed (or why nothing changed).

### User Story 4 - Customizable Brain Package (Priority: P1)

The brain package is user-editable data: policy packs, endpoint bindings, and tuning thresholds live in documented YAML a user can open, read, and change — with a documented customization guide, validation on load (bad edits refuse with readable errors), and candidate packs that users can diff and promote deliberately.

**Why this priority**: "easy for users to customize so the AI can genuinely learn" — learning means the editable surface must actually work for humans.

**Independent Test**: a user-facing doc + validation path — edit a pack value, reload, observe behavior change or a readable refusal; no code touched.

**Acceptance Scenarios**:

1. **Given** a malformed pack edit, **When** loaded, **Then** refusal names the file, field, and expectation in plain language.
2. **Given** a valid pack edit, **When** loaded, **Then** behavior changes with no code changes and the change is visible in emitted events.

### User Story 5 - Learning Metrics (Priority: P2)

The loop tracks learning progress: per-episode metrics (refusal rate, verify-failure rate, task completion rate, time-to-baseline) recorded canonically, so improvement is measured — "speed and quality of learning" is a tracked quantity, not a hope.

**Why this priority**: the directive asks to "enhance the brain's learning speed and quality" — that requires measurement before optimization.

**Independent Test**: two episode histories with different outcomes produce different recorded metrics; a candidate that improves the metric is preferred over one that doesn't.

**Acceptance Scenarios**:

1. **Given** a completed episode, **When** metrics are computed, **Then** a metrics event records the declared quantities from canonical evidence alone.
2. **Given** two candidate packs, **When** evaluated, **Then** the one scoring better on declared metrics wins — ties keep the incumbent (stability bias).

## Edge Cases

- **Self-check finds nothing**: the cycle emits a no-op diagnosis and ends — never invents work.
- **Improvement candidate is unsafe**: audit refuses it; the loop records and moves on — never force-promotes.
- **Validation evidence is insufficient** (too few episodes): decision is `defer`, recorded — never promotes on noise.
- **Loop crashes mid-cycle**: the cycle is a ledger workflow — restart reconciles and resumes; a half-applied candidate never becomes active.
- **Active scored episode**: no pack swap mid-episode — promotions take effect at the next episode boundary only (immutability invariant).
- **Feed output unavailable** (file locked/path bad): the loop still runs; feed failure is recorded, never fatal to gameplay.
- **User edits a pack mid-episode**: load-time validation applies at next load; the active in-episode copy stays immutable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-801**: a self-check cycle replays recent canonical evidence and emits `selfcheck.diagnosed` events naming defect class, affected span, and remediation path (or a recorded no-op).
- **FR-802**: improvement proposals flow through the existing typed-proposal pipeline — candidates materialize as candidate packs; no direct mutation of the active pack.
- **FR-803**: promotion requires (a) declared metrics no worse on replayed evidence, (b) audit pass, (c) an episode boundary — scored-episode immutability is preserved.
- **FR-804**: dedicated audit passes — code quality (tests, corpus, validators), policy invariants (single writer, no model-executed calls, fail-closed preserved), UX (feed coverage, readable refusals) — each emitting a canonical verdict event; failures block promotion and are never skipped.
- **FR-805**: a thought feed emits a human-readable entry for every decision point (observation summary, plan intent, reflex fire, task transition, diagnosis, promotion decision), keyed to its canonical event, as a first-class output file; entries degrade to structured event echoes when no narrative generator is bound.
- **FR-806**: the brain package (packs + bindings + thresholds) is documented, user-editable YAML with load-time validation producing plain-language refusals; a customization guide ships in the repo.
- **FR-807**: per-episode learning metrics (refusal rate, verify-failure rate, task completion rate, time-to-baseline where applicable) computed from canonical evidence and emitted as a canonical event.
- **FR-808**: the improvement cycle runs unsupervised for a declared number of iterations; every cycle leaves a complete audit trail; the loop terminates cleanly on demand or exhaustion — never a runaway.
- **FR-809**: new event types (`selfcheck.diagnosed`, `audit.verdict`, `improvement.promoted`/`improvement.rejected`, `episode.metrics`) register native in event-map + schemas + corpus.
- **FR-810**: all invariant boundaries hold — single writer, typed proposals only, canonical records authoritative, fail-closed on missing/bad data.
- **FR-811**: live runs emit periodic `colony.vitals` events (colonists, mood_avg, mood_min, downed, dead, sick_now) plus one `colony.sickness` event per new illness-hediff onset per pawn (diffed across samples) — outcome-level failure evidence, not just dispatch refusals.
- **FR-812**: defect patterns gain a `where` predicate (`{field, op, value}` over the event) and optional `window_ticks` (e.g. 3.6M = one game year), enabling colony-health defect classes: `poor_mood` (sustained low mood), `repeat_sickness` (>1 illness per pawn-year), `multiple_downed`, `colonist_death`.
- **FR-813**: `propose` accepts dict remediations `{ops: [...]}` — declarative mutations (`set_cfg`, `append`, `drop_template`, `drop_rule`) applied to a candidate copy. Failure definitions AND their fixes stay pack-declared; the engine applies ops mechanically. Candidates still flow through audit + metrics + episode-boundary gates unchanged.

### Success Criteria

- **SC-801**: sim evidence containing a planted recurring defect produces a diagnosis → candidate → validation → decision trace with zero human input.
- **SC-802**: an unsafe candidate (invariant violation or broken tests) is refused by audit with a recorded reason — promotion impossible.
- **SC-803**: a full loop run produces feed entries covering 100% of emitted decision-point events, each keyed to its event id.
- **SC-804**: a malformed pack edit refuses with a plain-language error naming file + field; a valid edit changes behavior with no code change.
- **SC-805**: two episodes with different outcomes produce measurably different metrics events; a better-scoring candidate beats a worse one in validation.
- **SC-806**: planted vitals evidence (mood_min < threshold sustained, downed >= 2, dead >= 1, >=2 sickness onsets per pawn within a game year) produces the matching defect findings, and dict-remediation patterns yield candidate packs with the declared mutations applied; live runs emit `colony.vitals` events without interrupting control.

## Constraints

- Autonomy is bounded by the safety envelope: live game writes still go through the dispatcher and pack policy; the loop can improve policy, never bypass it.
- Scored-episode immutability: promotions apply at episode boundaries only.
- The loop is spec/data-driven like everything else — cycle cadence, metric definitions, and audit checks are configurable, not hardcoded magic.
- Feed entries must not leak secrets — same privacy classification rules as canonical events.
- No invented evidence: diagnoses and metrics derive from canonical records only (real-colony-data-only rule extended to self-analysis).

## Assumptions

- "Fix bugs" scopes to policy/behavior defects detectable from evidence (refusals, verify-failures, regressions) and candidate-pack remediation; arbitrary source-code rewriting is out of scope for this feature — code-level findings become recorded diagnoses for the operator.
- "Audit subagents" maps to dedicated audit passes in the loop (deterministic checks + model-advisory review where bound); the mechanism is internal, the contract is the verdict events.
- "00.00.01 build" means the first release-acceptance gate set passes: component validators, corpus, runtime suite, and a documented release record — this feature contributes the self-improvement + transparency surfaces to that build.
