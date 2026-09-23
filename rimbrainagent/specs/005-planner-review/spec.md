# Feature Specification: Strategic Planner / Review Loop

**Feature Branch**: `005-planner-review`

**Created**: 2026-09-22

**Status**: Draft

**Input**: Unified architecture — hosted models (rimbrain.plan, rimbrain.review) do planning, strategy, review, and self-improvement while code stays the authority: models emit typed proposals, never unrestricted calls.

## Purpose

Wire the planning tier end-to-end: colony state → `rimbrain.plan` (OpenRouter/Gemini via feature-002 bindings) produces a **typed plan proposal** (actions + policy mutations, schema-validated) → `rimbrain.review` + deterministic constitution checks produce a verdict → accepted proposals materialize a **candidate pack revision** (never mutating the active pack) and may dispatch through the feature-004 single writer. Every step emits canonical events with model provenance and token usage.

## User Stories *(mandatory)*

### User Story 1 - Typed Plan Proposals (Priority: P1)

The planner consumes observed state + the active pack and returns a structured plan: `actions[]` (dispatcher calls) and `policy_mutations[]` (candidate edits). Malformed output is a named error, never a guess.

**Why this priority**: Models must emit typed choices — a free-text plan is unusable and dangerous.

**Independent Test**: Feed the planner a stubbed chat response containing JSON; assert the proposal validates `plan.schema.json`; feed malformed text and assert `plan.malformed` with zero writes.

**Acceptance Scenarios**:

1. **Given** a planner response with a `plan` JSON object, **When** planning completes, **Then** a validated PlanProposal `{plan_id, base_revision, horizon_ticks, actions, policy_mutations}` exists and a `plan.proposed` event records endpoint+model+usage.
2. **Given** a planner response that is not parseable JSON, **When** planning completes, **Then** `plan.rejected`/`plan.malformed` is recorded and no actions or candidates exist.

### User Story 2 - Review: Code Decides, Model Advises (Priority: P1)

Every proposal passes deterministic checks (actions resolve to real templates; params satisfy params_schema; mutations target allowed paths; pack-drift guards) plus an optional `rimbrain.review` model critique. Approval requires deterministic checks to pass — the model cannot approve a violating plan.

**Why this priority**: Constitution — models advise, code decides. This is the self-improvement gate.

**Independent Test**: Proposal referencing a nonexistent template → rejected by the deterministic gate even if the review model approves.

**Acceptance Scenarios**:

1. **Given** a proposal with an unknown template, **When** reviewed, **Then** `plan.rejected` with the deterministic violation listed.
2. **Given** a clean proposal, **When** reviewed, **Then** verdict approved (or revised with feedback) and `plan.reviewed` carries verdict + feedback.

### User Story 3 - Candidate Pack Revisions (Priority: P2)

Accepted `policy_mutations` produce a new candidate pack under `components/rimbrain/packs/candidates/` — validated, hash-versioned, never overwriting the active pack. Immutable scored packs are untouched.

**Why this priority**: Self-improvement = producing *new* revisions; active authority never mutates mid-run (constitution).

**Independent Test**: Accept a proposal with one mutation → candidate file exists, loads through `templates.load_pack`, hash differs from base, base file byte-identical.

**Acceptance Scenarios**:

1. **Given** an accepted proposal with mutations, **Then** `packs/candidates/<base>-<sha8>.yaml` exists and passes schema + inventory checks.
2. **Given** a mutation that would break schema/inventory, **When** materializing, **Then** `plan.rejected` (`plan.mutation_invalid`), no file written.

### User Story 4 - Provenance + Evidence (Priority: P2)

Every plan/review/accept/reject emits canonical `plan.*` events carrying `{endpoint_id, model, pack_revision, plan_id, usage{prompt_tokens, completion_tokens}, verdict}`.

**Why this priority**: Replay/eval comparability; SC-405 degraded-path visibility.

**Independent Test**: Run offline loop; assert events validate payload schemas and carry resolved endpoint+model and token counts.

### User Story 5 - Degraded Planner (Priority: P3)

If the planning endpoint is down, the loop degrades per `bindings.yaml` (openrouter → gemini → rules-only). `rules-only` is a deterministic fallback plan declared in the pack — the loop still completes, marked `degraded`.

**Why this priority**: UR-MOD-017 fail-closed, no hangs on free-tier limits.

**Independent Test**: Unreachable openrouter + gemini → resolution walks degraded path → rules-only plan produced with `plan.degraded` provenance.

