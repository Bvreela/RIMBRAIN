# Phase 1 Data Model: Fork Bootstrap and Contract Foundation

**Date**: 2026-09-22 | **Plan**: [plan.md](plan.md)

Entities below are contract-level definitions. Field-level wire format lives in
`contracts/*.md` here and lands as JSON Schema in `components/contracts/schemas/` at
implementation (increment C0–C1 per `specs/20-submodules/CONTRACTS.md`).

## Component

A buildable unit of the fork.

| Field | Rule |
|---|---|
| `component_id` | namespaced ID, e.g. `cmp.contracts` |
| `path` | repo-relative location, e.g. `components/contracts` |
| `remote` | URL or `null` until portable remote exists |
| `pin` | exact commit, or `pending` while in-repo |
| `owns` / `excludes` | boundary lists per `specs/10-architecture/REPOSITORY-TOPOLOGY.md` |
| `validate` | no-op-capable validation entry point (FR-003) |

## SubmodulePin

| Field | Rule |
|---|---|
| `path`, `url`, `commit` | full SHA, never a floating ref |
| `nested` | set of child pins (RimBridge inside upstream/rimagent) |

Validation: porcelain scan must be clean; drift = integrity failure (FR-002, SC-006).

## BaselineBundle

| Field | Rule |
|---|---|
| `bundle_id`, `created_utc`, `manifest_hash` | immutable once sealed |
| `pins` | SubmodulePin set incl. nested |
| `rpc_inventory` | method name, group, doc, source file/line — static `[Rpc]` extraction |
| `event_corpus` | per-kind synthesized examples, `provenance` marker |
| `automation_surface` | Steward orders/scorer/stock inventory |
| `tool_manifest` | OS, tool versions used to capture |
| `gaps` | deferred items (live state samples) with reason |

## ContractPrimitive

Shared types every other schema composes:

- **ID** — opaque ASCII, `kind.name` namespaced grammar (`evt.`, `plan.`, `cmp.`, `fix.` …);
  human labels never identity.
- **RevisionSet** — `schema_version` int + named revision slots (release, contracts, pack, model…).
- **Freshness** — `observed_tick`, `observed_utc`, `max_age_ticks`; missing on freshness-bearing
  objects = load failure.
- **Error** — `{ok:false, error:{code, message, details?, retryable}}`; mirrors upstream RPC
  envelope so bridge failures and contract failures share one shape.

## CanonicalRecord

Envelope per `specs/30-contracts/EVENT-AND-EXPORT.md` §1: `schema_version`, `event_id`,
`episode_id`, `sequence`, `event_type` (versioned registry), `game_tick`, `wall_time_utc`,
`source`, `correlation{…}`, `revisions{…}`, `payload` (discriminated by `event_type`), `privacy`.
Absent/null/unknown/censored are distinct states; none coerce to success.

## Fixture

| Field | Rule |
|---|---|
| `fixture_id` | `fix.*` ID + content hash |
| `manifest` | provenance (source run/baseline), schema revisions, file hashes |
| `input.jsonl` | canonical records feeding replay |
| `expected.jsonl` | observable outputs to compare |
| `quarantine/` | torn/invalid records separated at load |

## State transitions

- **Component**: `in-repo` → `remote-created` → `submodule-pinned` (one-way per release).
- **Fixture**: `proposed` → `validated` → `sealed`; corrupt → `quarantined`.
- **CanonicalRecord**: append-only; no transitions — supersession happens via newer records, not edits.
- **BaselineBundle**: `open` while capturing → `sealed` (manifest hash fixed); live-sample gap closes
  via a new bundle version, never mutation.
