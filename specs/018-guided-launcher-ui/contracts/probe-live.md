# Contract: `api.probe_live(role)` + `api.validate_pack_doc(doc)`

**Feature**: 018 | **Producer**: `components/runtime` (`runtime.api` facade)
**Consumers**: `components/dashboard` (brains panel, pack editor)

## probe_live(role) — role-shaped live verification

```python
def probe_live(role: str, *, timeout_s: int = 10) -> dict
```

Resolves the role offline (`resolve_role`), then executes ONE live call
against the bound model, shaped by the role's **required capability**
(`registry.ROLE_REQUIREMENTS`), not just the endpoint api:

| role capability | Call |
|---|---|
| `typed_decisions` | POST `{base_url}{decide_path}` — minimal typed question (existing `_decide_probe` shape), `model` included when bound |
| `chat` | POST `{base_url}/chat/completions` — `{model, messages:[{role:"user","content":"ping"}], max_tokens:1}` |
| `embeddings` | POST `{base_url}/embeddings` — `{model, input:["ping"]}` (existing `openai_compat_embed` shape) |

Note: a role binding to an endpoint lacking its required capability already
fails `resolve_role`'s capability gate — the shaped call only runs on
capable resolutions. For `systemone`: local single-family servers may 422
on a `model` field — implementation verifies and omits `model` for local
endpoints if so (hosted decisions requires it).

### Result envelope

```jsonc
{
  "ok": true,
  "role": "rimbrain.select",
  "verdict": "answered",            // answered | model_failed | unreachable
                                    // | missing_secret | fallback_only | unbound
  "endpoint": "local-laya",          // resolved endpoint id (null for fallback)
  "model": "laya",                   // bound model (null for fallback)
  "api": "systemone",
  "latency_ms": 55.2,                // live call only
  "fallbacks": ["openrouter-decisions:~typesafe/jev-latest", "rules"],
  "degraded": false,                 // true if resolution fell off the primary
  "checked_utc": "2026-09-24T12:00:00Z"
}
```

### Verdict semantics

| verdict | Meaning | UI treatment |
|---|---|---|
| `answered` | Live call returned 2xx with a parseable response | green + latency |
| `model_failed` | Endpoint reachable (TCP or listing ok) but the live call returned HTTP error/timeout | amber + status |
| `unreachable` | TCP connect failed | red |
| `missing_secret` | `api_key_ref` could not resolve | red + which env var |
| `fallback_only` | Role resolves to a sentinel fallback (`rules-only`, `skip`, …) — no endpoint exists to test | dim + fallback name |
| `unbound` | Role has no binding | dim |

Failure path also returns the shared `{ok:false,error:{code,...}}` envelope
for internal errors — callers distinguish `ok:true + verdict` from
`ok:false + error`.

### Rules

- Never mutates registry/bindings; read-only + one outbound call.
- `timeout_s` bounds the live call; TCP precheck stays at 5s.
- `429`/5xx live-call failures mark the result `retryable: true` (display as
  transient/busy, not hard-down).
- Cost floor: chat probes MUST send `max_tokens: 1` and a fixed one-token
  prompt; decide probes reuse the existing minimal question payload.

## validate_pack_doc(doc) — loader-identical pack validation

```python
def validate_pack_doc(doc: dict) -> dict
```

Runs the identical sequence `templates.load_pack` applies after parsing —
`validate_pack` (jsonschema or builtin) → `policy.validate_policy` when
`policy_version` is present → sealed-inventory method check — WITHOUT
touching the filesystem.

```jsonc
// ok
{"ok": true, "issues": []}
// invalid
{"ok": false, "issues": ["$.templates[3].method: 'x' not in bridge inventory", ...]}
```

### Rules

- Pure function of `doc`; no pack-path resolution, no file I/O, no writes.
- Issue strings match loader error text so editor messages equal what a
  rejected load would say.
- Class/inventory checks identical: a doc passing here MUST pass `load_pack`
  for the same content (modulo file-not-found/parse, which the editor
  controls).

## policy_vocabulary() — dialect vocabulary for guided editing

```python
def policy_vocabulary() -> dict
```

Returns the pack dialect vocabulary the editor's structured builders and
insert-assist need, sourced from `policy.py` (the dialect's owner — the
dashboard MUST NOT import it directly):

```jsonc
{
  "ok": true,
  "ops": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "empty",
          "not_empty", "truthy", "falsy", "contains", "contains_any",
          "matches", "absent", "present"],
  "combinators": ["all", "any", "not"],
  "functions": ["add", "sub", "min", "max", "anchor", "find_kind", ...],
  "resolvers": ["@cfg:", "@obs:", "@var:"]
}
```

### Rules

- Read-only, no I/O beyond what policy.py already does at import.
- The vocabulary is authoritative — dropdowns and insert-assist lists MUST
  come from here, never a duplicated constant in dashboard code (drift).
- If the facade is unavailable (runtime not importable — standalone
  overlay), guided builders degrade to freeform text entry; they MUST NOT
  fall back to a copied vocabulary table.
