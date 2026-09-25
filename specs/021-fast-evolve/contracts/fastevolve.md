# Contracts: Fast-Evolve Play Mode

## 1. CLI surface

```text
python -m runtime loop --mode fastevolve --game live --live [--fair]
                       [--feed] [--live-brain] [--iterations N]
rimbrain run --mode fastevolve ...
```

| Rule | Behavior |
|------|----------|
| Requires | `--game live` + `--live`, or `--game sim` (deterministic test path) |
| Implies | reflect-pass wiring (the `--live-mutate` PassState machinery) — the flag itself is not required, and the generic per-poll `maybe_trigger` call is bypassed: in this mode only `fastevolve.tick` invokes the pass, so cadence triggers can't fire (FR-2112) |
| `--stage` | stage debug entries (`plan`/`reflect`/`combat`) are unchanged and orthogonal — they bypass the loop and never enter fast-evolve behavior |
| Forbidden | combination with scored/fair-scored episode contexts; `--mode fastevolve` + any scored flag fails at launch with `loop.fastevolve_scored` |
| Dispatch grant | `Dispatcher(allow_save_load=True)` — `game.save`/`game.load` pass the fair check; `dev.*` still refused |
| Pack class | fair-class packs only (unchanged); the pack must declare `save-game`/`load-game` templates (start-mode-v0 already does) |

Error envelope on invalid combination (matches existing CLI error style):

```json
{"ok": false, "error": {"code": "loop.fastevolve_scored",
 "message": "fast-evolve is an unscored play mode; ...", "retryable": false}}
```

## 2. Pack contract — `fastevolve:` section

See `data-model.md` for the full schema. Contract-level rules:

- Absent section → mode runs with documented defaults (still pack-tunable by
  adding the section; defaults are the contract).
- `triggers.fail_when`/`near_when` are `policy.check` predicates evaluated
  against the canonical obs dict — the same dialect as goal `when` gates;
  invalid predicates fail pack validation at load (`pack.invalid`).
- `autosave_pattern` is a regex matched against `game.list_saves` names;
  only matching names can ever become anchors.
- A pack MAY tighten `max_reloads_per_day` to 0 (evolve-only, never reload).

## 3. Dispatcher contract change

`Dispatcher(..., allow_save_load: bool = False)`.

- `False` (default): unchanged — `game.save`/`game.load` refuse under fair
  with `dispatch.fair_mode`.
- `True`: those two methods dispatch normally; `dev.*` refusal, template
  validation, pack-drift check, and `action.*` evidence are all unchanged.
- The flag is set only by `--mode fastevolve`; no pack content can enable it.

## 4. Mid-run promotion contract

`evolve.promote_candidate(candidate_path, pack_id, state_dir, *, mid_run=True)`:

- Re-validates the candidate (`validate_candidate`, fair rules apply).
- Writes a parent backup under `packs/candidates/parent-<id>-<hash>.yaml`.
- Atomically installs over the pack file; appends a `promoted` lineage row
  with `mid_run: true` to `state/mutations.jsonl`.
- Caller MUST then `dispatcher.load_pack(pack_id)` — rebinding the recorded
  hash keeps `dispatch.pack_drift` sound.
- The episode-scoring auto-revert check in `boundary()` does not apply
  mid-run; it still runs at the next run boundary over the promoted pack.

## 5. Events

Payloads per `data-model.md`. Consumers: `feed.py` narration (one line per
event), `views.py` `fastevolve` block (`{day, anchor, reloads_used,
max_reloads, exhausted}` in `planning.json`), `audit.py` event-type list
(extended with the six `fastevolve.*` types).
