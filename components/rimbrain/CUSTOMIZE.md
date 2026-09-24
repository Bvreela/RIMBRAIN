# Customizing the brain

Everything the agent *believes* lives in this directory as plain YAML —
no code changes needed to change behavior. The agent **learns by
changing these files** (as candidate packs it must prove out), and you
can too.

Each pack is a folder: `packs/<name>/pack.yaml`, with aux files (notes,
experiments) beside it. A pack id is its folder name — `start-mode-v0`
loads `packs/start-mode-v0/pack.yaml`. Flat `packs/<name>.yaml` still
loads for compatibility (candidates materialize flat).

## What you can edit

| File | What it controls |
|---|---|
| `packs/core-survival-v0/pack.yaml` | Everyday policy: action templates, decision map, emergency reflexes, fallback plan |
| `packs/start-mode-v0/pack.yaml` | Fresh-start bootstrap: site weights, shelter dims, food/recreation choices, exit contract |
| `packs/improve-v0/pack.yaml` | Self-improvement: defect patterns, metric weights, audit gates, cycle cadence |
| `../../profiles/endpoints.yaml` | Model endpoints (which models exist, where) |
| `../../profiles/bindings.yaml` | Role → endpoint bindings (who plans, who reviews, who narrates) |

## Pack anatomy (core-survival)

```yaml
templates:          # the ONLY actions the agent can ever take
  - id: firefight   #   name the decision map / reflexes reference
    method: ui.job  #   bridge RPC — must exist in the sealed inventory
    params_schema:  #   JSON Schema checked BEFORE any game write
      required: [pawn, work, cell]
emergency:          # reflexes — fire before any model is asked
  - id: fire-fight
    priority: 1
    condition: {combinator: all, predicates:
      [{field: map.fires, op: gt, value: 0}]}
    action: {template_id: firefight, params: {...}}
decision_map:       # model choices -> templates (unmapped = refused)
fallback_plan:      # what the planner emits when models are offline
```

## The edit → reload → verify recipe

1. **Edit** a value — e.g. change a site weight or a zone size.
2. **Reload** — packs load at run start (`python -m runtime loop --pack <name> ...`), or live: pick a pack in the overlay's dropdown and hit **Use** — the running brain wipes its planning state and re-derives goals from the colony with fresh eyes under the new pack (needs `--live-brain`, on by default in `rimbrain run`). Bad edits refuse with a plain-language error naming the file and field.
3. **Verify** — run the sim (`--mode sim --iterations 5`) and read `state/feed.md` to see the change narrated, or diff `state/events.jsonl` before/after.

**Editing mid-run does nothing** — the active pack is snapshotted at load and its hash rides in every event. Change lands next run (or next overlay **Use**/Brain Reset). This is deliberate: policy can't shift under a scored episode.

## Live mutation (feature 016)

`--live-mutate` (on in the `rimbrain run` default) lets the brain reflect
on its own run: when a goal fails/expires, near-failure signals cluster
(requeues, refusal bursts, stalls, escalations, defect-pattern hits), or
every `mutate.goals_per_pass` terminal goals, a reflection pass fires.
The `rimbrain.improve` model gets a bounded failure digest and proposes
pack mutations (`set`/`append`/`remove`/`upsert` ops over any pack path);
a deterministic gate re-validates schema + sealed inventory + fair class,
then writes a **candidate** — never the active pack. At the next run's
boundary the pending candidate is re-validated and installed, with the
parent file backed up; if that episode scores worse than baseline the
pack auto-reverts. All of it is narrated in `feed.md` and tallied in
`state/mutations.jsonl` + the `mutation` block of `planning.json`.

Tune it in the pack's `mutate:` section (thresholds, cooldown, model-call
budget). If `rimbrain.improve` resolves to a bare `rules-only` fallback
the pass degrades to the improve pack's declared defect-pattern
remediations — still deterministic, still gated.

## Safe editing rules

- **Refusals are information, not failures.** A pack that won't load tells you exactly what it didn't like — read `action.refused`/`load` errors, fix the named field.
- **Every method must be in the sealed bridge inventory.** Invented RPC names are rejected at load — check `baselines/upstream-85cb050/` for the real surface.
- **Emergency reflexes never need a model.** Keep them deterministic; thresholds live in `predicates` values.
- **Candidate packs** land in `packs/candidates/` — the improvement loop's proposals and your experiments both. Promote deliberately: copy a validated candidate over the named pack, then run it.

## Watching the agent think

`python -m runtime loop --mode sim --feed` writes `state/feed.md` —
one plain-language entry per decision: what it saw, what it planned,
what it did, what it learned. `improve` mode narrates its own
reasoning the same way.

## Where to start (recommended first edits)

- `start-mode-v0/pack.yaml` → `start.food.plant`: swap `Plant_Rice` for `Plant_Potato`.
- `core-survival-v0/pack.yaml` → emergency thresholds (e.g. fire count).
- `improve-v0/pack.yaml` → `metrics.weights`: tell the loop what "better" means to you.
