# Contracts: `mutation.*` event types

New payload schemas under `components/contracts/schemas/events/types/` (one file per type, matching the feature-009/015 pattern), registered in `contracts/registry/event-map.yaml` with corpus cases.

| Event | Required payload | Contract notes |
|---|---|---|
| `mutation.triggered` | `reason`, `evidence`, `poll` | `reason` enum: `cadence` \| `failure` \| `near_failure`; `evidence` = task ids / defect classes that fired it |
| `mutation.proposed` | `mutation_id`, `endpoint_id`, `model`, `degraded`, `usage` | mirrors `plan.proposed` provenance fields |
| `mutation.candidate` | `candidate_id`, `path`, `hash`, `target_pack` | file materialized under `packs/candidates/` |
| `mutation.rejected` | `mutation_id`, `gate`, `violations` | `gate` enum: `schema` \| `stale` \| `vacuous` \| `validation` \| `boundary` |
| `mutation.promoted` | `candidate_id`, `pack_hash`, `parent_hash`, `episode_boundary`, `baseline_score` | `episode_boundary` must be `true` — same contract rule as `improvement.promoted` |
| `mutation.reverted` | `pack_hash`, `restored_parent`, `episode_score`, `baseline_score` | only ever follows a `mutation.promoted` lineage row |
| `mutation.degraded` | `reason`, `detail` | model unavailable; rules-only outcome recorded |
| `mutation.noop` | `reason`, `rationale` | pass ran; model proposed no change |

Invariants enforced by contract:

- `mutation.promoted` and `mutation.reverted` can only appear at a run boundary — `episode_boundary: true` is a hard enum, matching `improvement.promoted`.
- `mutation.candidate` never carries a `dispatch` field — a candidate is data; nothing executes it mid-run.
- Every event joins `feed.md` narration via the feed writer's decision-type table (audit.py `DECISION_TYPES` extended).
