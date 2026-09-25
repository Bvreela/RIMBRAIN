# Combat capability contract

**Status:** DRAFT
**Contract ID/version:** combat-capability/v0
**Provider:** runtime policy/select substrate + RimBridge (`steward.orders.*`, `ui.*`, `state.threats`, `state.pawn`, `map.*`, `defs.get`)
**Consumers:** RimBrain packs (fair-class `combat-defense-*`; dev `dev-lab-v0` harness)
**Requirement IDs:** FR-1901..1910, SC-1901..1906

## Purpose

Defines the pack-facing surface for colony combat: the `combat:` cfg block, the per-pawn option vocabulary inside `decide.select.pawn_scope`, the new fns/selectors, and the delegation contract with the Steward `combat` standing order.

## Operations/events/artifacts

**Pack cfg block** (`combat:` — pack schema v1 extension):

```yaml
combat:
  rally_anchor: <anchor-name>      # else 13x13 around base center
  engage_radius: 40                # cells from rally center
  overrun_radius: 5
  near_hostile: 30                 # relief suppression radius
  release_ticks: 600               # hostile-free stand-down window
  prolonged_ticks: 30000           # evidence escalation
  min_health: 30                   # draft floor, percent
  relief: {food: 15, rest: 15, recover: 50}
  allow_unarmed: false             # draft unarmed pawns
  engage_odds_floor: 0.5           # our_power/enemy_power below → watch/shelter
  power_overrides: {}              # def → combat-power pts (wiki defaults else)
  option_weights: {}               # option id → priority multiplier
  chase_skill: 6                   # min melee skill for chase-fleeing
  assault_duties: [AssaultColony, PrisonerAssaultColony, Breaching,
                   Sapper, Escort, Kidnap, Steal,
                   HuntEnemiesIndividual, AssaultThing, NestAssault]
  watch_lords: [LordJob_Siege]
  manhunter_mental: Manhunter
  delegate_order: combat           # steward order id | null = pack owns all
```

**Option vocabulary** (`decide.select.pawn_scope.options` entries; standard option fields):

`hold-rally` (move-pawn→rally_cell), `attack-nearest` (attack-target), `kite-step` (move-pawn→kite_cell), `melee-block` (move-pawn→block_cell), `chase-fleeing` (attack-target), `retreat` (move-pawn→safe_cell), `relieve` (draft-pawn false), `shelter` (set-area Home), `field-tend`, `rescue-downed`, `capture`, `ingest-drug`, `strip` (designate).

**New templates** (catalog entries; bridge methods sealed): `move-pawn`→`ui.goto`, `cancel-job`→`ui.cancel_job`, `set-area`/`set-hostility`→`ui.set_policies`, `press-gizmo`→`ui.press`, `order-pawn`→`ui.order`, `field-tend`/`capture`/`ingest-drug`→`ui.job`, `designate-hunt`→`ui.designate`, `animal-guard`→`ui.animal`, `rally-set`→`steward.orders.rally`, `order-run`→`steward.orders.run`, `combat-release`→`steward.orders.release`.

**New fns/selectors**: `combat_mode()`, `engaged_hostiles`, `watching_hostiles`, `hostiles_in_home()`, `hostiles_within(cell|r)`, `draftable(id|list)`, `fighters()`, `rally_cell(pawn)`, `kite_cell(pawn)`, `block_cell(pawn)`, `safe_cell(pawn)`, `weapon_stats(def|thing)` → `{class, range, dps, warmup, cooldown, burst}`, `outranges(p,h)`, `outrun_by(p)`, `outranged_by(p)`, `speed_of(id)`, `need_of(id, need)`, `health_of(id)`, `ticks_since_hostile()`, `nearest_fleeing(p)`, `skill_of(id, skill)`, `in_range(p,h)`, `enemy_mix()`, `enemy_max_range()`, `threat_power()`, `manhunters()`, `free_beds(kind)` — `kind` ∈ `any|medical|prison`, `casualty_ids()`, `pawns_needing_tend()`, `order_state(order)` → `{enabled, engaged, overrun, last}`.

**Evidence**: engagement lifecycle is read off the steward order ledger — `order_state(order).last` surfaces `combat_engaged`/`combat_released`. `combat.overrun`/`combat.prolonged` are decision-row markers emitted by pack rules on `order_state` transitions — evidence rows, not canonical event types (no event-map entries in v0) — plus existing decide records (`select.invalid`/`degraded`, per-pick rows).

## Request/input schema

