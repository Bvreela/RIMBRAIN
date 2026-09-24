# Data Model: Live-Run Pack Mutation

## Mutation proposal (model output — `mutation.schema.json`)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | `0` |
| `mutation_id` | string | `mut.<slug>` id grammar |
| `base_revision` | string | must equal active pack canonical hash (stale = reject) |
| `analysis.failure_paths` | array<string> | triggered failure paths the model identified |
| `analysis.likely_paths` | array<string> | predicted failure paths |
| `mutations` | array<MutationOp> | 1..N ops (budget from pack `mutate.max_ops`) |
| `rationale` | string | recorded, never executed |

### MutationOp

| Field | Type | Rule |
|---|---|---|
| `op` | enum | `set` \| `append` \| `remove` \| `upsert` |
| `path` | string | dotted path; a segment matching a list element's `id` descends into it |
| `value` | any | required for `set`/`append`/`upsert`; `upsert` value must carry `id` |

Semantics: `set` writes an existing-or-new dict key; `append` pushes onto a list path; `remove` drops the addressed list element/dict key; `upsert` replaces the list element whose `id` equals `value.id`, else appends.

## Mutation lineage (`state/mutations.jsonl` rows)

| Field | Content |
|---|---|
| `candidate_id` | `cand-mut-*` file stem |
| `target_pack` | pack file id the candidate installs over |
| `candidate_path` / `candidate_hash` | file + canonical hash |
| `parent_path` / `parent_hash` | pre-promotion backup under `candidates/` + its hash |
| `baseline_score` | `improve.score` of the incumbent's episode at promotion |
| `state` | `pending` \| `promoted` \| `rejected` \| `reverted` |

## Canonical events (`mutation.*`)

| Type | Payload core |
|---|---|
| `mutation.triggered` | `reason` (`cadence`\|`failure`\|`near_failure`), evidence refs (task ids, defect classes), poll/tick |
| `mutation.proposed` | `mutation_id`, `endpoint_id`, `model`, `degraded`, `analysis`, op count, `usage` |
| `mutation.candidate` | `candidate_id`, path, hash, `target_pack` |
| `mutation.rejected` | `gate` (`schema`\|`stale`\|`vacuous`\|`validation`\|`boundary`), `violations` |
| `mutation.promoted` | `candidate_id`, `pack_hash`, `parent_hash`, `episode_boundary: true`, `baseline_score` |
| `mutation.reverted` | `pack_hash`, `restored_parent`, `episode_score` vs `baseline_score` |
| `mutation.degraded` | trigger reason + `rules-only` outcome (or why nothing applied) |
| `mutation.noop` | trigger reason + model rationale (pass ran, no change proposed) |

## PassState (runtime-only, not canonical)

Per-run mutable state: event ring buffer (last N envelopes), terminal-goal counter since last pass, cooldown poll mark, passes run, last verdict. Disposable — rebuilt empty each launch; lineage survives in `mutations.jsonl`.
