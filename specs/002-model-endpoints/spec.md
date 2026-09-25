# Feature Specification: Model Endpoint Registry and Role Bindings

**Feature Branch**: `002-model-endpoints`
**Created**: 2026-09-22
**Status**: Draft
**Input**: User request — "allow easy editing and selection of previously configured local or remote api endpoints for both planning and matrix actions. A simple user friendly ui for this is prefered."

## Overview

The runtime needs named, reusable LLM endpoint configurations (local: LM Studio, Ollama, vLLM, llama.cpp; remote: OpenAI-compatible APIs) that a user can create once and then bind to semantic model roles — planning, action-matrix selection, review, embeddings — through a simple UI, without hand-editing config per use. Today upstream hardcodes a single `llm:` block; our tiered architecture needs per-role endpoints with capability gating and provenance.

## User Stories *(mandatory)*

### User Story 1 - Endpoint Registry (Priority: P1)

A user defines named endpoints once — local servers and remote APIs — with a single consistent schema, and can edit them via UI or YAML interchangeably.

**Why this priority**: Everything else (bindings, tiering, provenance) depends on a registry of trusted endpoints existing.

**Independent Test**: Create/edit/delete endpoints through the UI and by editing `profiles/endpoints.yaml` directly; both views agree; restart preserves entries.

**Acceptance Scenarios**:

1. **Given** a running LM Studio server, **When** user adds endpoint `{id: "local-lmstudio", base_url: "http://127.0.0.1:1234/v1"}`, **Then** it appears in the registry with discovered model list.
2. **Given** a registered endpoint, **When** user edits `endpoints.yaml` by hand, **Then** the UI reflects the change on next read (no UI-only state).
3. **Given** an endpoint entry with `api_key_ref: "env:OPENROUTER_API_KEY"`, **Then** the key resolves at call time and never appears in the file, logs, or canonical records.

---

### User Story 2 - Role Bindings (Priority: P1)

A user assigns endpoints+models to semantic roles (`rimbrain.plan`, `rimbrain.select` (action-matrix rows), `rimbrain.review`, `rimbrain.embed`, …) independently — e.g. big remote model for planning, local 8B for selection.

**Why this priority**: Per-role endpoints are the point of the tiered architecture (UR-MOD-001/013).

**Independent Test**: Bind `plan` → remote model, `select` → local 8B; inspect `profiles/bindings.yaml` + runtime resolution; each role resolves to its own endpoint.

**Acceptance Scenarios**:

1. **Given** two registered endpoints, **When** user assigns `rimbrain.plan` → remote, `rimbrain.select` → local, **Then** both bindings persist and resolve independently.
2. **Given** a scored episode in progress, **When** user edits a binding, **Then** the episode's pinned resolution is unchanged (bindings are runtime state, not pack mutation — UR-MOD-013/016).

---

### User Story 3 - Health, Capability, and Fallback (Priority: P2)

Before a binding is usable, the endpoint is probed: reachable, `/v1/models` lists the chosen model, required capabilities present (tool-calls for `select`/`plan`, embeddings for `embed`). Failure = fail-closed to declared degraded path.

**Why this priority**: Prevents silent misbinding — a non-tool-calling model must never serve a tool-calling role (UR-MOD-017).

**Independent Test**: Point a binding at a dead endpoint → UI shows failed probe, role reports degraded-path status, no silent calls attempted.

**Acceptance Scenarios**:

1. **Given** an endpoint that is down, **When** health probe runs, **Then** binding is marked failed with a named error and the role reports its degraded path.
2. **Given** an endpoint serving a model without tool-call support, **When** bound to `rimbrain.select`, **Then** the binding is rejected with a capability error.

---

### User Story 4 - Local Discovery (Priority: P3)

A "scan local" action probes well-known ports (LM Studio 1234, Ollama 11434, vLLM 8000, llama.cpp 8080) and offers discovered servers as one-click endpoint entries.

**Why this priority**: Convenience; manual entry already works. Verified pattern exists — this dev machine's LM Studio was auto-found on :1234 during environment setup.

**Independent Test**: With LM Studio running, scan produces a candidate endpoint with its live model list pre-filled.

---

### User Story 5 - Provenance and Manifest Binding (Priority: P2)

The resolved endpoint+model+revision for each role at episode start is recorded in the run manifest; per-endpoint usage/cost accumulates per episode.

**Why this priority**: Model provenance is constitutionally required for replay/eval comparability (UR-MOD-016, UR-EXP).

**Independent Test**: Run a bounded episode; manifest shows per-role endpoint id, model id, and (where the server reports it) revision/hash.

## Edge Cases

