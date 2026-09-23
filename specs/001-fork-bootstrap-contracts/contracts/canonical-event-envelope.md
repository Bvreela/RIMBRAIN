# Contract: Canonical Event Envelope + Upstream Mapping

**Version**: 0.1.0-draft | **Implements**: FR-007, FR-008 | **Owner**: `components/contracts`

Schema files at implementation: `schemas/events/envelope.schema.json` + per-family payload schemas
+ `components/contracts/registry/event-map.yaml` (versioned kind→type mapping; the event-type
registry per CONTRACTS.md §2).

## Envelope fields

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | envelope contract revision |
| `event_id` | `evt.*` ID | unique per record |
| `episode_id` | `ep.*` ID or null | null allowed for pre-episode system events |
| `sequence` | int | monotonic within episode |
| `event_type` | string | registered type, `family.name` grammar |
| `game_tick` | int or null | absent when unknowable |
| `wall_time_utc` | RFC 3339 | always present |
| `source` | string | emitting component |
| `correlation` | object | plan/goal/task/attempt/request/intent/command/parent-event refs |
| `revisions` | revision-set | provenance of producing code/policy/model |
| `payload` | object | discriminated by `event_type` |
| `privacy` | object | classification + applied redactions |

Distinct states honored: absent ≠ null ≠ `unknown` ≠ censored (CONTRACTS §5.4).

## Upstream `bus.py` → canonical map

Upstream envelope `{seq, t, kind, data}` → `{sequence, wall_time_utc, event_type, payload}`:

| Upstream `kind` | Canonical `event_type` | Notes |
|---|---|---|
| `status` | `system.status` | data carries game.status + phase |
| `think_start` / `think_end` | `model.think.started/completed` | trigger, notes, wake, calls |
| `reasoning` | `model.reasoning` | privacy: restricted; omitted from shared profiles |
| `assistant` | `model.assistant` | visible model text |
| `tool_call` / `tool_result` | `model.tool_call` / `model.tool_result` | dispatcher-era equivalents are `intent.queued`/`action.*`; mapping keeps legacy family for replay |
| `ledger` | `bridge.event.ingested` | ledger subkind preserved in payload |
| `watcher` | `policy.watcher.fired` | action/alert/error in payload |
| `brain_change` | `policy.brain.changed` | skill/tool/watcher/notebook/journal/git |
| `watchdog` | `policy.watchdog.completed` | summary/fixes/commits/errors |
| `episode_start` / `episode_end` | `episode.started` / `episode.closed` | seed, score, reason, brain_sha |
| `situation` | `observation.packet.shown` | what the model was shown |
| `operator` / `reply` | `operator.message` / `operator.reply` | operator-channel records |
| `log` / `error` | `system.log` / `system.error` | |

`game_tick`, `correlation`, `revisions` have no upstream source → emitted `null`/absent; mapping
must never fabricate them (R5). Unknown future `kind` values map to `legacy.unmapped` with the raw
kind preserved — stored, but rejected by strict execution consumers.

## Validation

- `sequence` strictly increasing per episode stream; duplicates/gaps flagged at load.
- Payload validated against the `event_type`-discriminated schema; unknown `event_type` → preserve
  in storage, reject for execution consumers.
- Round-trip corpus: one synthesized record per upstream kind must map forward and reproduce the
  original `{seq,kind,data}` payload losslessly (SC-004).
