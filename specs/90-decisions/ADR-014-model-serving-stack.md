# ADR-014: Model serving stack — native Laya for select, OpenRouter for plan/review, LM Studio for embed

**Status:** PROPOSED
**Date:** 2026-09-22
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** specs/002-model-endpoints, profiles/endpoints.yaml, profiles/bindings.yaml, UR-MOD-011..017, open decision #6 in INITIAL-ADRS.md (resolved here)

## Context

Role-tiered model routing needs concrete endpoints. Verified live on the dev machine 2026-09-22.

## Decision drivers

- `rimbrain.select` wants calibrated, low-latency typed decisions, not text generation.
- `rimbrain.plan`/`review` want strong reasoning with tool_calls; cost matters for dev loops.
- Secrets must stay out of specs/records (env-var `api_key_ref` pattern).

## Options considered

### Option A — All-local

LM Studio chat models for everything. Rejected: no ≥8B tool-calling model loaded; reliability unproven.

### Option B — All-remote

OpenRouter/Gemini for all roles including select. Rejected: latency + dependency for a per-tick-adjacent tier; local Laya is faster and free.

### Option C — Mixed (chosen)

Local decision engine for select; hosted LLM for plan/review; local embeddings.

## Decision

- **`rimbrain.select`** → local Laya `laya_english_q8_0` via `tools/serve-laya.ps1` on `127.0.0.1:8780` (`api: systemone`, `POST /v1/systemone`). Ordered fallback: OpenRouter `~typesafe/jev-latest` (`/api/alpha/decisions`, same wire shape) → rules.
- **`rimbrain.plan`/`rimbrain.review`** → OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` (verified chat+tool_calls+reasoning). Fallback: Gemini `gemini-3.5-flash-lite`.
- **`rimbrain.embed`** → LM Studio `nomic-embed-text-v1.5` on `127.0.0.1:1234`.
- Windows containers explicitly **not** used for Laya — single native binary; CUDA-12 DLLs from pip wheels (`tools/setup-laya.ps1`, docs `tools/LAYA-SETUP.md`).

## Consequences

### Positive

- Every tier verified live today; zero-cost dev loop; offline-capable select path.
- `systemone` adapter serves both local and hosted decision endpoints (one code path).

### Negative

- 421M selector capacity is bounded; complex multi-option rows may need a chat-model selector fallback (already in `degraded_paths`).
- Remote plan/review depends on free-tier availability (503s are retryable, not fatal — spec 002 edge cases).

## Verification

bridge_check 9/9; laya `/health` + `/v1/systemone` verified; OpenRouter chat+tool_calls+reasoning verified; env-check covers ports 5174/8765/8780/1234.

## Revisit/kill criteria

- Selector calibration gates fail on real matrix rows → qualify a chat-model selector or retrain.
- OpenRouter free-tier limits block episode runs → promote a paid key or bigger local model.
