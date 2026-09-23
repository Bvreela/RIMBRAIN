# Release profiles + LLM endpoint registry

Two distinct mechanisms live under `profiles/`:

## Release profiles (pinned compatibility)

Versioned, nonsecret compatibility manifests pinning component commits, contract versions, RimBrain pack hashes, model revisions, and supported game environments. No executable profile exists during specification preparation.

## Endpoint registry (planned — feature 002)

`endpoints.yaml` — named, nonsecret LLM endpoint entries: `id`, `label`, `base_url`, `api` shape, advertised models, capabilities (tool_calls / thinking / embeddings / vision), context limits, cost hints. Local (LM Studio, Ollama, vLLM, llama.cpp) and remote endpoints share the format.

`bindings.yaml` — semantic role → endpoint+model (`rimbrain.plan`, `rimbrain.select`, `rimbrain.review`, `rimbrain.embed`, …). Bindings are runtime state: changing them never mutates an active RimBrain pack.

Secrets stay out of both files: API keys are referenced by name from environment variables or `config.local.yaml` (gitignored). See `specs/002-model-endpoints/` and UNIFIED-REQUIREMENTS UR-MOD-011..017.
