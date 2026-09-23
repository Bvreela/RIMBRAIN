# Interface catalog

**Status:** READY  
**Purpose:** Name every cross-component boundary before implementation.

## IC-01 RimBridge transport

- **Provider:** RimBridge
- **Consumers:** runtime bridge gateway; Steward through assembly hooks/RPC registration
- **Transport:** loopback HTTP JSON plus C# assembly extension points
- **Operations:** health, method inventory, event polling, screenshot, RPC
- **Compatibility:** pinned revision + capability inventory hash
- **Failure semantics:** transport error, remote error envelope, timeout/uncertain mutation, event gap
- **Framework rule:** only read gateway and dispatcher mutation gateway use it.

## IC-02 Steward RPC/event protocol

- **Provider:** Steward
- **Consumer:** runtime Steward gateway; legacy client during transition
- **Operations:** capabilities, status, enable, pawn ownership, explain, posture desired state, stock desired state/run, research desired queue, standing-order state/control/release
- **Events:** stock state, posture expiry, standing-order actions, safety transitions
- **Version:** contract version reported at discovery
- **Correlation:** framework mutations carry intent/idempotency metadata where supported.

## IC-03 RimBrain pack mount

- **Provider:** RimBrain repository/release artifact
- **Consumer:** runtime `BrainStore`, Lab verifier/replay, dashboard artifact API
- **Form:** read-only directory/archive with manifest and content hashes
- **Operations:** load, validate, resolve refs, snapshot identity, semantic diff
- **Mutation:** none; proposals target separate workspace.

## IC-04 Provider role protocols

- **Provider:** runtime adapter implementations backed by local/hosted endpoints
- **Consumer:** model router/planning service
- **Operations:** `select`, `plan`, `repair`, `review`, optional `critique`
- **Request:** typed contract with deadline, revisions, packet hash
- **Result:** typed result/proposal or typed abstention/error
- **Rule:** transport adapter cannot alter candidate/policy semantics.

## IC-05 Runtime canonical event stream

- **Provider:** runtime event store/projection API
- **Consumers:** dashboard, Lab, operator tooling
- **Form:** schema-versioned append-only records and SSE projection
- **Ordering:** monotonic sequence per episode; causal parent links
- **Durability:** source event store authoritative; SSE may be replayed from sequence.

## IC-06 Runtime read API

- **Provider:** runtime
- **Consumer:** dashboard, diagnostics
- **Resources:** episode/system identity, plan/goals/tasks, survival, attention, matrices, providers, actions/verifications, policy/proposals, metrics
- **Semantics:** immutable revision-tagged snapshots; pagination for records
- **Security:** loopback default; no secrets/private endpoint payloads.

## IC-07 Runtime control API

- **Provider:** runtime
- **Consumer:** dashboard/operator CLI
- **Command envelope:** command ID, actor, action, parameters, expected revision, reason, confirmation token/class
- **Results:** accepted/rejected plus eventual completed event
- **Idempotency:** repeated command ID returns existing result
- **Rule:** control queues obligations/intents; endpoint handlers never call bridge directly.

## IC-08 Runtime state store

- **Provider/consumer:** internal runtime services
- **Form:** atomic snapshots + append records under configured state root
- **Public:** no cross-repo imports; format schemas live in Contracts
- **Recovery:** migrations and reconcile-only startup.

## IC-09 Action template registry

- **Provider:** runtime/domain code
- **Consumer:** dispatcher
- **Entry:** ID/version, typed params, required predicates/freshness, lock classes, max writes/time, idempotency query, execute function, verification, partial failure, rollback ability
- **Rule:** RimBrain may reference only registered entries.

## IC-10 Domain registration

- **Provider:** runtime domain packages
- **Consumer:** runtime composition/policy engine
- **Registers:** predicates, features, candidate generators, action templates, verifiers, failure classifiers, fixtures/capabilities
- **Rule:** no provider clients or raw mutation gateway.

## IC-11 Export bundle

- **Provider:** Lab
- **Consumers:** external AI/research tools, community benchmark, dashboard report viewer
- **Form:** manifest, schemas, JSONL, optional Parquet, fixtures, reports, checksums, data card
- **Profiles:** audit-full, analysis, training, community
- **Verification:** independent command/library API.

## IC-12 Replay protocol

- **Provider:** Lab runner
- **Consumers:** CI, pack contributors, calibration evaluation
- **Input:** fixture/export + exact contracts/pack/renderer/optional endpoint
- **Output:** deterministic result, equivalence/rejection, diff, metrics, provenance
- **Rule:** no live game writes.

## IC-13 Pack proposal/promotion evidence

- **Provider:** runtime reviewer/human working copy and Lab evaluation
- **Consumers:** human promoter, pack release tooling
- **Form:** scoped diff, diagnosis, evidence refs, fixtures, validation/replay/calibration/trial reports, approval, target parent hash
- **Activation:** handled by runtime/superproject only after release; Lab cannot activate.

## IC-14 Release profile

- **Provider:** superproject release process
- **Consumers:** deploy/runtime/Lab/dashboard
- **Form:** component commits/versions, contract compatibility, pack hash, supported environment, build hashes
- **Rule:** scored runs pin one validated profile.

## Interface readiness checklist

An interface is `READY` only when it has owner/consumer, versioning, schema/examples, timeout/failure semantics, idempotency where applicable, security/privacy classification, compatibility tests, and a migration story from upstream behavior.