- Endpoint registered but server later removed/moved → probe fails, binding marked stale, role degrades per UR-MOD-017.
- Two endpoints with identical base_url → allowed (distinct ids), flagged in UI as duplicates.
- Model list changes on a live server (LM Studio swaps loaded model) → probe detects `model` no longer advertised → binding warns/fails per strictness setting.
- Remote endpoint with key rotation → `api_key_ref` re-reads env var; no registry edit needed.
- `bindings.yaml` hand-edited to reference a nonexistent endpoint id → startup validation fails closed with named error.
- Strict endpoints reject nonstandard request fields → client strips provider extensions per `strict` flag (FR-011).
- Free-tier remote endpoints hit demand limits (503) → probe classifies as transient (`retryable: true`), binding allowed with degraded-path warning rather than hard rejection.
- Model id mismatches (e.g. `gemma-4-4b-it` vs actual `gemma-4-31b-it`) → probe validates `model` against the endpoint's advertised list before binding.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Registry `profiles/endpoints.yaml` stores named endpoints: `id`, `label`, `base_url`, `api` (openai-compat initially), `models[]`, `capabilities[]`, optional `context`, `cost_hint`.
- **FR-002**: Secrets never inline: `api_key_ref` names an env var or `config.local.yaml` key; resolved at call time only.
- **FR-003**: `profiles/bindings.yaml` maps role → `{endpoint_id, model, options}`; roles resolve independently.
- **FR-004**: A UI (dashboard settings surface) lists endpoints, edits entries, runs probes, edits bindings; YAML remains authoritative — UI writes the same files.
- **FR-005**: Health probe per endpoint: TCP + `GET /v1/models` + capability check; results cached with timestamp, re-probeable on demand.
- **FR-006**: Capability gating: `rimbrain.select` accepts `typed_decisions` (preferred — Laya `/v1/systemone` style, calibrated choice/score/noul) or `tool_calls` (chat-model fallback); `rimbrain.embed` requires `embeddings`; mismatch = fail-closed + named error.
- **FR-007**: Local discovery scan across known ports producing candidate endpoints with discovered models.
- **FR-008**: Episode manifests record per-role `{endpoint_id, model, revision?}` resolved at episode start; scored episodes pin bindings.
- **FR-009**: All failures use the shared error envelope `{ok:false,error:{code,message,details,retryable}}` (contract-primitives).
- **FR-011**: Endpoints may declare `strict: true`; the client MUST NOT send provider-specific extensions (`extra_body`, `chat_template_kwargs`, etc.) to strict endpoints. Verified failure 2026-09-22: Gemini's compat shim 400s on upstream's unconditional `chat_template_kwargs` — upstream `llm.py` is incompatible with strict endpoints, fork runtime must gate such fields per endpoint.
- **FR-010**: Changing a binding never mutates the active RimBrain pack or canonical records; bindings live under runtime state, not policy.

## Success Criteria *(mandatory)*

- **SC-001**: User configures a local endpoint and binds it to a role in under 2 minutes via UI with zero YAML edits.
- **SC-002**: A dead endpoint produces a named failure within the probe timeout and the role reports degraded status — no hangs, no silent calls.
- **SC-003**: Registry survives restart; hand-edited YAML and UI state never diverge (UI reads files as source of truth).
- **SC-004**: Episode manifest records every role's endpoint/model; two runs with different bindings produce distinguishable manifests.
- **SC-005**: No secret material appears in `profiles/*.yaml`, logs, canonical records, or packs — verified by the secrets sweep (feature 001 T036 pattern).

## Assumptions and Constraints

- OpenAI-compatible `/v1` API is the common shape; other API shapes are extension points, not v1 scope. **Decision (2026-09-22)**: Gemini is consumed via its OpenAI-compat shim (`https://generativelanguage.googleapis.com/v1beta/openai`), not the native `generateContent` action — keeps one API shape.
- UI lives on the dashboard surface (port 8770) or a settings view exposed by the runtime's public control API — never inside `components/dashboard` internals.
- This feature is runtime/profile-layer; it does not change bridge protocols or the ADR-001 bridge decision.
- Dev machine reality: LM Studio already serves on :1234 (5 models incl. `rimdialogue-8b`, `nomic-embed`); `:8000` vLLM absent; `:11434` Ollama absent — discovery must tolerate absent servers.
- Seed bindings (2026-09-22, verified live): `rimbrain.plan`/`rimbrain.review` → OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` (verified chat + tool_calls + `reasoning.enabled`; upstream `rimagent llm` round-trips it); `rimbrain.select` → local Laya `laya_english_q8_0` on :8780 (**verified**: `POST /v1/systemone`, ~55ms warm) with ordered degraded path → OpenRouter hosted `~typesafe/jev-latest` (`/api/alpha/decisions`, same wire shape, 428ms, ~$0.000018/call) → rules; `rimbrain.embed` → LM Studio `nomic-embed-text-v1.5`. Gemini `gemini-3.5-flash-lite` verified earlier and kept as alternate endpoint entry.
- `api` is NOT only openai-compat: `systemone` is a real v1 shape — typed `state`+`questions` → calibrated answers; no tokens generated. The registry treats `api` as a discriminator driving the client adapter; `decide_path` holds the per-host route (`/v1/systemone` local, `/api/alpha/decisions` on OpenRouter). Same wire shape serves local Laya AND hosted `~typesafe/jev-latest` — one adapter, two endpoints (verified 2026-09-22).
- Caveat to validate at probe time: remote planner models are demand-limited on free tier; degraded paths in bindings.yaml cover this (UR-MOD-017).

## Out of Scope

- Actual model quality/capability benchmarking per endpoint (lab concern).
- Cost accounting engines beyond per-endpoint counters.
- Non-OpenAI API adapters (Anthropic native, etc.) — extension point only.
- GPU/host management (starting/stopping model servers) — could be a later `profiles` extension.