- Options: `decide.select.pawn_scope` block per `contracts/select-batch.md`; each option `{id, template, when?, needs?, params?, priority?, label?}`.
- Fn signatures as listed; all resolve via `policy.resolve`/`policy.select` — string `@fn:name(args)` form.
- Cfg validation: positive ints for radii/ticks; `min_health`/`relief.*` percents 0-100; `chase_skill` 0-20; `engage_odds_floor` positive float; `allow_unarmed` bool; `power_overrides`/`option_weights` string→number maps; `delegate_order` ∈ known order ids or null.
- `rescue-downed` gate approximates route safety via `hostiles_within(casualty, near_hostile)` — no pathing fn in v0.

## Result/output schema

- Per-pawn pick → `dispatcher.dispatch(template, params)` result `{ok, …}` recorded on the decision row.
- Order steering calls return the steward RPC result; `order_state` is read-only projection — the order is never written except through `steward.orders.*`.

## Identity, revisions, and correlation

Candidates keyed `pawn.<pid>.<oid>`; decision rows carry `tick`/`poll`/`phase`/`inputs_hash`. Combat cfg changes are pack edits → `dispatch.pack_drift` freeze applies as with any pack.

## Ordering and consistency

Rules fire before the decide stage each poll (existing loop order). Order steering (`rally-set`, `order-run`) and pawn overrides may interleave — the order skips touched pawns for its own cooldown; the pack MUST NOT rely on the order honoring an override it will later re-steer (overrides are the exception path, order state is re-read next poll).

## Timeouts, cancellation, and retries

- Release = `release_ticks` hostile-free — hysteresis, not instant.
- Relief: needs < floor AND no hostile within `near_hostile` AND mode ≠ overrun; re-draft only when both needs > `recover`.
- Combat options have no per-option cooldown field — use `ticks_since_hostile`/rule cooldowns or the order's own 250-tick re-issue cadence.

## Idempotency

`draft-pawn`/`move-pawn`/`attack-target` re-issue harmlessly (game coalesces same-job). `rally-set` is declarative. Overrides on a touched pawn are no-ops while another writer's touch stands.

## Error/failure semantics

- Ineligible gate → option never compiles (no error).
- Dispatch refusal (downed draft, unreachable cell, unfogged-only) → `{ok:false}`, recorded; fallback never issues a refused write twice per poll.
- Endpoint down/invalid pick → `priority_head` fallback per select contract.
- `defs.get` miss on enemy weapon → `weapon_stats` null → `outranges`/`kite` gates evaluate false (conservative).
- `order_state` surface gap → missing fields read `null` → gates on them evaluate false (same conservative rule); `combat_mode`/classification fns are unaffected — they read `state.threats`, not the order.
- Per-pawn `touched` state unreadable → pawn treated as touched (excluded) — conservative under FR-1907; the delegate order still fights the battle.

## Security and privacy classification

Fair-class surface — no `dev.*` anywhere in this contract. No secrets.

## Compatibility/versioning

v0 contract; additive to pack schema v1 (`combat:` block optional). `delegate_order` defaults to the `combat` order when present; packs may set null to opt out (pack owns every write — unsupported well, allowed).

## Canonical valid examples

```yaml
decide:
  select:
    pawn_scope:
      for_each: colonists
      options:
        - id: retreat
          template: move-pawn
          when: {field: "@fn:health_of(@var:it)", op: lt, value: "@cfg:combat.min_health"}
          priority: 90
          params: {pawn: "@var:it.id", cell: "@fn:safe_cell(@var:it)"}
```

## Canonical invalid examples

- Option `when` gating on `@var:it` outside `pawn_scope` (no `it` binding at colony scope) → never compiles.
- `attack-target` with `needs: "@fn:downed_ids()"` → refuses downed target by contract (FR-1903 predicates exclude them).
- `combat.delegate_order: bogus-order` → load-time validation error.

## Provider tests

- fns return correct values over fixture obs (engaged vs watching classify, draftable, rally_cell distinctness, outranges sign).
- Option compile: gates prune, priorities order, ≤20 bound holds at 15 colonists.
- Delegate path: `steward.orders.*` calls dispatch through the single writer; `order_state` projects into obs.

## Consumer tests

- Pack with `combat:` block loads, migrates, and validates; a pack omitting it is unaffected.
- Sim raid: draft→rally→overrun→release lifecycle; no downed/fogged/friendly targets.
- Endpoint-down poll: fallback assignments equal deterministic best.

## Migration

No migration — net-new pack surface. `dev-lab-v0` combat phase unchanged (dev class). A later LOS/cover RPC is additive: new fns, no breaking change.
