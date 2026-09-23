# Plan: Model Endpoint Registry and Role Bindings (feature 002)

## Architecture

Registry layer in `components/runtime`; settings UI in `components/dashboard` consuming the
runtime's public API. `profiles/*.yaml` stays the single source of truth (SC-003 — UI never
holds state).

```
profiles/endpoints.yaml  (authoritative, hand-editable)
profiles/bindings.yaml   (authoritative, hand-editable)
        │
components/runtime/src/runtime/
  registry.py   load/validate/save endpoints+bindings (schema-checked vs contracts)
  secrets.py    api_key_ref resolution: env:VAR | config.local.yaml key — call-time only
  probe.py      TCP → /v1/models (or systemone health) → capability check; classifies
                hard vs transient (503 demand → retryable:true); strict-flag aware
  discover.py   local scan: 1234 LM Studio, 11434 Ollama, 8000 vLLM, 8080 llama.cpp, 8780 Laya
  bindings.py   role → {endpoint, model} resolution + degraded_paths ordered fallback
                + capability gating (select: typed_decisions|tool_calls; embed: embeddings)
  client.py     adapters: openai-compat chat (strict strips extra_body/chat_template_kwargs,
                FR-011) · systemone decisions (state+questions → decide_path)
  provenance.py episode manifest: per-role {endpoint_id, model, revision}
        │
components/dashboard/src/dashboard/server.py — stdlib http.server settings UI (no build step)
  HTML page + JSON API: list/add/edit/delete endpoints, probe, discover, edit bindings
```

## Contracts

`components/contracts/schemas/runtime/`:
- `endpoints.schema.json` — registry file shape (matches live `profiles/endpoints.yaml`)
- `bindings.schema.json` — bindings + degraded_paths

## Key decisions

- **api discriminator**: `openai-compat` | `systemone` — one adapter per shape; `decide_path`
  per-host (local `/v1/systemone`, hosted `/api/alpha/decisions`).
- **Secrets**: never serialized; `api_key_ref` resolves at call time; registry files and logs
  contain refs only (SC-005, swept by T036 pattern).
- **Fail-closed**: dead endpoint → named error + degraded path; non-capable model → reject
  binding; 503/demand-limit → `retryable:true` warning, not rejection.
- **UI = thin file editor + probe runner**; YAML wins on divergence (SC-003).
- Dashboard talks to runtime via in-process import (monorepo path fallback, same pattern as
  lab→contracts) — `runtime.registry`, `runtime.probe`, `runtime.discover`, `runtime.bindings`.

## Constitution gates

- Fail-closed safety: dead/incapable endpoints never silently called.
- Secrets: refs only, never inline.
- Immutability: bindings are runtime state; editing never mutates active packs (FR-010).
- Scored episodes pin resolved bindings at start (FR-008).
