# Feature Specification: Dispatcher (Single Writer), Action Templates, Core-Survival Policy Pack v0

**Feature Branch**: `004-dispatcher-single-writer`

**Created**: 2026-09-22

**Status**: Draft

**Input**: Unified architecture — "one runtime dispatcher owns every framework game write; models emit typed choices or proposals and never execute unrestricted game calls; emergencies never wait for a model" — first vertical slice: the agent performs survivable game actions through a validated, evidence-captured single writer.

## Purpose

Close the loop opened by features 001–003: we have contracts, live endpoint bindings, and a checkpoint/retry harness — but **nothing yet writes to the game from framework decisions**. This feature builds the single game writer (dispatcher), a declarative action-template library derived from the 115-RPC bridge inventory, a v0 core-survival policy pack (food + emergency), typed-decision → action mapping (Laya/systemone), a deterministic emergency reflex that bypasses models, and a poll loop — all offline-verifiable and evidence-captured as canonical events.

## User Stories *(mandatory)*

### User Story 1 - Single Writer (Priority: P1)

Every framework game mutation flows through one dispatcher as a validated action. No code path may call bridge RPCs directly; unknown actions are refused before any write.

**Why this priority**: Constitution-required. Without a single writer, "models never execute unrestricted game calls" is unenforceable.

**Independent Test**: Instrument the bridge client call count; run an offline episode with 50 framework actions; assert every call originated in `dispatch()` and the emitted event stream equals the write stream.

**Acceptance Scenarios**:

1. **Given** a template-registered action with valid params, **When** `dispatch()` is called, **Then** exactly one bridge RPC executes and `action.issued`/`action.completed` events are emitted.
2. **Given** an action id not in the template registry, **When** `dispatch()` is called, **Then** it is refused with `dispatch.unknown_action` and no bridge call is made.

### User Story 2 - Typed Decisions Drive Actions (Priority: P1)

`rimbrain.select` decisions (typed choice/score/noul answers from Laya or hosted jev) translate through a declared decision-map to dispatcher actions. A decision that maps to no template is refused.

**Why this priority**: This is the Laya integration — the select-tier matrix actually doing something in the game.

**Independent Test**: Feed a canned systemone response (`{p: {choice: "forbid"}}`) through the decision pipeline; assert the mapped template fires with mapped params; feed an unmapped choice and assert `dispatch.decision_unmapped`.

**Acceptance Scenarios**:

1. **Given** a decision-map entry `{decision: {q, choice}, action: {template, params}}`, **When** the select answer matches, **Then** the action dispatches with mapped params.
2. **Given** an answer with no matching decision-map entry, **When** the loop processes it, **Then** it is refused with a named error and no write occurs.

### User Story 3 - Core-Survival Policy Pack v0 (Priority: P2)

A validated-data pack declares the action templates, the survival jobs (food, emergency), and the decision-map. Packs are immutable during scored runs; the pack revision hash rides in every evidence event.

**Why this priority**: Policy must be reviewable, hashed, and immutable-in-run per constitution; templates come from the pack, not code.

**Independent Test**: Load `core-survival-v0` pack; validate against the pack schema; assert the hash is stable across loads and a one-byte edit changes it.

**Acceptance Scenarios**:

1. **Given** a pack with templates, **When** loaded, **Then** every template's `method` is cross-checked against the bridge inventory (115-RPC manifest) and unknown methods reject the pack.
2. **Given** an active scored run, **When** the pack file changes on disk, **Then** dispatch refuses new actions with `dispatch.pack_drift` (loaded revision vs disk hash).

### User Story 4 - Evidence Everywhere (Priority: P2)

Every accepted write, refusal, and reflex fires canonical `action.*` events with provenance: pack revision, decision id (when model-sourced), template id, params, result. Offline replayable.

**Why this priority**: SC-301 ("event stream ≡ write stream") and the retry/eval machinery from feature 003 both consume this.

**Independent Test**: Run the offline loop; replay the event JSONL through the feature-001 fixture harness; assert round-trip integrity and that refusals are represented (never silently dropped).

**Acceptance Scenarios**:

1. **Given** an accepted action, **Then** events carry `{pack_revision, template_id, params, outcome}`.
2. **Given** a refused action, **Then** a `action.refused` event records the refusal code — failures are evidence, not silence.

### User Story 5 - Emergency Reflex (Priority: P3)

Deterministic checks (downed colonist, fire) evaluated every poll **before** any model call; matching rules fire immediate template actions. Emergencies never wait for a model.

**Why this priority**: Constitution MUST: "emergencies never wait for a model."

**Independent Test**: Offline state with `colonist downed=true` and a stubbed select tier that would answer after 10s; assert the reflex action fires within one poll with **zero** client calls.

**Acceptance Scenarios**:

1. **Given** state matching an emergency rule, **When** the loop polls, **Then** the reflex template action dispatches immediately (no model call in the poll).
2. **Given** a model call in flight when an emergency triggers, **Then** the emergency action still dispatches (emergency priority over in-flight model work).

