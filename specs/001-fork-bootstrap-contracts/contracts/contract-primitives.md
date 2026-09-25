# Contract: Common Primitives

**Version**: 0.1.0-draft | **Implements**: FR-005, FR-006, FR-015 | **Owner**: `components/contracts`

Schema files at implementation: `schemas/common/{id,revision-set,freshness,error}.schema.json`
(JSON Schema 2020-12, `additionalProperties: false` on execution-bearing shapes).

## `common/id`

- Grammar: `^[a-z][a-z0-9]*\.[A-Za-z0-9][A-Za-z0-9_-]{2,63}$` — `kind.identifier`.
- Registered kinds: `evt`, `ep`, `obs`, `plan`, `goal`, `task`, `lock`, `intent`, `act`,
  `ver`, `req`, `resp`, `fix`, `pack`, `cmp`, `blb`, `pm` (post-mortem).
- IDs are opaque and immutable; ordering/identity semantics live in envelope fields, never in the ID.

## `common/revision-set`

- `schema_version`: non-negative integer, required on every contract object.
- Named slots (all optional except `schema_version`): `release`, `code`, `contracts`, `pack`,
  `policy`, `prompt`, `adapter`, `model`, `observation`.
- Rule: consumer with max known `schema_version = N` rejects any object declaring `> N` for
  execution-bearing schemas; archival readers may preserve unknown records losslessly (CONTRACTS §5.3).

## `common/freshness`

- Fields: `observed_tick` (int), `observed_utc` (RFC 3339), `max_age_ticks` (int).
- Freshness-bearing consumers treat missing freshness as a load failure, not as "fresh" (P13).

## `common/error`

- Envelope: `{ "ok": false, "error": { "code": string, "message": string,
  "details"?: object, "retryable": bool } }`.
- Success envelope: `{ "ok": true, "result": ... }`.
- Intentionally identical in spirit to upstream `{ok:false,error}` RPC responses — one failure
  grammar from bridge boundary to contract validation (FR-006 acceptance: machine-readable, never
  free-form strings).

## Corpus

`examples/valid/`: minimal + maximal instances per primitive.
`examples/invalid/`: malformed ID grammar, negative schema_version, missing freshness on a
freshness-bearing ref, error with missing `code`, unknown extra key on execution shape.