## Edge Cases

- Planner answers with markdown-fenced JSON → extractor handles ```json blocks and bare objects.
- Model returns valid JSON but wrong shape → `plan.malformed` (schema), zero writes.
- Review model down → verdict proceeds on deterministic checks only (`review.model_unavailable` noted, verdict still deterministic).
- Plan asks to dispatch while lock held → dispatcher `dispatch.locked` (feature 004) — plan outcome records refusal.
- Endpoint resolves to fallback sentinel (`rules-only`) → deterministic plan from pack `fallback_plan` block.
- Plan proposes mutation duplicating a template id → rejected (`plan.mutation_invalid`, no partial write).
- Scored episode → planner loop refuses to start (`plan.scored_episode_active`), same guard as feature 003.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-401**: Planner requests go through feature-002 bindings (`rimbrain.plan` → resolved endpoint+model) and feature-002 client (openai-compat chat honoring `strict`).
- **FR-402**: Planner output is a typed PlanProposal (schema): `{schema_version, plan_id, base_revision, horizon_ticks, actions[], policy_mutations[], rationale}`; unparseable/invalid → `plan.malformed`, zero side effects.
- **FR-403**: Review = deterministic checks (template existence, params against params_schema, mutation legality, inventory) THEN optional model critique via `rimbrain.review`; verdict requires deterministic pass.
- **FR-404**: Accepted mutations materialize `packs/candidates/<base>-<sha8>.yaml` (schema-validated, inventory-checked); the active pack file is never written; candidates are data, not auto-loaded.
- **FR-405**: Canonical events `plan.proposed`, `plan.reviewed`, `plan.accepted`, `plan.rejected` carry `{endpoint_id, model, pack_revision, plan_id, usage, verdict}` per the feature-001 envelope.
- **FR-406**: Accepted `actions[]` dispatch only through `Dispatcher.dispatch` (feature 004 single writer); the planner layer holds no bridge client.
- **FR-407**: Offline determinism: injected planner/reviewer produce fixture answers; sim loop is bit-identical across runs; live mode opt-in (`--live`).
- **FR-408**: Planner resolution uses binding degraded paths; terminal `rules-only` sentinel yields a deterministic fallback plan from the pack (`fallback_plan` key) — loop completes with `plan.degraded` provenance.
- **FR-409**: The planner loop refuses to start while a scored episode is active (`plan.scored_episode_active`), mirroring the feature-003 guard.

### Key Entities

- **PlanProposal**: `{schema_version, plan_id, base_revision, horizon_ticks, actions[], policy_mutations[], rationale}` — planner's typed output.
- **PlanAction**: `{template_id, params}` — dispatcher-shaped action request.
- **PolicyMutation**: `{op: add_template|edit_decision_map|add_emergency, target, patch}` — candidate pack edit.
- **ReviewVerdict**: `{verdict: approved|rejected|revised, violations[], feedback, model_unavailable?}`.
- **CandidatePack**: materialized pack revision under `packs/candidates/`, hashed and validated, never auto-active.

## Success Criteria *(mandatory)*

- **SC-401**: No violating plan is ever accepted — deterministic gate overrides model approval (tested with an approving stub + violating plan).
- **SC-402**: Malformed planner output → `plan.malformed` + zero writes/candidates.
- **SC-403**: Five offline plan loops produce bit-identical event streams.
- **SC-404**: Every materialized candidate loads through `templates.load_pack` (schema + inventory).
- **SC-405**: With planning endpoints unreachable, the loop completes via `rules-only` fallback with `degraded` provenance in the manifest.

## Assumptions

- Planning lives in `components/runtime` (may call the feature-002 client; may NOT hold a bridge client — dispatch only).
- `rimbrain.plan`/`rimbrain.review` bindings resolve per feature 002 (openrouter primary, gemini degraded, `rules-only` terminal).
- The deterministic review gate is code, not model output — model critique is advisory text in the verdict.
- Candidates are opt-in review artifacts; nothing auto-promotes them to active packs (promotion is a later feature + human gate).
- Plan loop is a dev/eval/operator tool for v0; scored runs embed plans via pinned manifests only.

## Out of Scope

- Auto-promoting candidates to active policy (human/ADR-gated later).
- Long-horizon multi-day planning (WP-304 holistic first week).
- Planner-authored new action templates reaching the bridge without inventory methods (rejected at review anyway).
- Learned/LLM-synthesized mutation spaces (feature 003 uses declared spaces).
