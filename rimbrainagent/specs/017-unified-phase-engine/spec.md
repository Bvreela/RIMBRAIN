# Feature Specification: Unified Phase Engine

**Feature Branch**: `feature/017-unified-phase-engine`

**Created**: 2026-09-24

**Status**: Draft

**Input**: "Remove the existing start mode system entirely and replace it with a unified, phase-driven structure using the main loop (plan → execute → improve → plan). The Pack defines the Start Phase as a prescriptive, structured initialization layer; all execution logic previously tied to start mode migrates into this phase. After initialization, control flows through a continuous plan → loop → improve → plan cycle, with the Pack defining goals, constraints, and action lists for each brain. The Loop produces compact action lists — no more than 20 items — for Laya to choose from at colony and pawn level, using real-time colony stats, pawn stats, efficiency metrics, and short-term goals. The planner runs as a central part of the main loop (~150s cadence), deriving short-term plans from long-term plans; Laya is the execution master. The mutation/improvement loop fully incorporates these changes so pack phases — including the Start Phase — can evolve over time."

**ADR**: `specs/90-decisions/ADR-019-unified-phase-engine.md`

**Terminology**: the pipeline's final stage is named **reflect** (domain term); its module is `evolve.py`; the pack config key stays `mutate:` for feature-016 compatibility. These are one thing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One loop drives the whole colony lifecycle (Priority: P1)

