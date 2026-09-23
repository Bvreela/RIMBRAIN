# Implementation plan and work packages

**Status:** READY FOR REVIEW, NOT APPROVAL TO CODE  
**Method:** Each work package is independently reviewable and has entry/exit gates.

## Global entry gate

Before any implementation:

- component remotes/ownership/license decisions exist;
- baseline toolchains are installed;
- upstream Python/RimBridge/Steward suites pass;
- contracts tooling ADR is accepted;
- exact evaluation machine/time budget is recorded;
- autonomy/high-impact human-approval policy is decided.

## Phase 0 — Repository and baseline

### WP-000 Component bootstrap

Create component repositories/submodules, licenses, CI shells, dependency rules, CODEOWNERS/governance, and release profile skeleton. No behavior change.

**Exit:** recursive clean checkout; every component can run a no-op validation job; exact upstream revisions recorded.

### WP-001 Upstream characterization

Capture method inventory, representative state/events, existing dashboard/API, LLM captures, Steward RPC/events, test/build outputs, game-day wall timing, and legacy run manifest.

**Exit:** immutable baseline bundle and known-failure register.

### WP-002 Contract foundation

Implement common IDs/revisions/freshness/errors, event envelope, core runtime object schemas, fixture harness, and compatibility checks.

**Exit:** valid/invalid corpus passes in initial Python consumer; canonical hashes stable.

## Phase 1 — Durable shadow spine

### WP-100 Controller boundary

Split composition into legacy/framework protocols without changing legacy outcomes.

**Requirements:** UR-CTL-008, UR-ARC-001/004.  
**Exit:** legacy tests/CLI parity; framework stub can start with zero write capability.

### WP-101 Canonical event and state stores

Add durable JSONL, atomic snapshots, migrations, recovery markers, and bus projection.

**Requirements:** UR-RUN-004, UR-DAT-001..003/007.  
**Exit:** crash/torn-tail/Windows replacement fixtures pass.

### WP-102 Objective/task/workflow/lock model

Implement state machines, all-or-nothing expiring locks, verifier-only success invariant, and persisted cursors.

**Requirements:** UR-RUN-001..004.  
**Exit:** state/graph/property tests and forced restart trace pass.

### WP-103 Observation/features/survival shadow

Extract observation collectors; add freshness, vitals/TTC scaffolding, runway, posture/hysteresis, attention precedence, heartbeat.

**Requirements:** UR-SUR-001..006, UR-RUN-005/007.  
**Exit:** human-labeled save fixtures agree within declared tolerances; dead-man test pauses.

### WP-104 Shadow controller

Run reconcile/attend/route/no-dispatch/evidence beside legacy across five sessions.

**Exit:** no framework writes; complete objective-to-decision trace; no crashes/gaps outside declared bridge retention.

## Phase 2 — Single writer and deterministic survival

### WP-200 Gateway separation

Create read and mutation gateways and static forbidden-import/direct-call tests.

**Requirements:** UR-CTL-001/002/008.  
**Exit:** framework cannot construct raw write tools; audit fixture proves isolation.

### WP-201 Dispatcher/action templates

Implement queue, validation chain, desired-state/idempotency, pending journal, uncertainty, bounded results.

**Requirements:** UR-CTL-003/004/006, UR-RUN-003.  
**Exit:** duplicate/timeout/effect-present/crash fixtures pass.

### WP-202 Verification and failure handling

Implement pass/fail/unknown, windows, circuit breakers, failure taxonomy, prediction error.

**Requirements:** UR-RUN-002/006, UR-BRN-010.  
**Exit:** no task succeeds outside verifier; repeated failures stop writes.

### WP-203 Food/shelter/emergency vertical slice

Add deterministic candidates/actions/verifiers; integrate Steward reflexes; enforce initial hard invariants.

**Exit:** live three-day landing, zero illegal/unowned writes, all effects verified or honestly failed.

## Phase 3 — RimBrain and model roles

### WP-300 Pack loader/core-survival pack

Implement restricted parsing, graph validation, immutable snapshots, proposal separation; seed first-week policy.

**Requirements:** UR-BRN-001..009.  
**Exit:** tamper/bad-ref/overlap/cycle tests; human edit→validate→snapshot flow.

### WP-301 Provider protocols/capability tests

Add stubs, OpenAI planner, Laya and optional Jev selector adapters, cancellation/deadlines/identity.

**Requirements:** UR-MOD-001/003/007/008.  
**Exit:** adapter swap, malformed/late/abstain/injection fixtures pass without writes.

### WP-302 Matrix routing/qualification

Implement Tier 0 precedence, rules baseline, per-row qualification, fallback, calibration snapshot consumption.

**Requirements:** UR-MOD-002..005.  
**Exit:** mixed qualified/unqualified pack routes exactly as fixtures declare.

### WP-303 Planner/critique/validation

Implement trigger obligations, packet renderer, proposal validation, one repair, pre-mortem/critique.

**Requirements:** UR-MOD-006/009/010.  
**Exit:** valid first-week plan; invalid/novel/stale proposals rejected or repaired within budget.

### WP-304 Holistic first week

Integrate landing, labor, food, shelter, health, logistics, basic power/research/defense.

**Exit:** matched stable week with fewer strong calls than legacy and no safety regression; framework becomes default candidate.

## Phase 4 — Stability and maintenance

### WP-400 Crisis/stability systems

Complete postures, spiral, hazards, post-mortems, churn/drift, progress/pause accounting.

### WP-401 Domain expansion

Add power/temp, mood, production/equipment, research capability graph, logistics.

**Exit:** 20–30 day matched trials hold enabled gates/progress floors.

### WP-402 Steward extraction/protocol

Extract standalone mod, add capabilities/correlation/idempotency compatibly.

**Exit:** legacy and framework clients pass same RPC corpus; duplicate-intent fixtures pass.

## Phase 5 — External surfaces

### WP-500 Lab export

Implement canonical verification, profiles, redaction, trajectories, data card, checksums, optional Parquet.

**Requirements:** UR-EXP-001..009.  
**Exit:** independent consumer verifies/reconstructs episode; leakage/privacy corpus passes.

### WP-501 Replay and pack diff

Decision/plan/failure replay, fixture ratchet, semantic diff.

**Exit:** contributor change demonstrated and bad change rejected offline.

### WP-502 Dashboard extraction

Implement public runtime APIs and independent UI with survival/plan/attention/decision/action views.

**Exit:** no runtime imports/direct bridge access; human review checklist passes.

## Phase 6 — Broader game and learning

### WP-600 Defense/recovery/world/endgame

Add matched incident workflows, trade/people/animals, caravans/site runway, quests, one victory path.

### WP-601 Calibration/evaluation

Matched trial manifests, survival curves, row calibration, drift/demotion, evaluation reports.

### WP-602 Proposal/promotion pipeline

Error clusters, reviewer proposals, human gates, signed release, monitored cohort, rollback.

**Exit:** one real failure patch accepted/rejected correctly; deliberate bad patch fails; regression rolls back.

## Phase 7 — Optional evidence-earned features

Judge tier, bounded numeric autopromotion, community benchmark index, general spatial planner. Each needs a separate mini-spec, simpler baseline comparison, and kill criterion.

## Definition of work-package done

- requirements and contracts unchanged or approved by ADR;
- tests written and passing at declared ladder levels;
- no unresolved critical/high risks;
- docs/examples/migrations updated;
- traceability links evidence;
- security/privacy review complete where applicable;
- rollback exercised;
- measurable exit demonstrated, not asserted.