## Edge Cases

- Decision maps to a template but required params are absent → `dispatch.params_invalid`, no write.
- Template method not in the bridge inventory → pack rejected at load (fail-closed, no partial pack).
- Pack hash drift mid-run → `dispatch.pack_drift`, new actions refused; already-issued writes stand.
- Two processes dispatch concurrently → lock conflict → one succeeds, other gets `dispatch.locked`.
- Reflex and model decision race → reflex wins (deterministic ordering: reflex before model in the poll).
- Bridge RPC fails (timeout/HTTP) → `action.failed` event with structured error; dispatcher stays available.
- Scored run with uncommitted/dirty pack → dispatch refuses (constitution: scored runs reject dirty state).
- Decision answer references an unknown question id → `dispatch.decision_unmapped`, no write.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-301**: The dispatcher is the single writer: all framework game mutations go through `dispatch(action_id, params)` after template validation; no other code path may invoke bridge game RPCs.
- **FR-302**: Action templates are declarative pack data: `{id, method, params_schema, require: [params], description}`; `method` must exist in the bridge inventory manifest; templates validate params before any RPC.
- **FR-303**: Typed decisions (systemone answers: choice/score/noul) map via the pack's `decision_map` to `{template_id, params}`; unmapped decisions are refused with a named error.
- **FR-304**: Fail-closed dispatch: unknown action id, invalid params, unmapped decision, capability mismatch, or lock conflict → structured error envelope (`common/error`), zero bridge writes.
- **FR-305**: Core-survival policy pack v0 is validated data: `{schema_version, pack_id, revision, templates[], jobs[], decision_map[], emergency[]}`; load validates schema + inventory cross-check; canonical hash (feature-001 canonical JSON) identifies the revision.
- **FR-306**: The dispatcher enforces a single-writer lock (in-process + advisory file lock); concurrent dispatch attempts fail with `dispatch.locked` rather than interleaving.
- **FR-307**: Evidence: each dispatch outcome emits canonical events `action.issued`, `action.completed`, `action.failed`, `action.refused`, `action.emergency` carrying `{pack_revision, decision_id?, template_id, params, outcome}` per the feature-001 event envelope.
- **FR-308**: Emergency reflex: a deterministic rule set evaluated before model decisions each poll; matching rules dispatch immediately — no model call, no planner wait.
- **FR-309**: The dispatcher loop is offline-verifiable: a deterministic SimGame stub serves the same RPC surface templates use; five consecutive loop runs are bit-identical; a live mode exists for operator smoke tests.

### Key Entities

- **ActionTemplate**: `{id, method, params_schema, require, description}` — declarative write contract.
- **PolicyPack**: `{schema_version, pack_id, revision, templates, jobs, decision_map, emergency}` — immutable-in-run validated data with canonical hash.
- **DecisionMapEntry**: `{question, choice|score|noul, action: {template_id, params}}` — typed answer → action binding.
- **EmergencyRule**: `{id, condition (state predicate), priority, action: {template_id, params}}` — deterministic no-model reflex.
- **DispatchRecord**: `{action_id, template_id, params, decision_id?, outcome, result?, error?}` — per-write evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-301**: Event-stream ≡ write-stream: in an offline episode, the set of bridge RPC calls equals the set of `action.issued` events (audited by test).
- **SC-302**: Zero unvalidated writes: across all dispatch tests, no bridge call occurs for unknown/invalid/unmapped/locked/pack-drift cases (fail-closed coverage).
- **SC-303**: Five consecutive offline loop runs produce bit-identical event streams and state traces (determinism).
- **SC-304**: A scored run's pack is immutable: pack hash is stable across loads; mid-run disk edit yields `dispatch.pack_drift` refusals.
- **SC-305**: Emergency reflex fires within one poll with zero model calls (offline test with a slow/stubbed select tier).

## Assumptions

- The dispatcher lives in `components/runtime` (may depend on RimBridge/Steward protocols and contracts); policy data lives in `components/rimbrain` (validated data, contracts/schemas only); evidence uses the feature-001 event envelope.
- Bridge HTTP surface remains the zorrobyte RimBridge :8765 (115-method inventory at `baselines/upstream-85cb050/rpc-inventory.json`).
- v0 scope is food + emergency survival actions (prioritize work, forbid/unforbid, haul, rescue, firefight); defense/world/endgame policies are later features.
- The select tier is Laya (local) with hosted jev fallback, per feature 002 bindings; decisions arrive as typed answers, not free text.
- Live smoke (like 003 T055) is operator-initiated; CI runs offline determinism only.

## Out of Scope

- Strategic planners / review loops (feature 005).
- Steward extraction/protocol and new mod logic — templates call existing bridge RPCs only.
- Learned mutation spaces (feature 003 already declares them); LLM-synthesized templates.
- Multi-colony, modding APIs beyond the inventory, and long-horizon (multi-day) policy packs.
