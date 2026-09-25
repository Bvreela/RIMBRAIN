# Research: Fast-Evolve Play Mode

All unknowns resolved against the codebase (features 015–017 state as of
2026-09-24). No external research needed — every mechanism reuses existing
machinery.

## D1 — Mode surface

**Decision**: new `--mode fastevolve` choice on `runtime loop`, passed through
`rimbrain run`; a play-option control on the spec-018 setup screen when that
feature ships.

**Rationale**: the mode is a runtime loop behavior, same level as
`run`/`cycle`/`improve`; the pack stays a policy document. Selecting it via
pack would smuggle a mode switch into data.

**Alternatives**: `--play fastevolve` flag on `run` (rejected: parallel mode
axis duplicates `choices`); pack-declared opt-in (rejected by operator).

## D2 — Save/load permission model

**Decision**: `Dispatcher(..., allow_save_load: bool = False)` — a scoped
grant that bypasses only the `game.save`/`game.load` half of the
`dispatch.fair_mode` refusal (`dispatch.py` ~line 212). `dev.*` refusal and
dev-class pack refusal unchanged; `fair` stays `True`.

**Rationale**: `--dev` opens the whole debug surface — far broader than the
feature needs. A named grant keeps fair-class guarantees (mutations still
can't introduce `dev.*`) while permitting exactly the two methods the retry
loop uses.

**Alternatives**: run under `--dev` (rejected: too permissive, hides the
distinction); direct `game.rpc` calls bypassing dispatch (rejected: violates
the single-writer invariant and loses `action.*` evidence).

## D3 — Retry anchor

**Decision**: poll `game.list_saves` every `saves_poll_every` polls (default
10); match names against `fastevolve.autosave_pattern` (default
`(?i)autosave`). The bridge returns `[{name, modified}]` — a wall-clock
mtime, no game-day field — so day attribution correlates `modified` against
`day_start_wall` (recorded in the day session at rollover): the anchor is
the match nearest day start, preferring at-or-after; a mid-day autosave
only becomes the anchor when no day-start match exists.

**Rationale**: operator locked "detect real autosaves"; RimWorld's autosaver
fires at day start by default, so the newest-match-at-day-start rule gives
"retry the whole day" semantics. `cycle.py::_saves` already wraps
`game.list_saves`.

**Alternatives**: own day-start `save-game` checkpoint (rejected by operator —
but the same code path remains available as a future `anchor: own` cfg);
newest save regardless of timing (rejected: replays only part of the day).

## D4 — Mid-run promotion

**Decision**: factor the install half of `evolve.boundary()` (re-validate →
parent backup → `write_atomic` over the pack file → lineage row →
`mutation.promoted`) into a shared `promote_candidate()` usable mid-run; skip
the episode-scoring revert check (no episode boundary mid-day); mark lineage
`mid_run: true`. After promotion, `dispatcher.load_pack(pack_id)` rebinds the
hash so `dispatch.pack_drift` stays intact.

**Rationale**: one candidate format + one lineage log + one gate is the
feature-016 invariant (T037); duplicating install logic forks it.

**Alternatives**: load the candidate file without touching the pack file
(rejected: drift check hashes the file vs. the loaded doc — would need a
second integrity model); keep boundary-only promotion and evolve on next
*run* (rejected: defeats the retry loop — the point is retrying under the
evolved brain).

## D5 — Post-reload reinit

**Decision**: reuse the brain-reset sequence (`loop.py` ~lines 148–180):
`rs.reset()`, `ledger.reset_ns("start.","govern.","phase.","combat.")`,
fresh `PhaseEngine`, fresh day-scoped `PassState` (seeded with the day's
cumulative evidence — see D8).

**Rationale**: constitution X — a pack change must leave no residual state;
the reset path is already tested (`test_brain_reset_unload_reload_loop`).

## D6 — Day detection

**Decision**: `obs["day"]` when present (SimGame and live `game.status` both
surface it; `state.summary` confirms), else `tick // 60000`. First poll of a
run establishes the current day; day rollover = anchor re-resolution +
budget reset.

## D7 — Trigger evaluation

**Decision**: two pack-declared sources, evaluated per poll inside the loop
after the reflect stage:

1. `fastevolve.triggers.fail_when` / `near_when` — `policy.check` predicates
   over obs (colony level: pawn downed/dead, food runway, hostiles).
2. `fastevolve.triggers.use_mutate` — reuse `evolve.check_triggers` on a
   day-scoped `PassState` (goal failed/expired, requeues, refusals, blocked
   dwell, escalations, defect patterns).

**Rationale**: both levels locked by operator; reusing `check_triggers` keeps
one trigger vocabulary. Day-scoped PassState means trigger windows reset at
day rollover — a day's failures don't bleed into the next.

## D8 — Reflection input on retry

**Decision**: the pass gets a `day_failure` (or `day_near_failure`) reason
and the digest sees cumulative evidence across the day's attempts — the
PassState window survives the reload, only its *marks* advance per pass.

**Rationale**: spec assumption; retry N's diagnosis should know retries
1..N-1 already failed.

## D9 — Pause during evolve

**Decision**: `game.pause` while the reflect pass + reload run; restore prior
speed after. The pass is wall-clock seconds; at speed 3 the day would advance
under the agent's feet.

## D10 — Session persistence

**Decision**: `state/fastevolve.json` — `{day, anchor, anchor_day, reloads_used,
exhausted, attempts: [...]}` written atomically (`store.write_atomic`). Lives
outside `RunState` so it survives both the reload wipe and process restarts.

## D11 — Exhausted-day evolve

**Decision**: a trigger on the final attempt still runs the reflection pass
(per-day pass budget applies); only the reload is skipped. Locked by
operator.

## D12 — Sim support

**Decision**: `SimGame` gains `game.save`/`game.load`/`game.list_saves` as
named state snapshots plus configurable autosave rows; `--mode fastevolve
--game sim` runs with injected reflect (same injection seam as
`mutate_resolver`/`mutate_chat`). Live requires `--live` as usual.

## Open risks

- **Autosave naming variance** across game versions/languages — mitigated by
  the configurable pattern; a non-matching setup degrades to evolve-only
  (`fastevolve.anchor_missing`), never to wrong-save reload.
- **`game.list_saves` cost** — filesystem scan throttled by
  `saves_poll_every`.
- **Bridge `game.load` while paused** — `_wait_playing` (phase.py:73) already
  handles the post-load transition; pause is reasserted by the speed-keepalive.
