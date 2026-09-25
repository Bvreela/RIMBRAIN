# Contract: Pack schema v1 + v0→v1 migration

**Feature**: 017 | **Producer/consumer**: `templates.load_pack` | **Scope**: all `packs/*/pack.yaml`

## v1 shape

```yaml
schema_version: 1
meta:        {pack_id, revision, class: fair|dev}
capabilities: {templates: [...]}                    # unchanged vocabulary
senses:      {...}                                  # observation config (site, vitals cadence, enrich)
reflexes:    [{id, priority, when, action}]         # pre-decide emergencies, policy.check dialect
rules:       [{id, when, action}]                   # standing invariants
phases:
  - id: init
    prescriptive: true
    steps: [...]                                    # ordered verified steps
    complete: {all: [...], fix: {...}}              # exit contract + fallback chains
  - id: <name>
    goals: [...]
    action_list: {scope, max_items, priority, fallback}
standing_goals: [...]                               # ex-govern.goals
options:       [...]                                # ex-goal_options
decide:
  select: {role: rimbrain.select, batch_pawns: true, fallback: priority_head, shadow: true}
  plan:   {role: rimbrain.plan, cadence_s: 150, on_phase_boundary: true, on_events: [...]}
mutate:      {...}                                  # 016 cfg unchanged
metrics:     {...}                                  # vitals + efficiency windows
```

## v0 → v1 migration map (in-memory at load)

| v0 path | v1 path |
|---|---|
| `templates` | `capabilities.templates` |
| `emergency[]` | `reflexes[]` (condition→`when` via dialect adapter) |
| `universal.rules` | `rules` |
| `universal.idle_patterns`/`chase_skill` | `senses.*` / `decide.select.*` |
| `start.site/shelter/food/...` cfg blocks | `senses.*` / `phases[0].cfg` (paths preserved — resolvers still find `@cfg:start.*` via alias map) |
| `start.phases` | `phases[0]` (`id: init, prescriptive: true`) |
| `start.exit` | `phases[0].complete` |
| `govern.<cfg>` (research/missions/hunt/power/blueprints/...) | `senses.govern.*` alias or `phases[].cfg` — resolved via alias map so `@cfg:govern.*` still resolves |
| `govern.goals` | `standing_goals` |
| `goal_options` | `options` |
| `cycle` | dropped (dev harness config moves to `dev-lab` pack / `--dev` only) |
| `jobs`, `decision_map` | dropped (dead fields — schema stops requiring them) |

## Rules

- Migration is load-time only; `pack.yaml` on disk is never rewritten by the loader.
- `mutate`/`evolve` ops address **v1 paths**; ops targeting v0 paths are rewritten through the same map before `packmut.apply_ops`.
- `schema_version > 1` rejected; `schema_version` absent ⇒ 0 ⇒ migrate.
- Pack hash is computed on the *normalized* (post-migration) doc so v0 file edits and v1 candidates hash consistently.
- cfg alias map preserves `@cfg:start.*`/`@cfg:govern.*` resolvers inside migrated packs — step bodies do not need rewriting on migration.
