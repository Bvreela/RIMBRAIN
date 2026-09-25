# Contracts submodule build specification

**Status:** READY  
**Future path:** `components/contracts`  
**Future remote:** `rimbrainagent-contracts`  
**Owns:** schemas, identifiers, compatibility rules, canonical examples, generated binding inputs

## 1. Purpose

Contracts is the dependency root shared by Python runtime, C# Steward, dashboard, lab, RimBrain validation, and external consumers. It specifies wire/data semantics without importing implementation code.

## 2. Scope

- JSON Schemas for canonical events, observations, features, plans, goals, tasks, locks, intents, action results, verifications, model requests/results, post-mortems, pack manifests, export manifests, fixtures, and release profiles.
- Stable ID and revision syntax.
- Event type registry and payload discriminator rules.
- Compatibility and migration policy.
- Canonical valid/invalid examples.
- Protocol descriptions for runtime HTTP/SSE read/control surfaces.
- Optional generation configuration for Python/C#/TypeScript bindings after schema stability.

## 3. Non-goals

- Runtime validation orchestration.
- Provider transport clients.
- Game-specific policy content.
- Executable predicates/actions.
- Database/index definitions.
- Authentication implementation.

## 4. Planned layout

```text
contracts/
  schemas/
    common/
    runtime/
    policy/
    providers/
    events/
    export/
    evaluation/
  examples/
    valid/
    invalid/
  protocols/
    runtime-read-api.md
    runtime-control-api.md
    rimbridge-capabilities.md
    steward-rpc.md
  compatibility/
    VERSIONING.md
    MIGRATIONS.md
  generators/
  tests/
  pyproject.toml-or-equivalent
  LICENSE
```

No generator is selected until consumers prove a need; schemas remain authoritative.

## 5. Core design

### 5.1 Envelope

Every canonical record includes schema version, stable ID, episode, monotonic sequence where applicable, game tick, wall UTC, source, correlation links, revisions, payload, and privacy classification. Payload is discriminated by `event_type`; unknown event types are preserved by storage but rejected by strict execution consumers.

### 5.2 IDs

IDs are opaque ASCII tokens with a namespaced kind prefix. Object revisions use separate integer/content revision fields rather than parsing mutable meaning from the ID. Trace links reference immutable record IDs. Human labels never serve as identity.

### 5.3 Versions

- Schema kind has integer `schema_version`.
- Public API and package use SemVer.
- New optional fields require explicit consumer behavior and generally a minor release.
- Changed meaning, removed fields, or stricter formerly-valid constraints require a major release.
- Consumers reject unknown newer execution schemas; offline archival readers may preserve unknown records losslessly.

### 5.4 Null, unknown, and absent

Contracts distinguish:

- absent: field not applicable or not emitted by this version;
- `null`: applicable but unavailable;
- typed `unknown` state: explicitly measured/required but unresolved;
- censored outcome: verification horizon incomplete or observation unavailable.

No consumer may coerce these to success/pass.

## 6. Required schemas

Initial order:

1. `common/id`, `common/revision-set`, `common/freshness`, `common/error`;
2. `events/envelope` and event type payloads;
3. `runtime/objective`, `plan`, `goal`, `task`, `lock`, `pending-action`;
4. `policy/matrix`, `workflow`, `task-template`, `action-template-ref`, `pack-manifest`;
5. `providers/decision-request/result`, `plan-request/proposal`, `capability-report`;
6. `runtime/action-intent/result`, `verification-result`, `vitals`, `runway`, `posture`;
7. `evaluation/fixture`, `calibration-record`, `proposal-result`;
8. `export/manifest`, `trajectory`, `data-quality-report`.

## 7. Validation requirements

- Reject unknown keys in execution-bearing schemas.
- Bound string, array, object, packet, and recursion sizes.
- Forbid absolute paths, parent traversal, YAML aliases after conversion, and secret-shaped fields in pack/export schemas.
- Require enter/exit thresholds together.
- Require verification and fallback for executable matrix options.
- Require stable references to resolve during pack validation.
- Use deterministic canonical JSON serialization for hashing.

## 8. Consumer contracts

- Runtime validates all ingress/egress at trust boundaries.
- RimBrain validates complete pack graphs, not files independently only.
- Steward publishes RPC capability/version documents matching contract fixtures.
- Dashboard uses generated/read-only event/API types.
- Lab validates exports before processing and writes only contract-valid derived artifacts.

## 9. Testing

- Every schema has minimum valid, maximal valid, and targeted invalid examples.
- Property tests cover ID grammar, bounds, and canonicalization.
- Golden canonicalization/hash tests are language-independent.
- Python/C#/TypeScript consumer tests validate the same corpus.
- Backward compatibility tests load every supported prior schema version.
- Malicious cases include oversized strings, deep nesting, path escape, unknown discriminators, NaN/Infinity, duplicate IDs, unresolved refs, and injected game text.

## 10. Upstream migration

Upstream has informal envelopes in `bus.py`, bridge method descriptions, ad hoc LLM capture records, and C# JSON objects. First capture representative examples without treating them as final contracts. Add compatibility adapters in runtime; do not force RimBridge to adopt agent-specific envelopes.

## 11. Delivery increments

- **C0:** repository, schema tooling choice, common conventions.
- **C1:** event envelope + runtime core objects + examples.
- **C2:** provider/matrix/pack contracts.
- **C3:** action/verification/survival contracts.
- **C4:** export/evaluation contracts and generated consumer bindings.

## 12. Acceptance

- All schemas have IDs, versions, docs, valid/invalid fixtures, and deterministic hashes.
- Three language consumers pass the shared corpus when their components exist.
- No contract imports implementation-specific package names.
- Breaking-change detection runs in CI.
- Runtime, lab, dashboard, Steward, and RimBrain pin a compatible contracts release.
