# Customizing the brain

Everything the agent *believes* lives in this directory as plain YAML —
no code changes needed to change behavior. The agent **learns by
changing these files** (as candidate packs it must prove out), and you
can too.

## What you can edit

| File | What it controls |
|---|---|
| `packs/core-survival-v0.yaml` | Everyday policy: action templates, decision map, emergency reflexes, fallback plan |
| `packs/start-mode-v0.yaml` | Fresh-start bootstrap: site weights, shelter dims, food/recreation choices, exit contract |
| `packs/improve-v0.yaml` | Self-improvement: defect patterns, metric weights, audit gates, cycle cadence |
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
2. **Reload** — packs load at run start (`python -m runtime loop --pack <name> ...`). Bad edits refuse with a plain-language error naming the file and field.
3. **Verify** — run the sim (`--mode sim --iterations 5`) and read `state/feed.md` to see the change narrated, or diff `state/events.jsonl` before/after.

**Editing mid-run does nothing** — the active pack is snapshotted at load and its hash rides in every event. Change lands next run. This is deliberate: policy can't shift under a scored episode.

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

- `start-mode-v0.yaml` → `start.food.plant`: swap `Plant_Rice` for `Plant_Potato`.
- `core-survival-v0.yaml` → emergency thresholds (e.g. fire count).
- `improve-v0.yaml` → `metrics.weights`: tell the loop what "better" means to you.
