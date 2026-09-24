# ADR-019: Unified Phase Engine — one pipeline for the whole colony lifecycle

**Status**: Proposed
**Date**: 2026-09-24
**Feature**: `specs/017-unified-phase-engine/`
**Builds on**: ADR-015 (brain policy boundary), ADR-016 (transparency/catalog), ADR-017 (pack classes), ADR-018 (live pack mutation)

## Context

The runtime grew in parallel rather than in layers:

- **Six loop entry points** (`run_loop`, `run_start`, `run_combat`, `run_cycle`, `run_improve`, `run_plan`) each re-implement the same poll skeleton (observe → reconcile → reflex → rules → act → views). Only `run_start` carries the full machinery (verified goals, vitals, brain lifecycle, mutation triggers); every other mode is a strictly weaker brain. The `--mode` flag selects *which subset of the system runs*.
- **Three propose→gate→candidate→promote pipelines**: `improve.py` (009), `mutate.py` (016), `planloop.py` (005) — three candidate formats, three gates (`review.py`, `audit_policy`, `mutate.gate`), three promotion paths. Feature 016 already converges ad hoc: `mutate.reflect` calls `improve.diagnose` and re-vocabularizes through `packmut.compile_legacy`.
- **Two predicate dialects**: `emergency:` conditions evaluated by a private evaluator in `dispatch.py` vs. the `policy.check` language used by `universal.rules`, `govern.goals`, and phases. Same concept; only one dialect can express non-trivial logic.
- **Three observation shapes**: `observe_start`, `game.status`+`enrich`, `vitals.sample`. The planner sees state the policy engine never sees and vice versa.
- **Pack sprawl**: `decision_map` exists only to satisfy a stale schema; `jobs`, `cycle`, `emergency`, `universal`, `start.*`, `govern.*` namespaces each follow different conventions; `goal_options` is inert — nothing promotes it.
- **Four run-state dicts, ~ten state files**, each owned by a different subsystem.
- **The decision tiers are wired but unreached**: `rimbrain.select` (Laya) answers a vestigial fixed 5-choice question in the legacy loop only; `rimbrain.plan` (planner) runs only as a standalone command. The colony's long-horizon behavior is a static priority list.

The user directive: one unified, phase-driven loop — plan → execute → improve → plan — with the pack defining phases (init being prescriptive), Laya executing from bounded action lists, the planner strategizing on cadence, and one mutation pipeline that can evolve every pack surface.

## Decision

1. **One pipeline, one loop.** A single run mode executes a fixed stage order — observe → reflex → decide → act → verify → reflect — for the entire colony lifecycle. `run` is the only loop mode; `cycle` stays an outer dev harness; `plan`/`reflect` become standalone *stage* entry points for debugging, not loops.

2. **Phases are pack data.** `pack.phases[]` is the lifecycle: `init` is prescriptive (today's `start.phases` steps + exit contract, verbatim semantics — deterministic structural steps, verified effects). Subsequent phases are planner-authored or pack-declared. Standing goals (today's `govern.goals`) evaluate every poll regardless of phase. Legacy namespaces migrate in memory at load — old packs keep working.

3. **Decide stage: Laya executes from bounded lists.** Each poll compiles ≤20 candidates — colony-scope goal ops + pawn-scope job options — ranked by pack priority expressions, rendered as one batched select request. Laya picks an offered option ID; the engine validates membership and dispatches through the single writer. Invalid/absent answers and endpoint outage resolve to a pack-declared deterministic fallback. Inside `init`, structural steps remain deterministic; pawn-level job choices still go through the select tier. Every decision is logged (offered set, pick, applied choice, inputs) — auditability replaces live reproducibility.

4. **Plan stage: the strategist runs in the loop.** `rimbrain.plan` fires on a pack-tunable cadence (~150s), on phase boundaries, and on declared major events. Accepted plans reorder action-list priorities, activate goals, and promote `goal_options` strategies into active goals/phases. Review gate stays decisive; planner outage leaves the last plan in force — the loop never blocks on it.

5. **Reflect stage: one mutation pipeline.** `improve` + `mutate` + `planloop` promotion machinery merge into a single path: digest → proposal (model or rules-only) → compile to `packmut` ops → one gate (schema, sealed inventory, class, budget) → candidate → boundary-only promotion. The path whitelist covers `phases`, `action_list`, `decide`, `reflexes`, `rules` — every pack surface is evolvable through the same audited route. `improve.diagnose`/metrics survive as evidence functions.

6. **Determinism narrows to where it is real.** Sim and CI are fully deterministic (no endpoint calls, repeatable event streams). Live runs are always model-assisted; reproducibility is dropped in favor of logged decision records (Constitution VII covers reconstruction). The constitution needs **no amendment**: Principle I already licenses models for unresolved tradeoffs (choosing among enumerated options is exactly that), Principle II's bounded-authority shape is preserved, and Principle V's "immutable during scored runs" constrains *policy* (pack), not choices — drift freeze and boundary promotion already enforce it.

7. **Selector authority is staged** per Principle VI: the new action-list matrix starts in shadow mode (Laya picks logged, deterministic fallback executes; divergence measured), then bounded live trial, then live authority — qualified per model/prompt/context tuple.

8. **Consolidation, not wrappers.** `startmode.py` engine, `loop.py::_live_decider`, `universal.py`, `dispatch.py::_condition/_op_holds`, and duplicate gate/promote code are deleted. Run-local state consolidates into one `RunState`. The flag matrix gets an explicit interaction table; undefined combinations fail closed.

## Alternatives considered

- **Keep start mode, hand off to planloop at `start.completed`** — leaves two engines, the mutation-surface split, and modes-as-subsets. Rejected.
- **Laya over raw RPC methods** — violates bounded model authority (Principle II). Rejected.
- **Planner-per-poll instead of Laya** — wrong tier: latency and cost per poll are prohibitive; the 150s strategist + per-poll tactician split matches the roles each model was provisioned for.
- **Deterministic live runs (rejected by user)** — the game is nondeterministic; choice determinism live was unachievable. Auditability via logged decisions is the honest guarantee.
- **Deprecate rather than delete** — wrapper shims preserve the parallel-structure defect. Compat lives at the *pack schema* layer (in-memory migration), not the code layer.

## Consequences

- `pack.yaml` becomes the single expression of the whole colony lifecycle — meta, capabilities, reflexes, rules, senses, phases, standing goals, options, decide, mutate, metrics. Schema v1; v0 packs migrate in memory at load.
- New modules: `phase.py` (engine), `select.py` (action-list compiler + Laya plumbing), `observe.py` (canonical observation), `evolve.py` (unified reflect), `runstate.py` (state owner). Net deletion overall.
- `rimbrain.select` becomes load-bearing in fair runs → shadow-mode qualification precedes live authority (Principle VI).
- ~all `test_startmode.py` coverage ports to `test_phase.py`; new tests for the ≤20 bound, fallback paths, shadow mode, and single-pipeline round-trips.
- `rimbrain.py` launch surface simplifies to `run`; `--mode start` is a one-release deprecated alias.
- The planner enters the fair-run hot path: cadence, timeout, and last-plan-standing semantics are spec requirements, not afterthoughts.

## Open risks

- **Mutation attribution noise** (accepted): game RNG + model RNG means promote/revert heuristics can misfire; mitigation is cheap re-proposal, revisit if thrash observed.
- **Select latency per poll**: one batched request per poll mitigates; if Laya lag exceeds poll cadence, decide cadence becomes pack-tunable.
- **Planner cost**: 150s cadence on a remote endpoint is a real spend; `decide.plan.cadence_s` is pack-tunable and stage entry can be disabled.
