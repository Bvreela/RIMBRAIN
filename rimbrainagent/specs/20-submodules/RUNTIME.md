# Runtime submodule build specification

**Status:** READY  
**Future path:** `components/runtime`  
**Future remote:** `rimbrainagent-runtime`  
**Base:** fork/extraction from `zorrobyte/rimagent` at `85cb050`

## 1. Purpose

The runtime is the live Python orchestrator. It preserves upstream legacy mode while adding the deterministic-first framework controller, durable state/evidence, model routing, single dispatcher, and public read/control APIs.

## 2. Owned responsibilities

- CLI, composition root, configuration, compatibility checks.
- RimBridge/Steward gateways and capability discovery.
- Reconciliation, features, vitals, runway, posture, attention.
- Objective/plan/goal/task/workflow state and locks.
- Candidate generation, matrix evaluation, routing, provider adapters.
- Single dispatcher, action templates, verification, failure/post-mortem creation.
- Canonical event/state stores and dashboard read model.
- Legacy controller compatibility.

## 3. Explicit exclusions

- RimBrain pack content and promotion evidence.
- RimBridge C# implementation.
- Steward C# implementation.
- Offline replay/benchmark/export transformations.
- Dashboard presentation code.
- Training/fine-tuning.

## 4. Planned package layout

```text
src/rimbrainagent/
  cli/
  app/
    bootstrap.py
    lifecycle.py
    modes.py
  legacy/                    # adapted upstream runner/loop/registry/reflection
  contracts/                 # dependency wrappers, not copied schemas
  bridge/
    client.py
    capabilities.py
    read_gateway.py
    mutation_gateway.py
    steward_gateway.py
  store/
    atomic.py
    event_store.py
    state_store.py
    migrations.py
    recovery.py
  framework/
    models.py
    reconcile.py
    scheduler.py
    locks.py
    lifecycle.py
    heartbeat.py
  survival/
    vitals.py
    ttc.py
    runway.py
    posture.py
    invariants.py
    spiral.py
    postmortem.py
  policy/
    brain_store.py
    predicates.py
    features.py
    matrices.py
    candidates.py
    routing.py
    qualification.py
  providers/
    protocols.py
    registry.py
    openai_chat.py
    laya.py
    jev.py
    stubs.py
    capability_tests.py
  planning/
    requests.py
    validation.py
    service.py
    critique.py
  execution/
    intents.py
    templates.py
    dispatcher.py
    verification.py
    failures.py
    circuit_breakers.py
  domains/
    bootstrap/
    food/
    shelter/
    health/
    logistics/
    ... phase-gated
  api/
    read.py
    control.py
    events.py
  observability/
    projections.py
    metrics.py
    redaction.py
```

## 5. Upstream modification map

- `cli.py`: add controller/mode, pack, profile, verify, and recovery commands; retain legacy commands.
- `config.py`: replace shallow merge with typed layered config and secret references; preserve legacy keys through migration.
- `runner.py`: become a legacy controller plus thin app lifecycle integration. New framework runner must not call `think`.
- `loop.py`: retain free-form legacy loop; extract read-only observation collectors into gateway/feature code.
- `bridge.py`: split reads from mutations; only dispatcher receives mutation gateway.
- `context.py`: legacy-only; framework uses capability-scoped dependencies.
- `registry.py`: legacy dynamic registry remains; framework uses explicit capability/action registries with closed schemas.
- `llm.py`: legacy adapter remains; framework provider registry owns role-specific clients, cancellation, deadlines, and identity.
- `bus.py`: convert to projection over canonical events; remove file-log authority.
- `roles.py`: parallel writers unavailable in framework. Optional specialists are read-only advisers whose output is never directly dispatched.
- `reflect.py`: framework emits plan repair or pack proposal; no hot edit/commit.
- `memory.py`/`braingit.py`: legacy only; framework stores structured state and proposals.
- `watchers.py`: classify legacy; framework alert watchers cannot mutate. Deterministic mutation belongs in Steward/action templates.
- `dashboard/app.py`: replace with API compatibility layer until dashboard extraction completes.
- `export_sft.py`: retain as legacy; delegate canonical export to Lab CLI/API.
- `paths.py`: separate install, config, pack, state, runs, cache, and export roots; no import-time directory side effects.

