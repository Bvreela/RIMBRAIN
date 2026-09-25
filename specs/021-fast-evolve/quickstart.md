# Quickstart: Fast-Evolve Play Mode

## Prerequisites

- Python env: `uv run pytest -q` baseline green
- Live path: RimBridge at `http://127.0.0.1:8765`, RimWorld running with
  autosaves enabled
- `start-mode-v0` pack (already declares `save-game`/`load-game` + `mutate:`)

## Scenario 1 — deterministic sim retry loop

SimGame gains save/load snapshots; the reflection pass is injected.

```powershell
uv run pytest components/runtime/tests/test_fastevolve.py -q
```

Expected: day-boundary checkpoint anchors resolve, a scripted failure
trigger produces `fastevolve.triggered` → `mutation.*` →
`fastevolve.reloaded` → state reinit; a third trigger emits
`fastevolve.exhausted` with no `load-game` dispatch. Identical inputs produce
a byte-identical event stream.

## Scenario 2 — live run

Testing always runs the UI: `rimbrain run` spawns the overlay alongside
the loop (its launch is verified — a dead overlay warns on stderr rather
than going silently headless). `--fresh` wipes session-scoped state
(runstate, task ledger, fast-evolve session, stale brain requests) so a
test starts from a clean slate while keeping canonical evidence
(`events.jsonl`, `mutations.jsonl`).

```powershell
python rimbrain.py run --mode fastevolve --game live --live-flag --fair --live-brain --feed --fresh
```

or headless:

```powershell
python -m runtime loop --pack start-mode-v0 --mode fastevolve --game live --live --fair --feed --fresh
```

Note: `rimbrain loop --overlay` attaches the UI to the pass-through path;
`rimbrain run --no-overlay` opts out.

Expected:

1. `state/fastevolve.json` appears; `fastevolve.day_start` records day +
   detected autosave anchor.
2. Force a failure (e.g. let a declared `fail_when` predicate trip — drop
   food below the threshold or lose a colonist): feed narrates
   `fastevolve.triggered`, the reflect pass, `mutation.promoted`
   (`mid_run: true`), `fastevolve.reloaded`, and the game visibly reloads
   the autosave.
3. `planning.json` shows the `fastevolve` block: day, anchor,
   `reloads_used`, `exhausted`.
4. After 2 reloads the next trigger emits `fastevolve.exhausted`; play
   continues under the last promoted pack; `state/mutations.jsonl` shows
   every promotion with parent backups.

## Scenario 3 — refusal guards

```powershell
python -m runtime loop --mode fastevolve --game sim          # allowed (sim, injected reflect)
python -m runtime loop --mode fastevolve --game live         # fails: needs --live
python -m runtime loop --mode run --game live --live --dev   # unaffected: dev mode unchanged
```

Expected: invalid combos fail at launch with a named error; `dev.*`
dispatches under fast-evolve still refuse `dispatch.fair_mode`.

## Scenario 4 — launcher (post-018)

When feature 018 ships, the setup screen exposes a Play option control with
`fair run` (default) and `fast-evolve`; selecting it composes the same
command line as Scenario 2.
