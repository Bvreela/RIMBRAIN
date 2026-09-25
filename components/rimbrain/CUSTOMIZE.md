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

## Pack anatomy (v1 — feature 017)

`schema_version: 1` packs are one document with seven surfaces:

```yaml
meta:               # pack_id, revision, class (fair|dev)
capabilities:
  templates:        # the ONLY actions the agent can ever take
    - id: firefight
      method: ui.job            # bridge RPC — sealed inventory only
      params_schema: {...}      # JSON Schema checked BEFORE writes
  fns: [...]        # capability primitives the pack may call
phases:             # lifecycle — prescriptive init steps, then
                    # goal-driven phases, in order
  - id: init
    prescriptive: true          # runs its steps verbatim, no model
    steps: [...]
  - id: stabilize
    goals: [{id: ..., effect: ..., steps: [...]}]
standing_goals:     # govern goals that re-arm on effect lapse
options:            # planner catalog the BigBrain may promote
decide:             # model wiring
  select: {role: rimbrain.select, fallback: priority_head,
           shadow: true}
  plan:   {role: rimbrain.plan, cadence_s: 150,
           on_phase_boundary: true}
reflexes:           # fire before any model is asked
rules:              # per-poll pawn/colony rules (@for_each etc.)
```

v0 roots (`templates`, `emergency`, `decision_map`, `start.phases`,
`govern.goals`) migrate automatically at load — `runtime.templates`
rewrites them into the v1 shape and `@cfg:` aliases keep old paths
resolving. Legacy flat packs still load; mutation ops written against
v0 paths are rewritten through the same map.

## The edit → reload → verify recipe

1. **Edit** a value — e.g. change a site weight or a zone size.
2. **Reload** — packs load at run start (`python -m runtime loop --pack <name> ...`), or live: pick a pack in the overlay's dropdown and hit **Use** — the running brain wipes its planning state and re-derives goals from the colony with fresh eyes under the new pack (needs `--live-brain`, on by default in `rimbrain run`). Bad edits refuse with a plain-language error naming the file and field.
3. **Verify** — run the sim (`--mode run --game sim --iterations 5`) and read `state/feed.md` to see the change narrated, or diff `state/events.jsonl` before/after. Sim is deterministic: same seed → byte-identical event stream, zero endpoint calls.

**Editing mid-run does nothing** — the active pack is snapshotted at load and its hash rides in every event. Change lands next run (or next overlay **Use**/Brain Reset). This is deliberate: policy can't shift under a scored episode.

## Live mutation (features 016+017)

`--live-mutate` (on in the `rimbrain run` default) lets the brain reflect
on its own run: when a goal fails/expires, near-failure signals cluster
(requeues, refusal bursts, stalls, escalations, defect-pattern hits), or
every `mutate.goals_per_pass` terminal goals, a reflection pass fires in
the unified loop's **reflect stage** (`runtime/evolve.py`).
The `rimbrain.improve` model gets a bounded failure digest and proposes
pack mutations (`set`/`append`/`remove`/`upsert` ops over any whitelisted
pack surface — `phases`, `action_list`, `decide`, `reflexes`, `rules`,
`options`, `senses`, `metrics`; v0 paths rewrite through the migration
map); a single deterministic gate re-validates schema + sealed inventory
+ fair class + budget, then writes a **candidate** — never the active
pack. At the next run's boundary the pending candidate is re-validated
and installed, with the parent file backed up; if that episode scores
worse than baseline the pack auto-reverts. All of it is narrated in
`feed.md` and tallied in `state/mutations.jsonl` + the `mutation` block
of `planning.json`.

Tune it in the pack's `mutate:` section (thresholds, cooldown, model-call
budget). If `rimbrain.improve` resolves to a bare `rules-only` fallback
the pass degrades to the improve pack's declared defect-pattern
remediations — still deterministic, still gated.

## Fast-evolve play mode (feature 021)

`--mode fastevolve` is a daily save-scum adaptation loop: each in-game
day anchors to the autosave nearest day start (`game.list_saves` +
`fastevolve.autosave_pattern`). When a `fastevolve.triggers` predicate
(`fail_when`/`near_when` over observed state, optionally plus the
`mutate:` goal-level triggers) fires, the game pauses, one reflection
pass runs, a gated candidate promotes **immediately** (mid-run, ADR-020
— the controlled exception to boundary-only promotion), the anchor
reloads, and the day retries under the evolved brain. At most
`max_reloads_per_day` reloads (default 2 → three attempts); an exhausted
day still evolves but moves on, keeping the last evolved pack.

Fair protections stay on inside the mode — `dev.*` stays refused; only
`game.save`/`game.load` get a scoped grant. Scored episodes refuse the
mode at launch (`loop.fastevolve_scored`), as does `--dev`
(`loop.fastevolve_requires_fair`). Retry state lives in
`state/fastevolve.json` (survives restarts and the post-reload wipe);
`planning.json` shows the `fastevolve` block; the feed narrates every
`fastevolve.*` event.

Tune it in the pack's `fastevolve:` section: reload budget, autosave
pattern, scan cadence, anchor age bound, pause behavior, per-day
reflection budget, and the trigger predicates — all pack data, validated
at pack load.

## Combat capability (feature 019)

