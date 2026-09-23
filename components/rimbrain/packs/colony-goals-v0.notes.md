# colony-goals-v0 — companion notes

## Grouping

19 goals, ordered along the survival arc the guide itself follows:

- **Immediate (early):** shelter, food, arming, chokepoint defense — the day-one
  bootstrap, aligned with `start-mode-v0`'s phase order (site → shelter → food → arm).
- **Stabilization (early→mid):** medicine, mood, power, research, recruitment,
  compound wall — removes the failure modes that kill stabilized colonies
  (infection, mental breaks, no power, missing skills).
- **Growth (mid):** killbox, turrets, components, trade, export production.
- **Wealth management (mid→late):** `cap-idle-wealth` (control: don't accumulate)
  vs `invest-wealth-in-defense` (investment: spend into capability) — the two
  strategy classes the wiki's Wealth management page defines. Both are kept as
  separate selectable goals because they are mutually exclusive postures.
- **Endgame (late):** `sustain-post-raid-recovery`, `launch-ship-endgame`.

`prerequisites` reference goal ids only; colony conditions were avoided since no
predicate vocabulary for goals exists yet (see open questions).

## Verified mechanics (wiki)

- Storyteller Wealth = items + creatures + buildings×0.5.
- Wealth→points: 0 below 14k; ~1 pt per 160.83 wealth between 14k–400k; cap at
  1M wealth / 10k raid points. Pawn points add per-colonist points that scale
  with wealth (15 + (wealth−10k)/3120 per colonist, 10k–400k range).
- Raid Points = (wealth + pawn pts) × threat scale × starting factor × adaption
  (0.4–1.47; grows with days since a colonist was last downed/killed).
- Raid-type unlock thresholds: mech raids/drop pods ~300, infestations/mech
  clusters ~400, sieges ~500, sappers/breachers ~700. Ship reactor / Royal
  Ascent raids force min 500 points.
- Selling is always at ≤ market value → net wealth down; gifting destroys
  wealth for goodwill; caravan cargo doesn't count while off-map; weapon/item
  HP loss destroys market value (50% HP ≈ 10% value).
- Wiki caveat worth surfacing to the planner: wealth management "should not
  really matter on Strive to Survive or below" — it pays off mainly at
  ≥155–220% threat scale. The catalog still includes `cap-idle-wealth` because
  difficulty is a run parameter.

## Uncertain / unverifiable claims

- **Turret declumping** (`construct-killbox`): the guide claims an unpowered
  mini-turret at the corridor entrance makes raiders stack instead of flooding
  (02:09:57–02:12:37). This is a pathing observation, not a documented
  mechanic; treat as guide-attributed tactic, not guaranteed behavior.
- **Guide economics figures** (organ ~1783 silver/prisoner, flake vs yayo
  pricing, ~15–30 crops/pawn): transcript-stated, plausible, not independently
  verified on the wiki during this pass.
- **"Sell weapons at 20%" / never-sell-weapons passage** (guide ~03:28:32): the
  transcript is self-contradictory (says never sell, then says sell to clear
  space). Wiki guidance is smelt/destroy surplus weapons. Left out of the YAML;
  `cap-idle-wealth` covers the outcome.
- **Royalty/Archonexus ending** not included: guide treats the ship as the
  canonical win; royalty ending needs the DLC path.
- No goal carries `unverified: true` — all load-bearing claims are either
  wiki-verified or explicitly attributed to guide timestamps in `sources`.

## Open questions

- Should goals reference concrete template ids (e.g. `build-layout`,
  `add-bill`) from `start-mode-v0`/`core-survival-v0`, or stay capability-free
  strategy that a separate mapping layer binds to templates? Currently the
  latter — no `templates:` block in this pack.
- Is `phase` the right granularity, or should entries carry predicate
  conditions (`{field,op,value}`) so the planner can gate goals on observed
  state (e.g. "threat_scale ≥ 1.55", "days since last downing > 30")?
- Should `raid_threat_impact` get a numeric score field for ranking, or is the
  prose enough for a model-side planner?
- Does the observation layer expose colony wealth / raid-point proxies? Goals
  like `cap-idle-wealth` need a wealth signal to trigger.
