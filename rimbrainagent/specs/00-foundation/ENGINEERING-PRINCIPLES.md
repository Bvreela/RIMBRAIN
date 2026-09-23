# Engineering principles

**Status:** READY  
**Applies to:** every component and work package

## P1. Deterministic before probabilistic

Use code when legality, arithmetic, freshness, ordering, idempotency, or a hard invariant determines the answer. A model is justified only for unresolved tradeoffs or novel strategic synthesis.

## P2. Authority decreases as uncertainty increases

Models may propose broader ideas but receive narrower execution authority. The planner can propose plans; the selector can choose one offered option; only deterministic local code can dispatch a write.

## P3. One writer, many readers

All game mutations pass through one serialized dispatcher. Observation, planning, selection, review, dashboard, and export services are read-only with respect to the game.

## P4. Safety is structural

Emergency paths have no provider dependency. Model-bearing objects do not hold bridge mutation handles. Policy packs contain no auto-executed code. Prompts are not relied on as authorization boundaries.

## P5. Human-readable does not mean loosely parsed

YAML and Markdown optimize review, but execution consumes canonical schema-validated objects. Unknown execution fields, ambiguous row matches, cycles, unbound IDs, and missing freshness constraints are load failures.

## P6. Evidence is immutable; conclusions are revisable

Observations, decisions, responses, actions, and outcomes append records. Lessons and policy claims may change status while preserving support, counterevidence, scope, and lineage.

## P7. Runtime state is not policy

Per-episode plans, pending actions, locks, and cursors belong to runtime state. Reusable matrices, workflows, prompts, parameters, and reviewed lessons belong to RimBrain packs. Exports are projections of evidence, not alternate state stores.

## P8. Qualification is granular

A model is not globally “trusted.” Selector authority is qualified per matrix row, model revision, renderer/prompt revision, and context family. Drift or calibration failure demotes only the affected tuple.

## P9. Compatibility is explicit

Every interface and artifact declares versions. Consumers reject unknown newer schemas. Releases pin exact submodule commits and pack/model revisions. Migrations occur between scored series, not during them.

## P10. Protocol-first modularity

Split a repository only when the boundary has an independent release cadence, stable public contract, external consumers, and independent tests. Keep internal packages together until evidence justifies another submodule.

## P11. Replay before live authority

Provider behavior, policy patches, action templates, and migration changes first pass offline fixtures and contract tests, then shadow mode, then bounded live trials.

## P12. Survival without stalling

Integrity and life outrank maintenance, progress, and efficiency, but every episode declares progress floors and pause accounting. A controller cannot win by doing nothing safely.

## P13. Fail closed on critical uncertainty

Unknown or stale safety data causes observation or safe pause. Noncritical missing data may use an explicitly declared fallback. The distinction is part of each contract.

## P14. Build for diagnosis

Every route, exclusion, fallback, lock, validation rejection, write, and verifier result emits a causal event. A reviewer must reconstruct behavior without source-level debugging or hidden model reasoning.

## P15. Preserve a migration escape hatch

Upstream legacy play remains an opt-in recovery/baseline mode while framework mode matures. It cannot share write authority with framework mode and cannot qualify as a scored framework run.
