# Data Model: Combat Capability

## Entities

### CombatMode (pack cfg + per-poll derived value)

Colony-level combat posture, recomputed each poll by `combat_mode()`:

```
watch | engage | hold | overrun
```

Transitions (all thresholds are `@cfg:combat.*`):

- `watch → engage`: any hostile classified engaged (in Home, ≤ engage_radius of rally, assault-duty lord, manhunter-while-colonist-outside)
- `engage → overrun`: hostile inside Home or ≤ overrun_radius of rally center
- `engage/overrun → watch`: engaged set empties
- `any → release` (not a mode — a release event): `living_hostiles` empty for ≥ `release_ticks`

### ThreatRow (observation unit — `state.threats` hostile entry)

| field | type | notes |
|---|---|---|
| id | string | pawn/thing id |
| pos | [x, z] | |
| def, kind | string | race/thing def |
| faction | string | never player/home factions |
| dead, downed, fogged | bool | all exclude from engagement |
| dist_home | number | |
| weapon | string | def name → `defs.get` for range/class |
| health | 0-100 | |
| lord | string | LordJob class (`LordJob_Siege` …) |
| mental | string | e.g. `Manhunter` |

### FighterEligibility (per-pawn predicate set)

spawned ∧ ¬dead ∧ ¬downed ∧ ¬prisoner ∧ ¬slave ∧ ¬juvenile ∧ violence-capable ∧ has drafter ∧ ¬touched ∧ managed-ok ∧ health ≥ `min_health` ∧ (armed ∨ `allow_unarmed`) — pack cfg owns the floors.

### CombatOption (pack-declared pawn candidate)

```yaml
- id: <name>              # e.g. kite-step
  template: <template id> # resolves to bridge method
  when: <predicate>       # gate: pawn fit × enemy mix × mode
  needs: <expr>           # optional resolver gate
  priority: <expr>        # fitness score → fallback ordering
  params: {…}             # @fn:/@var:it resolved at compile
```

Compiles to `cands[]` entry `{id: "pawn.<pid>.<oid>", scope: "pawn", dispatch: {template, params}}` — one pick per pawn per decide poll.

### Rally (pack cfg)

```
rally_anchor | rect | 13×13-around-base-center (fallback)
cell assignment: cover-first score → greedy spread (min-dist cap 4) → center bias
```

## Validation rules

- Candidate list ≤ 20 total across colony+pawn scopes (engine `HARD_MAX`).
- `engage`/`overrun`/`release` radii and tick windows are positive ints in `combat:` cfg.
- Option `template` must resolve to a catalog template; `params` satisfy its `params_schema`.
- Downed/dead/fogged hostiles can never satisfy `needs` for attack options.
- `release` never undrafts pawns the brain didn't draft (manual-touch carry-over).

## State transitions (per pawn, order-observable)

`undrafted → drafted (order or override) → holding-at-rally → attacking (overrun) → released (undrafted, area restored)`
side-paths: `drafted → relieved (needs floor, no hostile near) → redrafted (recover threshold)`; `any → retreating (health/bleeding override)`; `any → downed → rescued`.