`combat-defense-v0` is the fair-class defense pack: the Steward `combat`
standing order executes (draft → rally → hold → overrun → release) and
the pack steers it. Tune the `combat:` cfg block — `engage_radius` /
`overrun_radius` (classification radii), `near_hostile` (retreat safety
bound), `release_ticks`/`prolonged_ticks` (lifecycle windows),
`min_health` + `allow_unarmed` (fighter floors), `relief` (need
thresholds for standing down), `engage_odds_floor` (when to shelter
instead of fight), `chase_skill` (skill gate for chase/block options),
`assault_duties`/`watch_lords`/`manhunter_mental` (threat vocabulary),
`delegate_order` (which order to steer), `option_weights` (per-option
priority).

Per-pawn options live under `decide.select.pawn_scope` — `combat-retreat`
(outranged/outrun/hurt → safe cell), `combat-relief` (low needs → stand
down), `combat-block` (melee breach plug), `combat-focus` (nearest
hostile), `combat-chase` (fleeing pursuit), `combat-kite` (range+speed
edge), `combat-move` (rally cell). Each `when`/`needs` clause is
pack-editable; `option_weights` sets fallback priority. The
`combat-evidence` rule appends posture snapshots + lifecycle markers
(`combat.overrun`/`combat.prolonged`/`combat.released` with duration,
peak hostiles, casualties) to `decisions.jsonl`.

Dev-class packs keep the scripted harness under `combat:` (checkpoint/
spawn/rounds) and get the cfg surface via `dev_combat:` — see
`dev-lab-v0` for the shape.

## Rooms & archetypes (feature 020)

Rooms are declared in the pack's `rooms:` block — **archetype data only**;
the runtime compiles them to build ops and verifies them on observed
role/stats. `plan_room(rect, archetype_id)` is the compile primitive
(`ops:` of any `build-layout` step can be `"@fn:plan_room(@var:site.rect,
<archetype>).ops"`), and room goals must verify with role/stat predicates
(`room_role_at`/`rooms_matching`/`room_stat`) — an `enclosed_at`-only
effect on a room goal is a load-time error (SC-2004).

An archetype is:

```yaml
rooms:
  tier_table: auto          # auto | vanilla | realistic_rooms_rewritten
  archetypes:
    bedroom:
      size: {w: 4, h: 6}    # interior footprint — or tier_target: average
      stat_target: {impressiveness: 40}
      wall: Wall
      door: Door
      floor: Carpet         # TerrainDef; null = no floor ops
      furniture:
      - {def: Bed, count: 1, anchor: wall}
      - {def: Dresser, linked_to: Bed}        # within linkable_range
      - {def: EndTable, linked_to: Bed}
      - {def: StandingLamp, count: 1}
      - {def: PlantPot, optional: true}       # skip, never fails the room
```

Furnishing rules: `count`, `anchor` (`wall`/`corner`/`center`/`free`),
`linked_to` (def within the item's link radius), `adjacent_to`,
`separate` (keep ≥2 cells from other furnishing — butcher/stove),
`optional`, `links` (one instance per N link targets — tool cabinet ≤2
benches), `at` (`each_<def>` places one item per matching placed target —
workshop stool per bench). `tier_target` sizes the footprint to the
resolved space-tier profile instead of `size`.

**Space-tier profiles (US3):** `tier_table: auto` reads the live
`defs.get(Space).scoreStages` (modded thresholds win automatically),
falls back to the declared `mods.realistic_rooms_rewritten.settings`,
then vanilla — with one `rooms.profile_fallback` event per run when
detection is inconclusive. `mods.*` are declared cfg only; live detection
always wins. `space_tier(score)`/`space_target(tier)` expose the resolved
table to goals.

**Need-driven support rooms (US4):** `when` gates on `pawns_with_thought(
AteWithoutTable)` (dining), `pawns_wounded()` ≥ `govern.hospital.
need_threshold` (hospital), cookstation readiness (kitchen), a research
bench (workshop) — effects verify role + the archetype's `stat_target`.

## Guided editor (feature 018)

**Edit Brain** on the launcher's Setup screen opens the selected pack in a
guided editor: an outline of sections/phases on the left, typed controls
for scalars, a predicate builder, and template-dropdown + `params_schema`
rows for steps — plus a Raw YAML tab when you want the file itself.

Save writes a **new sibling pack**, never the source: `packs/<name>/pack.yaml`
with `pack_id: pack.<name>` and `derived_from: <source pack id>`, so lineage
survives in the pack list. Saving under the *currently running* pack's name
requires an explicit confirm — it hot-swaps the live brain (write +
`brain_reset.request {}`). `packs/candidates/` stays reserved for the
improvement loop.

## Safe editing rules

- **Refusals are information, not failures.** A pack that won't load tells you exactly what it didn't like — read `action.refused`/`load` errors, fix the named field.
- **Every method must be in the sealed bridge inventory.** Invented RPC names are rejected at load — check `baselines/upstream-85cb050/` for the real surface.
- **Emergency reflexes never need a model.** Keep them deterministic; thresholds live in `predicates` values.
- **Candidate packs** land in `packs/candidates/` — the improvement loop's proposals and your experiments both. Promote deliberately: copy a validated candidate over the named pack, then run it.

## Watching the agent think

`python -m runtime loop --mode run --game sim --feed` writes
`state/feed.md` — one plain-language entry per decision: what it saw,
what it planned, what it did, what it learned. The overlay shows the
current phase, the last select pick (with fallback/shadow marker), and
the in-force planner decision with its staleness.

## Where to start (recommended first edits)

- `start-mode-v0/pack.yaml` → `start.food.plant`: swap `Plant_Rice` for `Plant_Potato`.
- `core-survival-v0/pack.yaml` → emergency thresholds (e.g. fire count).
- `improve-v0/pack.yaml` → `metrics.weights`: tell the loop what "better" means to you.
