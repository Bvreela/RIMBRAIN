# System architecture

**Status:** READY  
**Requirements:** UR-CTL-*, UR-RUN-*, UR-SUR-*, UR-MOD-*, UR-BRN-*, UR-DAT-*, UR-EXP-*

## 1. Context

RimBrainAgent controls RimWorld through RimBridge while delegating high-frequency deterministic labor/reflex behavior to Steward. The Python runtime owns planning state, attention, model routing, bounded workflow dispatch, verification, and evidence. RimBrain packs provide immutable reusable policy. Lab consumes offline artifacts. Dashboard consumes a read model and sends audited operator commands.

```text
Human operator ───────────────┐
                              ▼
Dashboard ── audited command API ──► Runtime
   ▲                              /    │
   │ read model/events           /     │ typed intents
   └────────────────────────────┘      ▼
RimBrain pack ── read-only ──► Runtime dispatcher ──► RimBridge ──► RimWorld
Contracts ────────────────► all components                 ▲
                                    │ desired policy       │ hooks/RPC
                                    └──────────────────► Steward

Runtime canonical events ──► Lab export/replay/benchmark
RimBrain proposals/results ◄────────────── Lab promotion evidence
```

## 2. Runtime logical services

The runtime component contains one process and one event loop at first. Logical services remain independently testable.

### 2.1 Composition root

Creates role-scoped dependencies, loads configuration and pinned manifests, selects `legacy` or `framework` controller, starts health/read APIs, and performs startup compatibility checks. It is the only layer aware of concrete adapters.

### 2.2 Bridge gateway

Wraps RimBridge reads and presents mutation capability only to the dispatcher. It discovers methods but framework code consumes an allowlisted capability catalog, not arbitrary generated tools. It stamps calls/results with intent and correlation metadata locally even when the bridge protocol lacks those fields.

### 2.3 Reconciler

Ingests bridge events, refreshes due observations, resolves uncertain actions, computes feature freshness, and emits canonical events. On startup it owns reconcile-only mode.

### 2.4 Feature, vitals, and runway engine

Pure deterministic functions convert observations into typed features, per-pawn vitals/TTC estimates, per-site runways, trend slopes, known uncertainty, and posture candidates. Formula revisions are contract-visible.

### 2.5 Goal/task store

Owns objective, active plan, goals, tasks, workflow cursors, locks, pending actions, planner obligations, and persisted pause/ownership state. State transitions are validated and event-sourced enough to audit, while compact snapshots accelerate restart.

### 2.6 Attention scheduler

Applies strict precedence: operator hold, deterministic life emergency, critical deadline, overdue verification/review, then ordinary tie-break scoring. It selects one bounded item and records competitors/reasoning terms.

### 2.7 Candidate and policy engine

Loads a frozen RimBrain snapshot, matches exactly one matrix row, evaluates feature requirements and hard constraints, binds offered options to real targets, computes declared costs/risks/effects, and provides deterministic score/fallback.

### 2.8 Model router

Uses role-specific provider protocols. Tier-1 qualification is read from the active policy/calibration snapshot. The router never sees bridge write capabilities. It emits a validated choice or planning proposal and records every fallback/escalation reason.

### 2.9 Dispatcher

The only framework writer. A single queue consumer rechecks current revision, freshness, target binding, lock ownership, posture permissions, action allowlist, idempotency, stop condition, write budget, and verification schedule. It dispatches desired states, not incremental repeated commands.

### 2.10 Verifier

Runs fresh observation predicates and returns `pass`, `fail`, or `unknown`. It alone transitions tasks to success. It closes outcome windows, emits prediction error, releases locks, triggers circuit breakers, and creates failure/post-mortem obligations.

### 2.11 Canonical event store

Appends schema-versioned causal events durably. It provides recovery replay and projections to the dashboard/exporter. The in-memory bus is a projection, not authority.

### 2.12 Watchdog

An independent heartbeat monitor can only request safe pause and alert. It has no gameplay dispatch permission. Upstream’s source-patching watchdog remains legacy/developer tooling and is disabled during scored framework episodes.

## 3. Control tiers

### Tier 0

Steward standing orders, deterministic emergency handlers, validators, arithmetic, workflow cursors, observation, verification, rules fallback, and the dispatcher. Tier 0 is always available.

### Tier 1

Laya, Jev, or another closed-choice adapter selects one offered option or abstains. Authority is per row/model/renderer qualification. Optional Tier 1.5 judge follows the same contract.

### Tier 2

A capable planner/reviewer produces plans, repairs, critiques, or policy proposals on declared triggers. It cannot dispatch or activate policy.

## 4. End-to-end turn

1. Event/deadline/heartbeat wakes reconciliation.
2. Reconciler persists source events and refreshes due observations.
3. Feature engine updates vitals, runways, trends, and posture.
4. Verifier closes due action outcome windows.
5. Scheduler selects one attention item.
6. Candidate engine binds and validates options.
7. Router chooses Tier 0, qualified Tier 1, or a Tier-2 obligation.
8. Result validation checks correlation, deadline, revision, schema, and offered IDs.
9. Dispatcher either writes one bounded desired-state intent or records no-op/wait/block.
10. Verification is scheduled; evidence is flushed; next wake is computed.

## 5. Concurrency model

- One `asyncio` loop coordinates runtime services.
- One dispatcher task serializes writes.
- Provider calls and read-only bridge requests may run concurrently with deadlines.
- Policy snapshots are immutable objects swapped only at permitted boundaries.
- State mutation occurs through store commands, not shared dictionaries.
- Dashboard requests enqueue audited commands; they do not call services directly.
- Background export/replay reads closed episode files or consistent snapshots.

## 6. Modes

- `legacy`: upstream free-form behavior for baseline/recovery; existing risks explicitly accepted.
- `shadow`: framework computes and logs but dispatches zero game writes.
- `supervised`: framework proposes intents requiring configured approvals.
- `autonomous`: dispatcher executes allowed classes.
- `experiment`: dev RimBrain pack; proposals and declared bounded exploration permitted; unranked.
- `ranked`: frozen clean revisions; no mutation, reload, hidden intervention, or unqualified model route.

Controller mode and evaluation mode are orthogonal but validated as allowed combinations.

## 7. Failure policy

| Failure | Response |
|---|---|
| Stale/missing critical feature | Pause/observe |
| Selector unavailable/invalid/late | Matrix fallback |
| Planner unavailable | Continue valid plan or safe pause per autonomy |
| Bridge timeout after write | Mark uncertain; verify effect before retry |
| Repeated action failure | Open circuit and escalate/block |
| Event-store append failure | Stop acknowledging turns; safe pause |
| Pack/schema/hash mismatch | Refuse framework startup |
| Heartbeat loss | External safe pause + alert |
| Drift/calibration breach | Demote affected selector row to rules |
| Contract violation after activation | Automatic pack yank/rollback at safe boundary |

## 8. Architectural completion condition

The architecture is proven when the holistic first-week vertical slice runs through this service graph, all writes are dispatcher-attributed, restart reconciles an uncertain action, qualified and unqualified rows route differently as specified, and an external lab consumer reconstructs the full trajectory from exported records.
