# Test and evaluation strategy

**Status:** READY

## 1. Principles

- Test contracts before components.
- Test deterministic pure logic before game integration.
- Replay before shadow; shadow before writes; bounded writes before holistic runs.
- Treat failures, rejected decisions, and unknown outcomes as first-class cases.
- Group experimental evidence by start-save family, not decision count.
- Do not waive exits because evaluation is expensive; narrow scope instead.

## 2. Test layers

### L0 Static/spec

Schema lint, Markdown links, requirement IDs, ADR status, dependency/import rules, secret/path scans, license/notice checks, submodule cleanliness.

### L1 Unit/property

Pure state transitions, formulas, canonicalization, matrix matching, scoring, hysteresis, locks, redaction, metrics, idempotency. Property tests target lifecycle invariants and malformed boundaries.

### L2 Consumer/provider contract

Shared golden corpus across Python, C#, and dashboard types. Provider capability tests use no game writes. RimBridge/Steward stubs verify exact envelope/failure behavior.

### L3 Replay

Recorded decisions/plans/failures/events run through pack/router/verifier. Deterministic outputs must reproduce. Model comparisons are isolated and labeled nondeterministic/config-pinned.

### L4 Fault integration

Temporary filesystem and fake bridge/provider inject torn appends, replace denial, event gaps, timeouts, late responses, duplicate effects, crashes, stale revisions, capability drift.

### L5 Shadow game

Framework reads a real game and emits traces with zero writes. Compare vitals/runways/features against human labels and legacy observations.

### L6 Bounded live

One domain/action class with strict limits and operator readiness. Demonstrate desired-state writes, verification, restart, and emergency preemption.

### L7 Matched scenarios

Landing/maintenance/hazard/combat/world scenarios on paired save families and declared arms.

### L8 Holistic pilots

Rare 20–30 and 60-day episodes after lower layers pass. No debugging by silently reloading scored runs.

### L9 Held-out

Locked final evaluation inaccessible to planning/learning until retirement.

## 3. Mandatory engineering fixtures

- already-satisfied goal;
- stale/missing/contradictory observation;
- cycle/orphan/reference errors;
- lock conflict and expiry;
- sole critical-role contention;
- action acknowledged without effect;
- timeout with effect present;
- duplicate bill/blueprint/designation/target;
- emergency interrupt during provider call;
- unoffered/malformed/no-confidence/late/abstaining response;
- provider swap with in-flight request;
- game-text prompt injection;
- inaccessible food and season-invalid crop;
- blueprint placed but room unusable;
- worker lost mid-phase;
- power/freezer/temperature cascade;
- individual crisis hidden by average;
- capability researched but not implemented;
- wealth growth without defense;
- unsafe caravan home coverage;
- raid aftermath and recovery;
- lesson context mismatch/counterevidence;
- held-out/synthetic evidence attempting promotion;
- crash with pending action/locks;
- torn JSONL and Windows atomic replace failure;
- pack hash/path/signature attack;
- export redaction/reference/split leakage.

## 4. Experimental arms

- A: frozen upstream legacy free-form.
- B: framework rules-only.
- C: B plus fixed qualified Tier-1 selector.
- D: C plus sparse planner.
- E: D plus frozen improved RimBrain pack.

Compare one change at a time. A lower-cost arm that matches outcomes can be preferred. Selector and planner features remain optional if bets fail.

## 5. Metrics

Strict order:

1. integrity: contract violations, illegal/unowned writes, emergency stalls, forced reloads, interventions;
2. life: deaths by class, survival curves, near-miss time/rate, TTC dispatch margin;
3. maintenance: per-pawn and runway violations;
4. progress: verified capabilities/milestones/progress-floor failures;
5. efficiency: model calls/cost/latency, pause ratio, TPS, game-days/wall-hour, write/duplicate/fallback rates;
6. framework: deadline misses, overdue attention, blocked time, churn, repeated failures, calibration/drift, trace completeness.

Wealth is descriptive, not an optimization target.

## 6. Environment control

Manifest game/DLC/mod/load order, full starting save hash, scenario/storyteller/difficulty/tile, autosave policy, all component/config/pack/model revisions, speed/pause policy, action/model budgets, machine profile, manual/assisted actions, and game build.

## 7. Statistical honesty

Declare metrics, sample size/stopping, exclusion, and kill criteria before runs. Use matched starts where possible, at least three matched replicates for acted-on comparisons unless sequential design says otherwise, report distributions/intervals, and never count decisions within one colony as independent episodes.

## 8. CI split

- Per component PR: static, unit, contract, local fixtures.
- RimBrain PR: schema/DAG/matrix/prompt/fixture replay and semantic diff.
- Superproject integration: recursive compatibility and cross-component corpus.
- Scheduled hardware/game lane: shadow/bounded matched scenarios.
- Release: complete declared ladder through the release phase, clean pinned profile, export verification.

## 9. Test evidence

Results are machine-readable artifacts with test ID, requirement IDs, component/profile hashes, fixture/save hashes, timestamps, outcomes, logs, and limitations. Dashboard summaries never replace raw result envelopes.