The operator launches a single run command. The brain initializes a fresh colony through a prescriptive initialization phase (the same bootstrap contract today's start mode delivers), then continues into standing governance and planner-driven phases — without mode switches, subsystem handoffs, or separate commands. Every capability previously unique to start mode (verified phase steps, exit contracts, standing goals, universal rules, vitals, brain reset, live mutation) works in the one loop.

**Why this priority**: Six parallel loops and two engines are the root defect; consolidation is the entire point of the feature. Everything else layers on top.

**Independent Test**: Run the sim harness end-to-end: init phase completes its bootstrap contract, standing goals hold, and the run continues indefinitely with no second subsystem engaged.

**Acceptance Scenarios**:

1. **Given** a fresh colony, **When** a run starts, **Then** the pack's initialization phase executes its ordered steps and verifies each step's declared effect before advancing.
2. **Given** the initialization phase's completion contract holds, **When** the run continues, **Then** standing goals keep evaluating every poll in the same loop — no handoff to a separate subsystem.
3. **Given** any pack phase (including init), **When** the pack file is edited mid-run, **Then** the run freezes on drift detection exactly as before.

---

### User Story 2 - Laya executes: bounded action lists every poll (Priority: P2)

Each poll, the engine compiles a bounded candidate action list — colony-level (which goal operation to drive next) and pawn-level (per-pawn job options) — capped at 20 items, ranked by pack-declared priority expressions. The select-tier model (Laya) picks from the offered options using real-time colony stats, pawn stats, rolling efficiency metrics, and the current short-term plan; the engine validates the pick against the offered set and dispatches through the single writer.

**Why this priority**: This is the user's core ask — the model becomes the execution brain, but only ever chooses among enumerated, validated options.

**Independent Test**: With the select endpoint stubbed to a fixed choice, verify every poll offers ≤20 candidates, the pick is validated against the set, and the dispatch lands in the ledger; with the endpoint unreachable, the declared fallback fires deterministically.

**Acceptance Scenarios**:

1. **Given** a poll with more than 20 eligible actions, **When** the list compiles, **Then** it is truncated to 20 by pack-declared priority order.
2. **Given** the select model returns an option not in the offered set, **When** the engine validates, **Then** the choice is rejected and the declared fallback executes instead.
3. **Given** the select endpoint is unreachable, **When** a poll needs a choice, **Then** the pack-declared deterministic fallback executes and a degradation event is emitted.
4. **Given** the init phase is active, **When** steps execute, **Then** structural steps stay deterministic while pawn-level job choices go through the select model.
5. **Given** any select decision, **When** it is made, **Then** the full candidate list, the pick, and the applied choice are logged for audit.

---

### User Story 3 - The planner strategizes in the loop (Priority: P3)

The plan-tier model runs as a first-class stage of the main loop — on a ~150-second cadence (pack-tunable), on phase boundaries, and on major events (raids, contract completion). It emits a short-term plan — active goals, priorities, and promotions from the pack's strategy catalog — which feeds the priority scoring of Laya's per-poll action lists. A slow or unreachable planner degrades gracefully: the last accepted plan stands until refreshed.

**Why this priority**: Closes the plan→execute→improve→plan cycle the user described; the planner's catalog promotions are how new long-horizon phases enter the run.

**Independent Test**: Advance the sim clock past the plan cadence; verify a plan request fires, an accepted plan reorders action-list priorities, and a failed plan call leaves the previous plan in force with a degradation event.

**Acceptance Scenarios**:

1. **Given** a running colony, **When** the plan cadence elapses, **Then** a plan request fires with the current observation digest.
2. **Given** an accepted plan, **When** the next action list compiles, **Then** its ordering reflects the plan's declared priorities.
3. **Given** the planner is unreachable or times out, **When** the cadence fires, **Then** the previous plan remains active and the run continues — the loop never blocks on the planner.
4. **Given** a plan promoting a catalog strategy into an active goal, **When** the goal becomes unsatisfied, **Then** it joins standing-goal evaluation like any pack goal.

---

### User Story 4 - One reflection pipeline mutates the whole pack (Priority: P4)

Failure signals, near-failure clusters, and periodic review trigger a single reflection stage that proposes pack mutations through one pipeline: digest → proposal (model or rules-only) → compile to the shared ops vocabulary → deterministic gate → candidate file → boundary-only promotion. Any pack surface — phases (including init), action lists, decide configuration, rules, standing goals — is mutable through the same governed path.

**Why this priority**: Three parallel propose→gate→promote pipelines exist today (improve, mutate, planloop); unification makes every pack surface evolvable through one audited path.

**Independent Test**: Trigger a reflection pass in sim; verify one gate validates schema, inventory, and class for a proposal touching a phase definition, and that the candidate promotes only at a run boundary.

**Acceptance Scenarios**:

1. **Given** a proposal targeting any pack phase (including init), **When** the gate validates, **Then** the same checks apply as for any other pack path — no special-cased surfaces.
2. **Given** a promoted candidate, **When** the new run loads it, **Then** the modified phase executes under identical engine semantics as before.
3. **Given** a regression after promotion, **When** the run scores worse than the recorded baseline, **Then** the pack auto-reverts per existing lineage rules.

---

### User Story 5 - Determinism where it matters, nowhere else (Priority: P2)

Sim runs and the test suite are fully deterministic — no model endpoints are ever invoked. Live runs are always model-assisted: Laya selects every poll, the planner strategizes on cadence, and every decision is logged to the evidence stream for audit. Reproducibility is replaced by auditability; "deterministic" narrows to sim, CI, and the legality/safety checks that gate every model choice.

**Why this priority**: The game itself is nondeterministic; demanding choice determinism live was unachievable theater. But losing determinism in tests would make the suite unverifiable.

**Independent Test**: Full suite passes with zero endpoint calls; a sim run produces identical event sequences across repeats.

**Acceptance Scenarios**:

1. **Given** sim mode, **When** any stage runs, **Then** no endpoint call is attempted and outcomes are deterministic across repeats.
2. **Given** a live run, **When** a model chooses, **Then** the decision record contains enough context to reconstruct why — candidates, stats snapshot, plan in force.

---

### Edge Cases

- Planner returns a plan promoting a goal whose prerequisites can never be met → it joins evaluation, stays blocked, and surfaces in the blocked-goal view; reflection may later mutate it.
- Select model healthy but planner down for a long window → Laya keeps executing the stale plan; staleness is visible in the snapshot.
- Action list compiles to zero candidates → the pack-declared fallback (`decide.select.fallback`, e.g. `priority_head`) fires; never a silent stall.
- Reflection proposes deleting the init phase → gate must still enforce schema validity; a pack without a valid init phase fails validation like any malformed pack.
- Live-mutate and a model-assisted run together: a promoted pack can change the action-list or decide config the *next* run uses — mid-run semantics never shift under the active pack hash.

## Requirements *(mandatory)*

### Functional Requirements

**Pipeline & engine**

- **FR-1401**: The system MUST provide a single run loop executing a fixed stage pipeline — observe → reflex → decide → act → verify → reflect — for the entire colony lifecycle.
- **FR-1402**: All behavior previously reachable only via start mode MUST execute in that loop: ordered verified init steps, exit-contract evaluation, standing goals, universal rules, periodic vitals, brain lifecycle requests, and reflection triggers.
- **FR-1403**: Pack `phases` MUST be an ordered list where each phase declares an identity, entry/completion conditions, goals or steps, and an action-list configuration; phase `init` is prescriptive (deterministic steps, verified effects).
- **FR-1404**: Legacy pack namespaces (`start.phases`, `govern.goals`, `universal.rules`, `emergency`, `exit`) MUST load into the unified structure via an automatic in-memory migration so existing packs keep working.
- **FR-1405**: Every rule dialect MUST evaluate through one predicate/resolver language; emergency rules become pre-decide reflexes expressed in the same dialect as all other rules.
- **FR-1406**: The system MUST produce one canonical observation per poll consumed by reflexes, rules, action-list compilation, planner digests, vitals, and views — no per-consumer observation shapes.

**Decide stage**

- **FR-1407**: Each poll MUST compile a candidate action list of at most 20 items spanning colony-scope (goal operations) and pawn-scope (per-pawn options), ordered by pack-declared priority expressions.
- **FR-1408**: The select-tier model MUST choose only among offered option identifiers; invalid, absent, or unreachable-endpoint outcomes MUST resolve to a pack-declared deterministic fallback with a degradation event.
- **FR-1409**: Select inputs MUST include colony statistics, per-pawn statistics, rolling efficiency metrics, and the current short-term plan — all drawn from the canonical observation and ledger state.
- **FR-1410**: Inside the prescriptive init phase, structural steps MUST execute deterministically while pawn-level job choices go through the select model.
- **FR-1411**: Every select decision MUST be logged with the full offered set, the model's pick, the applied choice, and the inputs that informed it.

**Plan stage**

- **FR-1412**: The plan-tier model MUST fire on a pack-tunable cadence (default ~150 seconds), on phase boundaries, and on declared major events.
- **FR-1413**: An accepted plan MUST be able to reorder action-list priorities, activate/deactivate goals, and promote catalog strategies (`goal_options`) into active goals or new phases.
- **FR-1414**: Planner failure MUST degrade to the last accepted plan (or rules-only defaults if none) — the loop MUST NOT block or stall on the planner.
- **FR-1415**: Plans MUST pass the deterministic review gate before adoption; rejected plans leave the prior plan in force.

**Reflect stage**

- **FR-1416**: One reflection pipeline MUST serve all pack mutation: digest → proposal → compile to the shared ops vocabulary → gate (schema, sealed inventory, class, budget) → candidate → boundary-only promotion.
- **FR-1417**: The mutation path whitelist MUST cover every pack surface including `phases`, `action_list`, `decide`, `reflexes`, and `rules`.
- **FR-1418**: Mid-run pack changes MUST remain impossible; promoted candidates apply only at run boundaries and regression auto-reverts per lineage rules.
- **FR-1419**: Existing improve-mode diagnosis (defect patterns, metrics scoring) MUST be preserved as evidence functions feeding the unified reflection stage.

**Modes, flags & determinism**

- **FR-1420**: Sim mode MUST never invoke model endpoints and MUST produce identical event sequences across repeated runs.
- **FR-1421**: Live runs MUST have model assistance always available when endpoints resolve — no deterministic-choices flag.
- **FR-1422**: The mode/flag surface MUST reduce to: `run` (unified), `cycle` (dev harness), and standalone stage entries (`--stage plan|reflect`) for debugging; `start` survives one release as a deprecated alias. Game backend selection (`--game sim|live`, sim default) MUST be orthogonal to mode — `sim` is the world implementation, not a mode.
- **FR-1423**: The interaction contract among fair/dev, live-brain, live-mutate, and episode boundaries MUST be explicitly defined; undefined combinations MUST fail closed.
- **FR-1424**: Selector authority MUST be staged per the constitution's qualification ladder: shadow mode (model picks logged, deterministic fallback executes) → bounded live trial → live authority, per model/prompt/context tuple. Authority state (current rung, divergence evidence, per-tuple record) MUST be persisted so promotion is inspectable and survives restarts.

**Consolidation**

- **FR-1425**: Duplicate engines and loops MUST be removed (the consolidation constraint on FR-1402): the start-mode engine, the generic loop's fixed-choice decider, the legacy universal-rules wrapper, and the standalone combat-mode engine are deleted, not deprecated in place.
- **FR-1426**: The three proposal/gate/promote implementations MUST merge into the single reflect pipeline; shared mechanics (candidate materialization, gate checks, lineage) live in one module.
- **FR-1427**: Run-local state (mode vars, rule state, reflection state, vitals state) MUST consolidate into one owned run-state object with defined persistence.
- **FR-1428**: The transparency views MUST present the unified picture: current phase, pending action list, last select choice (with fallback marker), active plan, and reflection status.
- **FR-1429**: The combat-mode subsystem MUST be pack-ified: raid-scenario behavior becomes phases/rules in a dev-class pack and `combatmode.py` is deleted; the dev harness (`cycle`) continues to drive it via the unified loop.
- **FR-1430**: Decide cadence MUST be pack-tunable (`decide.select.cadence_polls`, default every poll) so slow select endpoints cannot outrun the poll loop; when select lags, the engine skips rather than queues decisions.

### Key Entities

- **Phase**: Ordered lifecycle unit; `init` prescriptive, later phases planner-authored or pack-declared. Attributes: id, entry/completion conditions, goals/steps, action-list config.
- **Action List**: Per-poll bounded (≤20) candidate set across colony and pawn scopes; priority-ordered; consumed by the select tier.
- **Plan**: Planner output in force until superseded — goal ordering, active goals, catalog promotions; expires on refresh or explicit invalidation.
- **Candidate / Lineage**: Gated pack mutation artifact promoted only at boundaries; parent hash recorded for regression reverts (existing 016 semantics).
- **Decision Record**: Logged select outcome — offered set, pick, applied choice, inputs — the auditability backbone replacing live determinism.
- **Run State**: Consolidated per-run mutable state (vars, rule state, reflection state, vitals state) with one persistence owner.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh colony run reaches the initialization contract's completion through the unified loop with zero references to the deleted start-mode subsystem — verified by suite + grep.
- **SC-002**: Every poll offers no more than 20 select candidates; 100% of select outcomes (pick, invalid, fallback) are logged and dispatched through the single writer.
- **SC-003**: With the select endpoint down, the run completes a full sim episode on declared fallbacks with no stalled polls.
- **SC-004**: Planner cadence fires within ±10% of the configured interval during a healthy run; planner outage of any duration produces zero blocked polls.
- **SC-005**: A reflection pass can mutate a phase definition and the promoted pack executes it identically at the next boundary — round-trip verified in tests.
- **SC-006**: The full test suite is deterministic: repeated sim runs produce identical event streams; zero endpoint calls in sim mode.
- **SC-007**: Module count for loop/proposal machinery decreases: start-mode engine, legacy decider, universal-rules wrapper, and duplicate gate/promote code paths removed (net deletion, not addition).

## Assumptions

- Feature 016 (live pack mutation) lands before this work begins; the reflect stage builds on its trigger/gate/boundary machinery rather than competing with it.
- The select endpoint (`rimbrain.select` → local Laya) and plan endpoint (`rimbrain.plan` → OpenRouter-compatible) continue to exist; this feature wires them into the loop, it does not provision them.
- Live-run choice determinism is explicitly NOT required — the colony game is nondeterministic by nature; auditability via logged decision records is the replacement guarantee. Sim/CI determinism remains non-negotiable.
- `goal_options` catalog semantics from feature 015 carry forward — promotion is the missing consumption path this feature adds.
- The flag/CLI simplification may break existing launch scripts; `rimbrain.py` is updated in the same feature.
- Selector qualification (shadow → trial → authority) applies to the new action-list matrix; existing qualified matrices are unaffected.
