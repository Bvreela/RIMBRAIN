# Data Model: Fast-Evolve Play Mode

## Entities

### DaySession (durable — `state/fastevolve.json`)

Persisted per in-game day; survives the post-reload runstate wipe and
process restarts. Written atomically on every field change.

| Field | Type | Meaning |
|-------|------|---------|
| `schema_version` | int | currently 0 |
| `day` | int | in-game day this session covers |
| `day_start_wall` | str | wall-clock timestamp when this day's rollover was observed |
| `anchor` | str \| null | save name this day rewinds to |
| `anchor_day` | int \| null | day the anchor autosave was detected for |
| `reloads_used` | int | 0..`max_reloads_per_day` |
| `exhausted` | bool | true once a trigger fires on the final attempt |
| `attempts` | list | per-attempt outcome rows (see below) |

### EvolveAttempt (row inside `DaySession.attempts`)

| Field | Type | Meaning |
|-------|------|---------|
| `n` | int | 1-based attempt number within the day |
| `trigger` | str | `day_failure` \| `day_near_failure` |
| `evidence` | dict | trigger evidence (predicate hits, failing goals) |
| `reflect_verdict` | str | `candidate` \| `noop` \| `rejected` \| `degraded` |
| `candidate_id` | str \| null | promoted candidate, if any |
| `reloaded` | bool | whether the anchor load was dispatched |
| `save` | str \| null | anchor actually loaded |

### AutosaveAnchor (in-memory scan cache)

`game.list_saves` returns `[{name, modified}]` — a wall-clock mtime, no
game-day field. Day attribution therefore uses `day_start_wall`:

| Field | Type | Meaning |
|-------|------|---------|
| `name` | str | save file name matching the pattern |
| `modified` | str | file mtime from `game.list_saves` |

Selection rule: among pattern matches, the anchor is the save whose
`modified` is **nearest `day_start_wall`** — preferring the closest match
at or after it (a day-start autosave), falling back to the newest match
before it. A match whose `modified` predates the previous day's
`day_start_wall` by more than `max_anchor_age_days` is flagged `stale`.
When a run starts mid-day, `day_start_wall` is unknown for the current
day; the newest match is taken as the anchor (documented assumption: it
belongs to today).

## Pack configuration — `fastevolve:` section

All retry policy is pack data (Principle IX). Validation: unknown keys
warn; numeric fields clamp to sane ranges; `fail_when`/`near_when` must be
valid `policy.check` predicates (validated at pack load like `when` gates).

```yaml
fastevolve:
  max_reloads_per_day: 2        # -> 3 total attempts
  autosave_pattern: "(?i)autosave"
  saves_poll_every: 10          # polls between game.list_saves scans
  max_anchor_age_days: 1        # older anchor => treated as missing
  pause_during_evolve: true
  max_passes_per_day: 3         # reflection budget, day-scoped
  triggers:
    use_mutate: true            # reuse evolve.check_triggers
    fail_when: {any: []}        # policy.check over obs -> day_failure
    near_when: {any: []}        # policy.check over obs -> day_near_failure
```

### Day-scoped PassState config

The reused `evolve.check_triggers` runs on a `PassState` whose cfg is the
pack's `mutate:` section with two overrides from `fastevolve:`:
`max_passes_per_run := fastevolve.max_passes_per_day` and
`cooldown_polls := 0` — day-scoping replaces run-scoping, and retry
latency matters more than pass spacing inside a failing day.

## Canonical events (`fastevolve.*`)

All envelopes use the standard mutation/event envelope shape
(`schema_version`, `event_id`, `sequence`, `game_tick`, `wall_time_utc`,
`source: rimbrainagent.runtime.fastevolve`, `payload`).

| Event | Payload | When |
|-------|---------|------|
| `fastevolve.day_start` | `{day, anchor, anchor_stale}` | day rollover detected |
| `fastevolve.triggered` | `{day, attempt, reason, evidence}` | day trigger fired |
| `fastevolve.anchor_missing` | `{day, reason}` | trigger with no usable anchor (evolve runs, no reload, attempt not spent) |
| `fastevolve.reloaded` | `{day, attempt, save, candidate_id}` | anchor load completed |
| `fastevolve.exhausted` | `{day, attempts}` | trigger fired on final attempt |
| `fastevolve.promoted` | `{day, candidate_id, parent_hash}` | mid-run promotion (alongside `mutation.promoted` with `mid_run: true`) |

`mutation.*` events keep their existing meanings for the embedded reflect
pass; `fastevolve.*` covers the retry bookkeeping around it.

## State transitions

```
day N begins
  -> [anchor resolved] -> playing
playing --trigger, reloads_used < max--> evolving (pause)
evolving --candidate gated--> promoting -> reloading -> reinit -> playing
evolving --noop/rejected/degraded--> reloading -> reinit -> playing
playing --trigger, budget spent--> exhausted (evolve runs, no reload)
day N+1 begins -> fresh session, reloads_used = 0
```

## Validation rules

- `reloads_used` never exceeds `max_reloads_per_day` (FR-2106).
- `anchor` may only name a save returned by `game.list_saves` matching the
  pattern — never an arbitrary string (prevents loading hand-made saves).
- `attempts` is append-only within a day.
- `exhausted` is one-way within a day; resets on rollover.
- On reload failure the attempt row records `reloaded: false` and the
  budget is still spent.
