# Feature Specification: Fork Bootstrap and Contract Foundation

**Feature Branch**: `001-fork-bootstrap-contracts`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Bootstrap RimBrainAgent as a fork of upstream RimAgent — evolve the pinned
upstream codebase rather than rewrite it: establish the component/submodule layout over the existing
upstream Python agent and RimBridge/Steward mod code, add common contract primitives (IDs, revisions,
freshness, error envelope), the canonical event envelope building on the existing JSONL event stream,
core runtime object schemas reflecting upstream concepts (episodes, situations, tools, watchers), and a
fixture harness seeded from recorded upstream behavior — per WP-000 through WP-002 in
specs/40-work-packages/IMPLEMENTATION-PLAN.md."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fork Checkout and Validation (Priority: P1)

A maintainer clones the RimBrainAgent superproject, initializes submodules, and runs the documented
validation job. They get a working fork checkout: the pinned upstream baseline is present and intact,
every component location exists with its own no-op validation entry point, and the upstream test
suites still pass unmodified — proving nothing was rebuilt from scratch and nothing was broken.

**Why this priority**: Everything else in the program depends on a trustworthy fork baseline. If a
clean recursive checkout plus unchanged upstream tests doesn't work, no later contract, migration, or
runtime work can be trusted.

**Independent Test**: On a clean machine, clone recursively, run each component's validation command
and the upstream Python/mod test suites; all pass with zero modifications to the pinned upstream tree.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the superproject, **When** submodules are initialized recursively,
   **Then** the upstream baseline checks out at its recorded pinned revision and reports a clean tree.
2. **Given** the fork checkout, **When** each component's validation job runs, **Then** each reports
   success without requiring secrets, a running game, or a model endpoint.
3. **Given** the pinned upstream baseline, **When** its existing test suites run, **Then** they pass
   identically to upstream, confirming the fork inherits working behavior rather than reimplementing it.

---

### User Story 2 - Baseline Characterization Capture (Priority: P2)

A maintainer runs one documented capture step against the pinned upstream code and gets an immutable
baseline bundle: the exposed game-interface method inventory, representative state/event samples, the
existing event-stream format, deterministic-automation surface, and a manifest recording every pinned
revision and tool version. Later work can diff against this bundle to prove parity or explain drift.

**Why this priority**: The migration plan requires an objective "before" picture. Without a captured
baseline, every later equivalence claim is anecdotal and regressions during migration are invisible.

**Independent Test**: Run the capture step twice; both bundles agree on the pinned revisions and
inventories, and the bundle is sufficient to answer "what did upstream expose and emit" without
re-running anything.

**Acceptance Scenarios**:

1. **Given** the pinned upstream baseline, **When** the capture step runs, **Then** a baseline bundle
   records the interface inventory, representative samples, and a manifest of exact revisions.
2. **Given** two captures of the same pinned baseline, **When** their manifests are compared,
   **Then** identical revision and inventory records are produced.

---

### User Story 3 - Shared Contract Primitives (Priority: P1)

Component authors consume one shared definition of identity, revision, freshness, and failure: the
same ID formats, revision/compatibility declarations, freshness semantics, and error envelope are
available to every component and to RimBrain policy packs, so no component invents divergent
conventions.

**Why this priority**: Every subsequent interface (dispatcher intents, event records, pack manifests,
export formats) depends on these primitives. Getting them shared once prevents four incompatible
implementations.

**Independent Test**: A valid/invalid corpus of example objects is accepted or rejected identically by
the contract definitions and by an initial consumer in the runtime component.

**Acceptance Scenarios**:

1. **Given** an object missing required revision information, **When** any component loads it,
   **Then** it is rejected with a structured error identifying the missing element.
2. **Given** two components exchanging a typed failure, **When** one fails an operation, **Then** the
   other receives a machine-readable error object, not a free-form string.

---

### User Story 4 - Canonical Event Envelope (Priority: P2)

The fork defines one canonical record envelope that subsumes the upstream JSONL event stream: every
observation, decision, action, and outcome carries identity, ordering, causality links, timestamp, and
schema revision. Existing upstream event kinds map into the envelope so history captured by the old
runtime remains readable.

**Why this priority**: Canonical events are the substrate for evidence, exports, replay, and
diagnosis (constitution principles V and VII). A clean mapping from the existing event stream is what
makes this a migration rather than a restart.

**Independent Test**: A corpus containing every current upstream event kind round-trips through the
canonical mapping losslessly enough to reconstruct the original ordering and payload.

**Acceptance Scenarios**:

1. **Given** a recorded upstream event stream, **When** it is mapped into canonical records,
   **Then** every record validates against the declared schema revision and preserves ordering and
   payload content.
2. **Given** a record written under a newer unknown schema revision, **When** a consumer reads it,
   **Then** it is rejected explicitly rather than silently misinterpreted.

---

### User Story 5 - Replayable Fixture Harness (Priority: P3)

A developer can package a recorded upstream session segment as a portable fixture — recorded inputs,
expected observable outputs, and provenance — and replay it offline to verify that migrated behavior
produces equivalent decisions, without launching the game or any model.

**Why this priority**: The constitution's "replay before live authority" rule needs machinery. This
harness is that machinery's foundation, and upstream recordings are its first corpus.

**Independent Test**: Replay a fixture derived from upstream behavior; the harness reports equivalent
versus divergent observable outputs deterministically on repeated runs.

**Acceptance Scenarios**:

1. **Given** a valid fixture package, **When** it is replayed offline, **Then** the harness emits a
   deterministic comparison report with no game or model dependency.
