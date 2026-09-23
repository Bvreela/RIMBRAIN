# Plan: Brain Policy Engine (feature 012)

## Approach

One new module `runtime/policy.py` implements the primitive vocabulary; the three mode modules become interpreters over pack data; the shipped pack absorbs all current policy verbatim.

## Design

### policy.py

- `resolve(spec, ctx)` — recursive. Strings: `@cfg:a.b`, `@obs:a.b`, `@var:name` / `@var:name.idx`, `@fn:name(arg,…)` (args are themselves resolvable or literals). Dicts/lists resolve element-wise. `ctx` = `{cfg, obs, game, site, vars, state, tick}`.
- `FN` registry — pure capability functions, signature `(ctx, *args)`:
  - math: `add`, `sub`, `mul`, `fdiv`, `neg`
  - geometry: `cell(x,z)`, `rect(x,z,w,h)`, `near_home(dx,dz)` (threats home_center)
  - collections: `ids(list)`, `first(list)`, `count(list)`
  - obs lookups: `anchor(name)`, `map_find_id(kind_or_def, radius?)`, `loose_id()`, `loose_ids()`, `forbidden_ids()`
  - world scans: `fertile(rect)` (map.cell fertility grid), `stuff(prefs)` (first available), `hostile_faction()`, `best(selector_or_list, skill)`, `unarmed()`, `arm_match(field)` → `{pawn, weapon}` cached per ctx (`arm_pawn`/`arm_weapon` accessors), `downed_hostiles()`, `living_hostiles()`, `fleeing_hostiles()`, `colonist_ids()`, `site_min/rect` via `@var:site`
  - `need` (resolved effect value) exposed as `@var:need` for repeat guards
- `check(pred, ctx)` — `field`/`value` resolved via `resolve`; ops listed in spec; `all`/`any`/`not` combinators. Missing field → `False` (fail-closed) except `empty`/`not_empty` which tolerate absent lists.
- `run_steps(steps, dispatcher, ctx)` — per step: `for_each` selector iterates candidates into `@var:it`/`@var:index`; `when` predicate gates; `needs` resolver must yield truthy; `cooldown_polls` keys on template+resolved-params-hash in ctx.state. Collect results; first non-optional failure aborts the step list.
- `run_rules(rules, dispatcher, ctx, state)` — per rule: select candidates (`for_each` string → SELECTORS registry, or `{from: sel, where: pred}`), filter by `when`, skip cooled keys, run `try` alternatives in order (first whose `needs`+`when` resolve and dispatch is attempted), record cooldown key per candidate/rule.
- `SELECTORS` registry — `colonists`, `idle_colonists` (job contains any of `cfg.universal.idle_patterns`), `unarmed_colonists`, `hostiles`, `living_hostiles`, `downed_hostiles`, `fleeing_hostiles` (dist-trend state in `ctx.state`), `items`, `forbidden_items`, `armor_items`.
- `validate_policy(pack)` — walk phases/rules/steps: every `@fn`/`@var`/`@cfg` selector/op/template id must exist; returns error list (fail-closed at pack load or first run).

### startmode.py

- `observe_start` unchanged (capability metrics).
- `StartMode.step`: `phases = cfg["phases"]` — each `{id, set?, adopt?, effect, steps, repeat?}`:
  - `set: {var: resolver}` binds ctx vars (e.g. `site` ← `rank_site`); `adopt: {var, from_anchor}` restores persisted world state after reload.
  - `effect` predicate → skip-path/`_check_effect` equivalent.
  - `repeat` guard predicate gates re-dispatch while effect unmet (blueprint-deficit logic becomes a predicate).
  - steps run via `run_steps`.
- `exit_eval`: `conditions` map iterated generically — keys are pack-chosen names.
- `BOOTSTRAP`/`BASELINE`/`_effect_of`/`_dispatch`/`_inject`/`_dispatch_arm`/`_meal_target`/`_scan_arm` deleted — policy moves to the pack; capability helpers (`rank_site`, `_pick_stuff`, `_fertile_rect`, `_scan_arm` internals) move into `policy.py` FN impls.

### combatmode.py

- `run_combat` = prereq check → `run_steps(combat.setup)` → per round: `run_steps(combat.spawn)` → engage loop (`until` predicate each poll; universal rules + `combat.engage.rules` applied; speed re-assert retained as runtime safety) → `run_steps(combat.cleanup)`. Spawned/cleared/casualty/verdict accounting stays.

### universal.py

- Shrinks to `apply_rules(...)` delegating to `policy.run_rules` with `universal.rules` from the pack; helper predicates (`is_downed`, `fleeing` trend) move into `policy.py` as FN/selector internals.

### Pack (`start-mode-v0.yaml`)

- `policy_version: 1`.
- `start.phases`: 13 declarative phases mirroring today's behavior.
- `start.exit.conditions`: five named predicates.
- `universal.rules`: idle-work, strip-downed, chase-fleeing (+ `idle_patterns`).
- `combat`: `setup/spawn/engage/cleanup` script.

## Risks

- DSL expressiveness gaps → add primitives, never hacks (per spec boundary).
- Test fixtures assert old code paths — rewrite to assert pack-driven outcomes.
- `validate_policy` must be invoked at pack load so bad packs fail before the game does.

## Tasks → tasks.md (T155+)