## 6. Controller boundary

Define a controller protocol with lifecycle operations: start/adopt, reconcile, next obligation, handle operator command, shutdown, and episode close. `LegacyController` wraps upstream behavior. `FrameworkController` owns the new spine. Composition selects one; no shared write path exists.

## 7. Dispatcher design

- One `asyncio.Queue[ActionIntent]` and one consumer.
- Action template registry is explicit and code-reviewed.
- Validation order: mode/hold → intent/revisions → freshness → posture/invariants → target binding → locks → action bounds → idempotency query → dispatch.
- Result persisted before scheduling verifier.
- Timeout produces `uncertain`, never immediate retry.
- Every mutation gateway call requires a dispatcher-only capability token/object not constructible by provider/domain code.
- Pack loading enforces `class` (UR-BRN-018): fair/ranked runs refuse a `class: dev` pack — or any pack declaring `dev.*` methods — at load (`pack.not_fair`), so debug tooling can never enter a scored registry.
- Mode completion is a handoff: bounded callers stop at the exit contract; held runs continue into the pack's `govern` standing goals on the same ledger machinery (UR-RUN-009).

## 8. Provider design

Protocols: `Selector.select`, `Planner.plan/repair`, `Reviewer.review`, optional `Judge.select`. Adapters implement transport only. Renderer and semantic validation live in runtime policy/planning. Each call records endpoint/model/config/prompt/packet hashes, deadline, usage, latency, and rejection reason. Secrets remain outside records.

## 9. Domain plugin contract

A domain registers pure predicates/features, candidate generators, task/workflow definitions, action templates, verifiers, known failure classes, and fixtures. It does not import concrete providers, dashboard, lab, or raw mutation client. Domain activation is config/pack-declared and phase-gated.

## 10. Persistence and recovery

Use append-only event records plus atomic snapshots. Acknowledged records are flushed. Recovery truncates only an invalid final JSONL record and emits a recovery event. Startup is reconcile-only until pending effects, game identity, pack hash, and pause/ownership state resolve.

## 11. Legacy compatibility

- Legacy config maps to `controller.mode: legacy` automatically during transition.
- Legacy `brain/`, captures, scores, dashboard endpoints, and commands remain usable.
- Framework mode ignores executable `brain/tools` and `brain/watchers`.
- Scored framework manifests label any legacy fallback as invalid/assisted.
- Removal of legacy mode requires a later ADR and benchmark evidence.

## 12. Tests

- Unit: state machines, scheduling precedence, locks, hysteresis, TTC/runway formulas, matrix matching, router, dispatcher validation, verifiers, migrations.
- Contract: providers, RimBridge/Steward gateway, dashboard API, event/export producer.
- Property: idempotency, no success without verifier, no write without dispatcher, stable tie-break.
- Fault injection: crash mid-append/write, bridge timeout with effect, stale provider result, event gaps, pack mismatch.
- Shadow/live: first-week fixtures and matched saves.
- Static: forbidden imports/direct mutation calls.

## 13. Delivery sequence

- **R0:** fork bootstrap, legacy green, composition boundary.
- **R1:** contracts, durable store, canonical events, shadow controller.
- **R2:** dispatcher/read-mutation split, deterministic food/shelter/emergency.
- **R3:** provider roles, matrix routing, planner, first-week slice.
- **R4:** survival/stability systems and domain expansion.
- **R5:** public API and extracted dashboard/lab integration.
- **R6:** learning proposal integration and ranked mode.

## 14. Acceptance

- Existing legacy tests pass unchanged or with documented compatibility migrations.
- Framework process can be constructed without any general tool registry or unrestricted bridge handle.
- Audit finds zero writes outside dispatcher.
- Forced restart reconciles pending effects before new dispatch.
- Unqualified selector rows route rules; qualified rows can route configured selector; both preserve fallback.
- First-week shadow/live acceptance and export lineage pass.
