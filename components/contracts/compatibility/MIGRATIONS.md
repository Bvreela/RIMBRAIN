# Schema Migrations

Registry of schema_version transitions. One entry per breaking (major) change;
minor/patch changes are recorded in release notes only.

## Entry format

```
## <schema-name> v<old> -> v<new>
- **Date / contracts release**: ...
- **Breaking change**: what changed meaning, was removed, or tightened.
- **Reader rule**: how consumers must treat v<old> records (accept-and-map,
  reject, archive-only).
- **Writer rule**: minimum version producers may emit.
- **Migration**: mechanical transform if one exists, or "none — reject".
```

## Current migrations

None. Baseline: all `schemas/common/*` at `schema_version` 0 (draft) — the
version space starts here; first breaking change begins the table.

## Standing rules

- Records are append-only: supersession happens via newer records, never edits
  (data-model.md §State transitions).
- Consumers rejecting a too-new `schema_version` emit
  `{ok:false, error:{code:"schema.version.too_new", retryable:false}}`.
- A migration is done when the corpus contains valid examples at the new
  version and the property/property-parity tests still pass.
