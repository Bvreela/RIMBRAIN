# Plan: Checkpoint-Reload Retry Loops (feature 003)

## Architecture

`components/lab` owns the loop (lab = replay/eval per `specs/20-submodules/LAB.md`); runtime
integration is a later feature. The engine is transport-agnostic:

```
RetryConfig (YAML, schema-validated)
  → RetryLoop engine (lab/retryloop.py)
      GameCtl abstraction (lab/bridge.py)
        ├─ LiveBridge  — HTTP /rpc to zorrobyte :8765 (game.save/load/status/speed/list_saves)
        └─ SimBridge   — in-memory deterministic fake for offline tests
      Gate evaluator (lab/gate.py)  — {field, op, value} predicates over state
      Mutation space (lab/mutations.py) — ordered, enumerable, one-per-retry
      Event sink → canonical `retry.*` envelopes (feature-001 envelope + eventmap)
      Fixture exporter → US5 fixture-package (manifest + input.jsonl + expected.jsonl + sha256)
```

## Key decisions

- **Config as contract**: `schemas/runtime/retry-config.schema.json` — RetryConfig is a versioned
  contract object (`schema_version`, id grammar, revisions).
- **New event types**: `retry.checkpoint.saved`, `retry.window.started`, `retry.gate.evaluated`,
  `retry.mutation.applied`, `retry.iteration.completed`, `retry.loop.completed` — native canonical
  types (no upstream mapping needed), schemas under `schemas/events/types/retry.*`.
- **Gates are state predicates**, never event equality (RimWorld RNG) — `{field, op, value}` list
  with `all|any` combinator over a state snapshot.
- **Mutation space = ordered list** of `{id, apply:{path, op, value}}` edits to a candidate plan
  dict; each retry pops the next; exhaustion → `exhausted`.
- **Scored-episode guard**: refuse to start when `scored_episode_active` flag set or live status
  reports a scored run — fail closed.
- **Checkpoint namespacing**: `retry--<run_id>--cp<N>` save names; `list_saves` verifies no
  collision and no out-of-family writes.
- **Fixture export**: iteration records → `input.jsonl`, expected verdicts → `expected.jsonl`,
  sha256 manifest — replays through the existing US5 harness.

## Constitution gates

- One writer: only `game.*` bridge calls; no game writes outside save/load/speed.
- Immutable packs: mutations produce new candidate revisions, never in-place edits.
- Scored-episode exclusion is a hard rejection (FR-208).
- Flat-file evidence: iteration events are canonical JSONL under the run dir.
- ADR not required: no architectural change — consumes existing bridge + lab contracts.
