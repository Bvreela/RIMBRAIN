# Research: Unified Phase Engine

**Date**: 2026-09-24 | **Feature**: 017

All unknowns were resolved in design discussion before this document. Recorded here as Decision / Rationale / Alternatives for traceability.

## R1 — Loop topology

- **Decision**: One pipeline — observe → reflex → decide → act → verify → reflect — one `run` mode; modes become pack phase configurations, not code paths.
- **Rationale**: Six loops each implemented a subset; only `run_start` was complete. A mode flag selecting "which subset of the system runs" is the root defect.
- **Alternatives**: keep startmode + handoff to planloop at `start.completed` (rejected — preserves dual engines and the mutation-surface split); extract a shared poll-skeleton helper while keeping six loops (rejected — treats duplication as a library problem when it's a topology problem).

## R2 — Where the start-mode machinery goes

- **Decision**: `PhaseEngine` in `phase.py` ports `StartMode` mechanics (vars, `_drive`, retry backoff, `exit.fix` chains, ledger-verified effects). `start.phases` becomes `phases[0]` (`init`, `prescriptive: true`); `exit` becomes `init.complete`; `govern.goals` becomes `standing_goals` evaluated every poll.
- **Rationale**: the mechanics are phase-agnostic already; only the namespace was start-specific.
- **Alternatives**: keep `start` namespace as special (rejected — mutation surface must be uniform so the reflect stage can evolve init like any phase).

## R3 — Decide tier wiring

- **Decision**: per-poll action-list compiler → ≤20 candidates (colony scope: satisfiable goal ops; pawn scope: per-pawn options) → one batched systemone `questions` request → validate pick ∈ offered set → dispatch. Fallback: pack-declared deterministic head. `init` structural steps skip select (deterministic); pawn jobs inside `init` still select.
- **Rationale**: bounded-authority shape required by Constitution II; one request per poll bounds latency; ≤20 is a model-context contract, not a preference.
- **Alternatives**: per-question requests (latency ×N); Laya over raw methods (violates Principle II); planner-per-poll (wrong tier — cost/latency).

## R4 — Planner role

- **Decision**: `rimbrain.plan` fires on pack-tunable cadence (~150s), phase boundaries, and declared major events. Accepted plans reorder action-list priorities, toggle goals, promote `goal_options` into active goals/phases. Gate stays decisive. Failure → last plan stands.
- **Rationale**: user directive — "big brain gives short-term plans based on its long-term plans; Laya is the execution master."
- **Alternatives**: boundary-only planning (misses mid-phase shifts like raids); planner optional flag (rejected by user — planner is central).

## R5 — Reflect unification

- **Decision**: `evolve.py` = 016 `mutate` triggers/digest/gate/boundary + `improve` diagnose/metrics as evidence functions + `planloop` promotion machinery. `packmut` whitelist covers all v1 surfaces.
- **Rationale**: three pipelines already converging ad hoc (`mutate.reflect` calls `improve.diagnose` + `compile_legacy`); unify before the shim hardens.
- **Alternatives**: keep three pipelines behind a façade (rejected — same defect, new paint).

## R6 — Determinism contract

- **Decision**: sim/CI deterministic (no endpoint calls, repeatable streams). Live always model-assisted; reproducibility replaced by logged decision records (offered set, pick, applied, inputs). `--no-select` flag does not exist.
- **Rationale**: user directive + honest analysis — the game is nondeterministic; live choice determinism was unachievable; Constitution VII auditability is the real guarantee.
- **Alternatives**: replay recorded decisions for scored runs (deferred — adds machinery for a guarantee the game layer voids anyway).
- **Cost accepted**: promote/revert attribution is noisier; false reverts are cheap (re-proposal), revisit if thrash observed.

## R7 — Selector qualification

- **Decision**: action-list matrix starts in **shadow mode** (Laya picks logged, deterministic fallback executes, divergence measured) → bounded live trial → live authority, per model/prompt/context tuple (Constitution VI).
- **Rationale**: mandatory qualification ladder for new model authority.
- **Alternatives**: direct authority (unconstitutional); per-pack opt-in (fragmented authority records).

## R8 — Observation contract

- **Decision**: `observe.py` produces one canonical obs per poll — sections: colony, pawns, map, stocks, vitals, threats. `observe_start`, `planloop.enrich`, `vitals.sample` merge in. Every stage consumes sections of the same obs.
- **Rationale**: three shapes meant planner saw state policy never saw and vice versa.
- **Alternatives**: keep per-consumer observers (rejected — F4 finding).

## R9 — Reflex dialect

- **Decision**: `emergency:` rules parsed into the `policy.check` dialect at load (reflex class: pre-decide, priority-ordered). `dispatch.py::_condition`/`_op_holds` deleted.
- **Rationale**: two predicate languages for one concept; only `policy.check` reaches resolvers/obs paths.
- **Alternatives**: upgrade the private evaluator to parity (rejected — doubles the language).

## R10 — Flag/mode surface

- **Decision**: `--mode run` (start → one-release alias), `--stage plan|reflect` standalone debug entries, `--game sim|live` orthogonal backend selection, explicit flag-interaction table (fair/dev × live-brain × live-mutate × boundary), undefined combos fail closed.
- **Rationale**: F7 — implicit interactions were unanswerable; sim is the world implementation, not a mode — separating mode from backend keeps `run` semantically identical across sim and live.

## R11 — Combat mode fate (added post-analyze)

- **Decision**: `combatmode.py` is pack-ified, not kept as an engine — raid-scenario behavior becomes phases/rules in a dev-class pack (`dev-lab-v0`), driven by the unified loop under `--dev` via the `cycle` harness.
- **Rationale**: a sixth engine for one scenario type contradicts the whole premise; phases already express "spawn → engage → verify" as data.
- **Alternatives**: keep as a loop mode (rejected — modes-as-subsets defect); drop entirely (rejected — raid smoke is valuable dev tooling).

## R12 — Decide cadence (added post-analyze)

- **Decision**: `decide.select.cadence_polls` is pack-tunable (default 1); a lagging endpoint causes skipped decisions, never queued ones.
- **Rationale**: ADR open risk — per-poll select latency must not accumulate backlog.
- **Alternatives**: queue-and-drain (rejected — stale picks act on old world state); block the poll (rejected — decide never stalls the loop).
