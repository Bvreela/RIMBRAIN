# Contracts Versioning Policy

Implements CONTRACTS.md §5.3 and FR-006. Two version axes exist and must not be
conflated:

- **`schema_version`** — a non-negative integer embedded in every contract
  object (`common/revision-set`). Tracks the *meaning* of one schema.
- **Package/API version** — SemVer on the `rimbrainagent-contracts` package and
  any generated bindings. Tracks the *release* of the whole bundle.

## schema_version bump rules

| Change | Bump | Rationale |
|---|---|---|
| Meaning change of an existing field | major | old instances misread silently otherwise |
| Removed field or removed enum value | major | consumers may depend on presence |
| Stricter constraint on a formerly-valid value | major | previously-valid input now rejected |
| New **required** field | major | old producers cannot emit it |
| New **optional** field | minor | consumers must define behavior for it (default: reject via `additionalProperties: false` on execution shapes, preserve on archival shapes) |
| Wider constraint (more values accepted) | minor | old consumers still accept the subset they know |
| Doc/annotation-only change | patch | no wire difference |

## Consumer rules

- An execution-bearing consumer with max known `schema_version = N` **rejects**
  any object declaring `> N` with the shared error envelope
  `{ok:false, error:{code:"schema.version.too_new", ...}}` — never a silent pass.
- Archival/offline readers may preserve unknown records losslessly, but must not
  execute them.
- `additionalProperties: false` on execution-bearing schemas makes "unknown
  newer minor field" an explicit rejection rather than silent data loss.

## Breaking-change detection

A change is breaking if any corpus-valid instance under version N becomes
invalid under N+1, or the schema's acceptance set narrows. Detection:

1. Run the corpus runner (`tests/contract/corpus_runner.py validate-corpus`)
   against both revisions — every prior valid example must still pass.
2. Diff schemas for: removed `required` loosening, added `required` fields,
   narrowed `pattern`/`enum`/`minimum`/`maximum`, added `additionalProperties`.
3. Any breaking schema change requires the major bump above plus a MIGRATIONS.md
   entry before merge.

## Revision value types (recorded decision, T042)

`revision-set` slot values intentionally accept `string | integer >= 0`:
schema/contract revisions are non-negative integers; artifact revisions (commit
SHAs, release tags, model ids like `nemotron-3-ultra-550b-a55b`) are strings.
The union is deliberate -- do not tighten it to a single type. New slots follow
the same rule.`