2. **Given** a corrupted or truncated fixture, **When** replay is attempted, **Then** the harness
   fails closed with a precise structural error instead of partial replay.

---

### Edge Cases

- **Partial submodule checkout**: initialization interrupted mid-fetch leaves clear, resumable state;
  validation reports which pinned revisions are missing rather than failing cryptically.
- **Upstream baseline tampering**: any modification inside the pinned upstream tree is detected by
  validation and reported as a baseline-integrity failure.
- **Schema revision drift**: a consumer meeting a newer unknown schema revision rejects it
  explicitly; an older known revision follows the declared migration or compatibility rule.
- **Corrupt canonical records**: a torn or truncated record tail is detected and quarantined; prior
  intact records remain readable.
- **Fixture provenance gaps**: a fixture missing its source-run manifest is rejected; fixtures must
  always trace to a recorded baseline.
- **Windows checkout constraints**: long paths and line-ending differences must not break recursive
  checkout, hashing, or replay on the documented Windows toolchain.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The superproject MUST produce a working fork from a clean recursive clone: every
  declared component location present, every submodule pinned to an exact recorded revision.
- **FR-002**: The pinned upstream RimAgent baseline (including its nested RimBridge submodule) MUST
  remain an intact, read-only reference; any modification inside it MUST be detectable by validation.
- **FR-003**: Each component MUST expose a no-op validation entry point that passes without game,
  model, network, or secret dependencies.
- **FR-004**: The upstream baseline's existing test suites MUST pass unmodified in the fork layout,
  demonstrating inherited behavior rather than reimplementation.
- **FR-005**: The system MUST provide shared primitives for unique IDs, artifact/schema revisions,
  freshness declarations, and a structured error envelope usable by all components and policy packs.
- **FR-006**: Consumers MUST reject objects with missing or unknown-newer revision declarations via
  the structured error envelope.
- **FR-007**: The system MUST define a canonical event record envelope carrying identity, ordering,
  causality references, timestamp, payload, and schema revision.
- **FR-008**: Every event kind currently emitted by the upstream runtime MUST have a documented,
  bidirectionally-testable mapping into the canonical envelope.
- **FR-009**: The fork MUST capture an immutable upstream baseline bundle containing the game-interface
  method inventory, representative state and event samples, deterministic-automation surface, and a
  manifest of all pinned revisions and tool versions.
- **FR-010**: The system MUST provide an offline fixture harness that packages a recorded session
  segment (inputs, expected observable outputs, provenance manifest) and replays it deterministically.
- **FR-011**: Fixture replay MUST fail closed on corrupt or truncated fixture data, naming the exact
  structural defect.
- **FR-012**: Canonical record storage MUST detect torn or truncated tails and quarantine them without
  losing preceding intact records.
- **FR-013**: Every migrated or adapted element MUST be traceable to its upstream origin, consistent
  with the upstream migration map.
- **FR-014**: Component CI/validation shells MUST be committed in a form that activates unchanged once
  component remotes exist; `.gitmodules` MUST NOT reference local filesystem paths.
- **FR-015**: All new structures MUST carry stable identifiers consistent with the project's
  requirement-ID conventions so traceability rows can link them to verification evidence.

### Key Entities

- **Component**: a buildable unit of the fork (contracts, runtime, rimbrain, steward, lab, dashboard,
  bridge integration) with an owner boundary, a validation entry point, and a pinned-or-pending
  submodule identity.
- **Upstream baseline**: the pinned reference revision of RimAgent (and nested RimBridge) that the
  fork evolves; content-addressed by commit hash and integrity-checked.
- **Baseline bundle**: immutable characterization capture — interface inventory, representative
  samples, automation surface, manifest — used as the equivalence reference for migration.
- **Contract primitive**: shared definition of ID, revision, freshness, or error shape; versioned and
  consumed identically everywhere.
- **Canonical record**: a single enveloped evidence/event entry with identity, ordering, causality,
  timestamp, payload, and schema revision.
- **Fixture**: a portable replay package of recorded inputs, expected observable outputs, and a
  provenance manifest tracing to a baseline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new maintainer can go from clean clone to fully validated fork checkout in under 30
  minutes using only documented steps.
- **SC-002**: 100% of upstream test suites pass unmodified in the fork layout.
- **SC-003**: 100% of valid corpus objects are accepted and 100% of invalid corpus objects are
  rejected by the shared contract primitives, identically across consumers.
- **SC-004**: 100% of currently emitted upstream event kinds map into canonical records with zero
  ordering or payload loss.
- **SC-005**: Fixture replay is bit-for-bit deterministic across 5 consecutive offline runs of the
  same fixture.
- **SC-006**: Any single-line modification inside the pinned upstream baseline is detected by
  validation in under 60 seconds.
- **SC-007**: Zero `[NEEDS CLARIFICATION]` items remain unresolved at planning time, and every
  functional requirement maps to at least one acceptance scenario or exit gate.

## Assumptions

- The fork evolves upstream RimAgent at pinned revision `85cb050` (nested RimBridge `3c1e4c7`); a
  clean-room rewrite is explicitly out of scope.
- Component remotes do not exist yet; components begin as in-repo directories with committed
  validation shells and are promoted to pinned submodules only after portable remotes exist.
- The upstream MIT license and Steward third-party notices are preserved and propagate into the fork.
- Validation and replay on Windows use the documented toolchain; `uv` and the .NET SDK are installed
  as Phase 0 prerequisites.
- No live game session, model endpoint, or network service beyond source-control hosting is required
  for any acceptance scenario in this feature.
- CI shells are committed but inactive until component remotes exist; "validation" in this feature
  means locally runnable jobs.
