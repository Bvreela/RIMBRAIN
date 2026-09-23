# Tasks: Model Endpoint Registry and Role Bindings (feature 002)

## Phase 1: Contracts + runtime core

- [x] T056 [P] Schemas `components/contracts/schemas/runtime/endpoints.schema.json` +
  `bindings.schema.json` matching live `profiles/` shape (endpoint: id/label/base_url/api/
  api_key_ref/strict/decide_path/models/capabilities/notes; binding: role→{endpoint,model} +
  degraded_paths) — versioned contract objects
- [x] T057 [P] `runtime/registry.py` — load/validate/save endpoints.yaml + bindings.yaml against
  the schemas; CRUD: add_endpoint, update_endpoint, delete_endpoint, set_binding; named errors
  (`registry.endpoint.missing`, `registry.validation.failed`); YAML authoritative
- [x] T058 [P] `runtime/secrets.py` — resolve `api_key_ref`: `env:NAME` → os.environ;
  `config.local.yaml` key lookup (upstream/rimagent/config.local.yaml); resolved only at call
  time, never serialized into manifests/logs/canonical records (FR-002, SC-005)
- [x] T059 `runtime/probe.py` — probe_endpoint(id): TCP connect → api-shaped model list
  (`GET /v1/models` for openai-compat; `GET /health`+`/v1/models` for systemone) → capability
  check vs declared; classify transient (503/timeout → retryable) vs hard; strict-flag aware;
  `{ok, models, capabilities, latency_ms, probed_utc}` result
- [x] T060 `runtime/discover.py` — scan_local(): probe 1234/11434/8000/8080/8780 concurrently,
  return candidate endpoint dicts with discovered models (FR-007)
- [x] T061 `runtime/bindings.py` — resolve_role(role): binding → endpoint+model; capability gate
  (`rimbrain.select` needs typed_decisions|tool_calls; `rimbrain.embed` needs embeddings;
  FR-006); on failure walk degraded_paths in order → `{resolved, degraded, reason}`; refuse
  nonexistent endpoint ids at load (fail-closed)
- [x] T062 `runtime/client.py` — call adapters: `openai_compat_chat(endpoint, model, messages,
  tools=None)` honoring `strict` (strip extra_body/chat_template_kwargs, FR-011);
  `systemone_decide(endpoint, state, questions)` POST to `decide_path`; structured errors
- [x] T063 `runtime/provenance.py` — episode-manifest writer: per-role `{endpoint_id, model,
  revision?}` resolved at episode start; deterministic JSON (FR-008, SC-004)

## Phase 2: Dashboard UI

- [x] T064 `components/dashboard/src/dashboard/server.py` — stdlib `http.server` settings UI:
  GET `/` (HTML page: endpoints table + bindings editor + probe/discover buttons), JSON API
  `GET/POST/PUT/DELETE /api/endpoints[/<id>]`, `GET/POST /api/bindings`, `POST /api/probe/<id>`,
  `GET /api/discover`; YAML files authoritative (read-per-request); never exposes secrets
- [x] T065 CLI shim `python -m runtime.registry` (list/probe/discover/bind) so the UI and ops
  share one entry point; `python -m dashboard.server --port 8771` launches the UI

## Phase 3: Tests + verification

- [x] T066 [P] Tests `components/runtime/tests/`: registry round-trip, secrets never serialized,
  probe against stub HTTP servers (hard vs transient classification), capability gating,
  degraded-path resolution order, discovery scan, provenance manifest determinism, config.local
  key resolution
- [x] T067 [P] Tests `components/dashboard/tests/`: API surface tests (stub server + urllib),
  YAML round-trip via API, secrets never in API responses, page renders
- [x] T068 runtime+dashboard `validate.py` → real pytest suites; docs (README, INDEX row)
- [x] T069 Live verification: probe openrouter/gemini/local-laya/local-lmstudio against real
  services; discovery finds LM Studio :1234 + Laya :8780; resolved bindings print; secrets sweep

## Phase 4: Convergence

- [x] T070 Add a public `runtime/api.py` facade (list/probe/discover/resolve/bind/client entry points) and switch `components/dashboard/server.py` to import only the facade � dashboard must not import runtime internals per repo boundary rule (contradicts)
- [x] T071 Cache probe results with timestamps (keyed endpoint_id+model, served as last-known when a fresh probe is not requested) per FR-005 (partial)
- [x] T072 Capability-gate `set_binding` at write time so an endpoint lacking the role's required capability is rejected with a structured capability error per US3/AC2 (partial)
- [x] T073 Flag duplicate `base_url` values across registry endpoints in the API payload and dashboard UI per spec edge cases (partial)

## Phase 5: Convergence

- [x] T074 Add binding pinning for scored episodes: `api.pin_bindings()` returns a frozen role->resolution snapshot (endpoint, model, api, degraded flag) and `resolve_role(role, pinned=snapshot)` resolves from the snapshot so mid-episode set_binding cannot alter resolutions per FR-008/US5 (partial)
- [x] T075 Reject `set_binding` when `model` is not in the endpoint's declared `models` list with error code `registry.binding.model` per US3/AC2 and spec edge cases (partial)
- [x] T076 Add `runtime/usage.py` per-endpoint usage counters (calls, tokens where the API reports them) accumulated per episode and folded into `episode_manifest` per US5 (partial)
