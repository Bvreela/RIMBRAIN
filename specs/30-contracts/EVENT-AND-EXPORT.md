# Event and export contract specification

**Status:** READY  
**Requirements:** UR-DAT-004..006, UR-EXP-001..009

## 1. Event envelope

Required fields:

- `schema_version`;
- `event_id`;
- `episode_id`;
- `sequence` monotonically increasing in episode;
- `event_type` from versioned registry;
- `game_tick` and optional structured game time;
- `wall_time_utc`;
- `source` component/service;
- correlation object with plan/goal/task/attempt/request/intent/command and parent event IDs;
- revision set for release/code/contracts/pack/policy/prompt/adapter/model/observation;
- typed payload;
- privacy classification and applied redactions.

Records must remain useful without hidden reasoning.

## 2. Event families

### Lifecycle

`system.started`, `system.compatibility_checked`, `episode.started`, `episode.adopted`, `episode.closed`, `shutdown.requested`, `recovery.started/completed`, `intervention.recorded`, `reload.recorded`.

### Observation and survival

`bridge.event.ingested`, `observation.captured`, `observation.invalidated`, `feature.computed`, `vitals.updated`, `runway.updated`, `posture.changed`, `spiral.detected`, `hazard.updated`.

### Planning and tasking

`objective.updated`, `plan.requested/proposed/rejected/activated/repaired`, `goal.transitioned`, `task.transitioned`, `workflow.advanced`, `lock.acquired/released/revoked`, `assumption.violated`.

### Attention and decision

`attention.queued/selected/preempted`, `candidates.generated`, `candidate.excluded`, `route.selected`, `model.requested/responded/rejected/timed_out/cancelled`, `decision.completed/fallback/abstained`.

### Execution and verification

`intent.queued/rejected`, `action.dispatched/result/uncertain`, `verification.scheduled/completed`, `prediction.scored`, `circuit.opened/closed`.

### Learning and policy

`failure.classified`, `near_miss.detected`, `pawn.died`, `postmortem.completed`, `fixture.proposed`, `lesson.proposed/status_changed`, `policy.proposed/validated/activated/rolled_back`, `selector.qualified/demoted`, `drift.alarm`.

### Operations

`heartbeat`, `safe_pause.requested/completed`, `operator.command.requested/accepted/rejected/completed`, `store.recovered`, `export.created/verified`.

## 3. Decision record projection

The decision projection joins canonical events and includes:

- task intent/deadline and attention reason/competitors;
- exact feature values, units, freshness, source observation IDs;
- matched row/revision;
- every generated option and bound target;
- every exclusion and machine reason code;
- deterministic score/cost/risk/time/effect;
- chosen route and cascade-hop reasons;
- canonical model request/result metadata if called;
- selected and fallback option;
- action intent/result;
- predicted outcome, window, verifier result, censoring, and intervening incidents.

Unchosen options have no observed outcome label.

## 4. Raw provider payload policy

Canonical decision events store structured packet hash, parsed response, usage, timing, and concise rationale/claims. Raw request/response may be written to a restricted stream when enabled and provider terms permit. Authentication headers and secrets are never recorded. Shared exports omit raw reasoning/private reasoning fields by default.

## 5. Export bundle

```text
MANIFEST.yaml
DATA_CARD.md
schemas/
episodes.jsonl
events.jsonl
decisions.jsonl
trajectories.jsonl
fixtures/
reports/
checksums.sha256
```

Manifest includes source episode/file hashes, query/filter, profile, transformation version, schema/contracts release, component/pack/model revisions, environment, assistance/intervention/reload flags, row counts, missingness, privacy policy, license, creation identity/time, and optional signature.

## 6. Training trajectory

A trajectory contains:

- stable trajectory/episode/context-family IDs;
- source event range and state observation refs;
- normalized state/features with missing/unknown masks;
- candidate set and availability mask;
- selected option and route;
- dispatched action abstraction;
- immediate verification;
- delayed outcome windows with horizon and censoring;
- intervening incident IDs;
- policy/model revisions;
- assistance and quality flags;
- split assignment by start-save family.

It excludes fabricated rewards and counterfactual outcomes.

## 7. Profiles

| Profile | Raw model payload | Operator text | IDs | Primary use |
|---|---|---|---|---|
| audit-full | optional local | local restricted | original local | incident audit |
| analysis | parsed only | removed | pseudonymous | strategy/metrics |
| training | parsed structured | removed | pseudonymous | model/outcome training |
| community | minimal | removed | pseudonymous/coarsened | benchmark/sharing |

## 8. Redaction pipeline

1. validate source records;
2. select profile allowlisted fields;
3. remove secret-shaped and prohibited fields regardless of profile;
4. pseudonymize IDs with export-local keyed mapping;
5. normalize/free-text cap or remove according to class;
6. validate no absolute paths, usernames, machine IDs, headers, keys, marked-private text;
7. write provisional bundle;
8. run schema, referential, sequence, privacy, and checksum validation;
9. seal manifest/checksums.

## 9. Verification

Independent verifier checks schemas, file hashes, source hash declarations where source is available, sequence uniqueness/order, ID/reference closure, revision completeness, profile field allowlists, split-family disjointness, no labels on unchosen options, and data-card/manifest consistency.

## 10. Backpressure and loss

Canonical event append failure pauses runtime. Dashboard projection loss is recoverable from sequence. Export reports source gaps and never silently drops malformed records. Large payloads may be content-addressed as side blobs with hash/length/privacy metadata; the event remains self-describing.
