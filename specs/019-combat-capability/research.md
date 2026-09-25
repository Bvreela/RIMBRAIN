# Research: combat capability primitive

Research extract for a combat capability/pack design (UR-BRN-011/013: all
tactics, thresholds, and decision rules live as pack data; runtime supplies
only capability primitives). Every mechanic below is mapped to the existing
pack vocabulary — `templates` (bridge verbs), `selectors`/`@fn:*` resolvers,
`{field, op, value}` predicates, `rules` (`for_each`/`when`/`try`/`needs`/
`cooldown`), `reflexes`, `govern.goals` — and tagged `[have]` (works today),
`[fn]` (needs a runtime resolver), or `[bridge-gap]` (needs bridge work).

## Sources

- `upstream/rimagent/mod-steward/Source/Steward/Orders/Order_Combat.cs` +
  `OrderLogic.cs` — production reference implementation of the whole decision
  model (detection, classify, draft, rally, hold, overrun, release).
- `upstream/rimagent/mod/Source/` — `UiRpc.cs` (ui.draft/goto/attack/job/order/
  press/set_policies/cancel_job), `StateRpc.cs` (state.threats/pawn/pawns/
  letters/factions/summary), `Snapshot.cs`/`Render.cs` (observed fields),
  `MapRpc.cs` (map.cell/path/reachable/view/detail/survey), `DefsRpc.cs`
  (defs.get/search).
- `upstream/rimagent/brain/skills/defense-basics.md`, `storyteller-and-threats.md`
  — distilled doctrine with verified numbers.
- `rimworld-complete-guide-transcript.txt` — tactics: kiting (01:58-02:05,
  02:52-02:55), melee block (02:07-02:11), killbox sizing (02:13-02:15),
  cover/weather (02:03-02:04), friendly fire (02:47-02:49), structures
  (02:49-02:52), shield/tank (02:58).
- rimworldwiki.com: Combat, Cover, Drafting, Weapons (firing cycle, accuracy,
  stopping power, melee formulas), Shooting Accuracy (per-tile curve), Move
  Speed, Defense tactics, Raider (victory conditions, raid variants).
- `baselines/upstream-85cb050/rpc-inventory.json` — sealed 115-method surface.

## 1. Observable state (what a pack can predicate on)

| Signal | Source | Fields usable in `when`/`@fn:` |
|---|---|---|
| Hostile list | `state.threats` | per hostile: `id`, `def`, `kind`, `pos` [x,z], `faction`, `dead`, `downed`, `dist_home`, `fogged`, `weapon` (def name), `health` (0-100), `lord` (LordJob class, e.g. `LordJob_Siege`), `mental` (e.g. `Manhunter`); plus `danger` (DangerRating), `threat_points`, `home_center` |
| Colonist brief | `state.pawns` / `state.summary.colonist_list` | `id`, `pos`, `downed`, `drafted`, `health` %, `job` (text), `mental_state`, `bleeding`, `needs_tending`, `mood`, `top_skills`, `weapon` (label) |
| Colonist detail | `state.pawn` | `skills` map (Shooting/Melee level+passion), `capacities` % (Moving, Manipulation, Sight, Consciousness), `pain`, `bleeding`, `needs` % (Food, Rest, Mood), `break_thresholds`, `equipment`/`apparel`/`inventory` (ids+defs), `allowed_area`, `hostility_response`, `job_detail`, `disabled_work` |
| Cell detail | `map.cell` | `terrain`, `fertility`, `roof`, `zone`, `home` (in Home area), `room`, `temperature`, `light`, `things` (cover objects: sandbags/walls/chunks), `fogged`, `walkable`, `standable`, `designations` |
| Geometry | `map.view`/`map.detail`/`map.survey`/`map.overview` | ASCII layers incl. `fog`, `pawns` (`!` hostiles), buildings, `home` |
| Pathing | `map.path` (cost/cells/straight), `map.reachable` (Some/Deadly) | `[have]` bridge, `[fn]` unwrapped |
| Def metadata | `defs.get`/`defs.search` | weapon verbs/stats: range, warmup, cooldown, burst, accuracy bands, damage, AP, stopping power, coverEffectiveness on buildings — `[fn]` unwrapped |
| Raid letters | `state.letters` | `def` (ThreatBig/ThreatSmall…), `label`, `text` (raid-variant wording: sappers/breachers/"unusually clever"/drop pods), `lookTargets` |
| Factions | `state.factions` | `hostile`, `defeated`, `tech` |
| Meta | `state.summary` | `wealth`, `danger`, `threat_points`, `alerts`, `hostiles` brief, `speed`, `paused` |
| Steward order | `steward.status`, `steward.orders(.explain)` | order enabled/last summary; `steward.orders.rally` rect |

Gaps worth noting: no direct LOS query (`map.los` doesn't exist — cover/LOS must
be derived from `map.cell`/`map.view` buildings+fog, or added bridge-side);
hostile `weapon` is a def name → range lookup needs `defs.get`; hostile move
speed is not exposed (race/kind → `defs.get` approximates).

## 2. Control surface → action templates

| Bridge verb | Params | Semantics |
|---|---|---|
| `ui.draft` | `{pawn, drafted}` | Instant. Errors: no drafter, downed. Interrupts job, drops carried items (except first-time baby). Drafted = ignores needs/zones/threat-response. Auto-undrafts after 10000 ticks with no threats/orders; mental break/downed ends it. Records `ui.draft` touch. |
| `ui.goto` | `{pawn, cell, draft?}` | Default `draft=true` (auto-drafts). Standable+reachable enforced; snaps to `BestOrderedGotoDestNear`. `JobDefOf.Goto` playerForced. Touch `ui.goto`. |
| `ui.attack` | `{pawn, target, melee?}` | Auto-drafts. `melee` defaults to weapon `IsMeleeWeapon` (unarmed counts as melee). `melee=true` → `AttackMelee`; false → `AttackStatic` with `endIfCantShootTargetFromCurPos=false` (holds position, waits for LOS/range). Sets `enemyTarget`. Touch `ui.attack`. |
| `ui.job` | `{pawn, job, target...}` | Combat-relevant jobs: `Rescue`, `TendPatient`, `Equip`, `Wear`, `Ingest` (go-juice), `LayDown`, `Capture`, `Goto`, `AttackMelee/AttackStatic`. Drafted-pawn jobs and attack/move jobs record touch `ui.job:<def>`. |
| `ui.order`/`ui.orders_at` | `{pawn, at, label|i}` | Context float-menu orders (Attack, Move, Capture, Strip…). On a drafted pawn records `ui.order.drafted:<label>`. |
| `ui.press` | `{thing, label|i, target?}` | Gizmo press: fire-at-will toggle, trap auto-rearm, turret/mortar commands, undraft gizmo (`ui.press:draft` touch). |
| `ui.cancel_job` | `{pawn, drafted?}` | Interrupt current job; optional undraft. |
| `ui.set_policies` | `{pawn, area?, hostility?: Flee|Attack|Ignore, medical?, self_tend?}` | Area restriction (non-fighter sheltering) + threat response for undrafted pawns. Touch `ui.set_policies:area`. |
| `ui.designate` | `{designator, things|cells|rect}` | `strip` (downed hostiles → untainted gear), `hunt`, `claim`, `forbid`/`unforbid`. |
| `ui.animal` | `{pawn, follow_draft?, master?, train?}` | Guard animals follow drafted master; attack-trained can be released. |
| `steward.orders.*` | `set`/`rally`/`run`/`release`/`explain` | The in-mod standing combat order (see §6). `rally {rect}` sets the hold position. `release` forces stand-down. |
| `game.speed`/`game.pause` | | Letters auto-pause; `speed_reassert` pattern already in `combat.engage`. |
| `dev.*` (dev-class only) | `dev.spawn_pawn`, `dev.incident`, `dev.heal`, `dev.damage`, `dev.kill_hostiles` | Combat harness tooling — refused under `--fair`. |

## 3. Mechanics — ranged

**Firing cycle** (per burst): `warmup` (aim; stationary; cancellable; shown as
wedge) → `burst` (N shots, `burstTicks` between; uninterruptible except stun;
ends early on target death) → `cooldown` (stationary; weapon cooldown × pawn
Ranged Cooldown Multiplier). MaxDPS = `dmg×burst / (cooldown+warmup+burstTicks×(burst-1))` per 60t.

**Range bands**: accuracy values defined at Touch=3, Short=12, Medium=25,
Long=40 cells; linear interpolation between; the verb **never fires beyond its
`range` stat**. Examples: pump shotgun 15.9, assault rifle ~31, sniper ~45,
centipede blaster ~27, pikeman needle gun 44.9, mini-turret 28.9.

**Accuracy**: `hitChance = ShootingAccuracy^range × weaponAcc(range) × weather ×
smoke × cover × bodySize + darknessPrecept`.
- ShootingAccuracy = per-tile no-miss chance; skill 0 → 89%, 10 → 97%, 20 →
  99% (post-curve; Sight 12×, Manipulation 8×, traits ±5, gunlink +3). Per-tile
  compounding ⇒ skill dominates at range: 99% vs 98% at 32 cells = 72.5% vs
  52.4% base.
- Weather: fog ×0.5 → clear ×1.0. Smoke: ×0.3 if any tile between. Body size:
  ×0.5 ≤0.5, =size to 2, ×2 ≥2 (makes centipedes easy to hit).
- Miss scatter: projectile lands within max-miss distance scaled by accuracy
  (100%→1 cell … 2%→10 cells); stray shot 50% nothing / 50% hits what's there.
- Forced-miss radius (explosives): ×0 ≤8 cells, ×0.5 9-24, ×0.8 25-48, ×1 49+.
- Interception: live pawns can eat projectiles mid-flight; factor 40%×bodysize
  (4-80%), impossible within 5 cells of shooter, full at 12+; downed reduced.
- Stopping power: hit on body-size ≤ stopping power → stagger = 1/6 speed for
  95 ticks. Humans = size 1 ⇒ any SP≥1 staggers.
- Melee-range restriction: a shooter can't fire at a target in *its own* melee
  range, but **colonists** may target distant enemies while being melee'd
  (NPCs can't) — ranged pawns under assault should retarget, not brawl.

## 4. Mechanics — cover

| Object | Cover | Notes |
|---|---|---|
| Wall (any) / held-open door | 75% (high) | Blocks LOF; shooters "lean" at corners; blocks explosives |
| Sandbags / barricade | 55% (low) | Doesn't block LOF; non-flammable (stone barricade = more HP) |
| Stone/steel chunk | 50% (low) | Free; dump via dumping zone to improvise a line |
| Tree | 25% | Saguaro 30%; bush 20%; rubble ~20% |
| Animals/pawns | small | Also interception risk for both sides |

Angle multiplier on cover: <15° 100%, 15-27° 80%, 27-40° 60%, 40-52° 40%,
52-65° 20%, >65° 0%. Point-blank penalty: 33% effective when shooter adjacent
to the cover, 66% at 1 tile off it. Diagonal shots can hit 2 cover units
(stacked) — firing nearly *along* the cover line nearly nullifies it
(flanking). "Wall + adjacent sandbag" lean-combo reaches ~83-97% effective.

## 5. Mechanics — melee

- Engaged only at adjacency (1 cell); **one enemy attacker per cell per target**
  ⇒ the 3v1 chokepoint block: 3 brawlers stand *outside* (not in) a 1-wide gap.
- Hit resolution: attacker `MeleeHitChance` (skill + Manipulation + Sight) vs
  defender `MeleeDodgeChance`; a dodge is a guaranteed miss. Blunt damage:
  no bleed, stun chance, armor weak vs blunt. Dirt/water kick: −80%/−50% sight.
- Melee engagement suppresses ranged fire *of the engaged enemy* — melee
  sorties neutralize enemy shooters; shield belts block ranged for the
  approach (melee weapons only while worn).
- Makeshift melee: guns bash at reduced DPS; body-part weapons (knee spikes,
  power claw) give ranged pawns a melee fallback.
- Fast enemies can't be kited → door-potshot loop (open door, shoot, step back
  so it closes, repair door) kills anything given time — guide 02:04-02:06.

## 6. Reference decision model — `Order_Combat` distilled

The steward's standing combat order is the proven baseline state machine
(`Order_Combat.cs`, interval 60 ticks):

**Detection** — hostiles = `attackTargetsCache.TargetsHostileToColony`, spawned,
not fogged, not threat-disabled, not downed/dead, and never player-faction or
host-faction pawns (excludes berserk colonists, rebelling slaves, prison
breaks, colony animals).

**Classify → engage vs watch** (`ThreatRules.Engage`, radius 40):
| Hostile | Engage | Watch |
|---|---|---|
| Inside Home area OR ≤40 cells of rally center | ✓ | |
| Siege (`LordJob_Siege`) | | ✓ |
| Manhunter mental state | only if a colonist is outside Home | everyone indoors → ✓ |
| Lorded pawn | only when duty ∈ {AssaultColony, PrisonerAssaultColony, Breaching, Sapper, Escort, Kidnap, Steal, HuntEnemiesIndividual, AssaultThing, NestAssault} | staging/sleeping/guard duties → ✓ |
| Structures (turrets, mech-cluster buildings) | only when near | far → ✓ |

**Draft eligibility** (`CombatEligibility.WhyNot`) — skip when: not spawned/
dead, downed, prisoner, slave, juvenile, incapable of violence, in mental
state, no drafter, **touched** (live manual touch), unmanaged, health < 30%,
unarmed. Needs hysteresis: relieve (undraft) when food OR rest < 15% with no
hostile within 30 cells of pawn/rally; re-draft only when both > 50%; **never
relieve while overrun** (base breached = everybody fights).

**Deploy**: rally = `steward.orders.rally` rect, else 13×13 around base center;
none on a baseless map. Assign each fighter a distinct standable cell inside
the rect — candidates scored by `CoverUtility.TotalSurroundingCoverScore`
(cover-first), then greedy spread (min-distance cap 4) with a 0.05
center-bias; door cells excluded. Non-fighters → restricted to Home area
(previous area remembered).

**Hold**: positions re-issued every 250 ticks (wanderers re-sent; pawns a job
undrafted get re-drafted).

**Overrun** (`overrun`): hostile inside Home or ≤5 cells of rally center → all
fighters `ui.attack` their nearest hostile (melee weapon → AttackMelee else
AttackStatic).

**Release**: 600 hostile-free ticks → undraft only what the order drafted
(manually-touched pawns stay drafted, retried each pass until touch expires),
restore non-fighters' areas (unless the director changed them — drop the
record), run the rescue order once, ledger `combat_released`. Engagements >
30000 ticks (half a day) → `combat_prolonged` once.

**Manual-touch interlock** (2500-tick cooldowns): touches in scope
{ui.draft, ui.goto, ui.attack, ui.order.drafted, ui.job, ui.press:draft,
ui.set_policies:area} exclude the pawn from order control; on release,
control-scope touches keep the pawn drafted; area-scope touches drop the area
restore. **Pack implication: orders issued by the brain are manual touches —
either route combat through the steward order, or accept that each issued
draft/goto/attack pauses order control for that pawn ~1 h.**

## 7. Mechanics — threat taxonomy & behavior

**Raid arrival** (weights): walk-in edge 45%, walk-in group 15%, drop pods 30%
(~9s before pods open; "drop on top of you" targets a colonist not under
overhead mountain, 40% lands on powered unroofed trade beacon), haywired pods
10%, mech cluster (Royalty). **Attack styles**: immediate; smart (avoids
turret LOS only); preparation/staging (idle near spawn until timer/losses →
free prep or pre-empt); sapper (best miner digs toward *assigned* beds, avoids
turret LOS); breach (breach axe / frag grenadier / termite thump-cannon vs
colony-built walls only; smart variant avoids turret LOS); siege (2 mortars +
sandbags; assault after 1.5-3d or ~8% chance per hit taken).

**Raider behavior**: attacks random constructed objects/colonists/animals;
torches crops/power/conduits; never natural rock (sappers excepted) or
*unpowered* turrets (the declump trick); prioritizes active shooters; can't
open doors; with no pathable route, bashes random furniture/walls and splits
up. Grenadiers avoid own-faction friendly fire; rocketeers try to.

**Morale/flee**: human groups flee when downed+killed ≥ a per-group random
40-70% of strength, or after ~10-15 h attacking (26-38k ticks from assault
start; sappers 33-38k). Per-group independent. Kidnap/steal duties disengage
early with captives/loot. **Mechanoids never flee** and don't use cover;
destroy all targets then wander. Manhunter animals: melee-only, can't open
doors (will chew them), linger 24-54 h, scaria rots corpses. Insects guard
~10 cells of hives.

**Threat sizing** (planner-level): raid points = (wealth pts + pawn pts) ×
threat scale × starting factor × adaption (0.4-1.47); min 35, max 10k.
Combat power ~1 pt each: drifter 35, tribal archer 45, warrior 50, pirate
gunner 65, scyther 150, centipede 400. Unlocks: mech/center pods ~300,
infestation/cluster ~400, siege ~500, sapper/breach ~700.

## 8. Mechanics — positioning, kiting, retreat

**Positioning rules**
- Spacing ≥1 tile between shooters (miss-scatter + AoE), OR all within 5 tiles
  (zero friendly fire). Firing line ≤3 deep rows firing over shoulders is safe.
- Shooters adjacent to cover; wall-lean + barricade combo; firing line roofed
  (weather immunity for accuracy) and floored/lit (move speed for
  repositioning).
- Chokepoint: exactly one open route into base; melee blockers *outside* the
  gap; traps in one lane of a 2-wide entrance, fence lane for colonists;
  spike traps can't be placed adjacent (incl. blueprint-next-to-built) and
  colonists can trip them; auto-rearm on.
- Killbox: firing-line-to-entrance distance = weapon max range so targets are
  engaged only once inside; unpowered turret at entrance declumps the stream;
  double walls vs breachers; turrets spaced ≥4 (50% explode under 20% HP,
  3.9-radius bomb); hospital adjacent; IEDs with non-overlapping radii.
- Retreat layering: rows of cover to fall back through; if overrun, enemies
  gain your cover lines.

**Kiting rules** (when to run-and-gun)
- Requires pawn speed > target speed, or weapon range > target range (AR ~31
  vs centipede ~27: fire, step back ~3 cells, repeat). Slow-weapon users
  (sniper) can't potshot safely; fast long-range weapons (AR, bolt-action) are
  the kiting kit; lightly armored kiters.
- Never kite what outranges or outruns you (lancers, snipers, fast animals
  unless Moving >140%). Don't break enemy attention or they retarget.
- Manhunter-sized threats: slow animals kitable by anyone; fast ones only by
  fast pawns; boomalopes/boomrats forbidden as melee blockers (explode).
- Drug assist: go-juice +30% speed/−90% pain/+10% consciousness; yayo +15%
  speed/−50% pain. Stagger (stopping power) is a speed debuff lever.

**Retreat conditions** (when to run)
- Pawn-level: health < 30% (order floor), bleeding with ~2 h to live → drag
  out immediately; food|rest < 15% with no hostile within 30 → relieve;
  shield-belt tanks retreat when shield drops.
- Position-level: overrun (hostile in Home or ≤5 of rally) → abandon hold to
  free attack; covered line compromised (breach, termite) → fall back to next
  line.
- Colony-level: unwinnable raid → keep everyone in Home/behind walls, wait out
  manhunters (24-54 h) and let morale timers (10-15 h) or flee-threshold run;
  never chase routers (guide: let them leave — chasing extends danger and
  risks re-engagement).

**Advance conditions** (when to push)
- Staging raid in range of your shooters → pre-empt or snipe to trigger their
  assault into prepared ground.
- Siege: hit the camp early *after* supply pods land (before → they flee and
  take the loot), or wound one to trigger the assault.
- Sappers/breachers at the wall → sortie; waiting in the killbox loses the
  wall.
- Fleeing hostiles: chase only with spare capacity (best-Melee runner per
  `chase-fleeing` rule) — stripping/capture is the real prize.
- Downed hostiles → strip-designate before they die (untainted gear), capture
  for recruitment, rescue your own immediately.

## 9. Decision hooks → pack mapping

| Trigger | Detect via | Action class |
|---|---|---|
| Raid letter / threat appears | `state.letters` def ThreatBig/Small, `state.threats.hostiles` non-empty, `danger` rise | `reflex` or rule → draft-capable set evaluation |
| Hostile classified engage (in Home / ≤40 rally / assault duty / manhunter w/ colonists out) | hostile row fields (`pos`, `lord`, `mental`) + `map.cell.home` | `draft-pawn` all eligible; `ui.goto` to rally cells (`@fn:rally_cell`) |
| Watch-only threat (siege, staging, far structures, manhunter w/ all indoors) | same fields | no draft; optionally `ui.set_policies area:Home` for all |
| Overrun (hostile in Home or ≤5 rally) | `dist_home`/`pos` + home flags | `attack-target` nearest per fighter (melee flag auto) |
| Fighter needs break | `state.pawn` needs.Food/Rest <15, no hostile within 30 | undraft; re-draft when both >50 (hysteresis state) |
| 600 hostile-free ticks | `@fn:living_hostiles()` empty streak | undraft drafted, restore areas, `rescue` once, strip/capture |
| Prolonged fight | engaged duration > 30000t | escalate/log (`combat_prolonged`-style event) |
| Chase window | `fleeing_ids()`/`fleeing_hostiles` rising `dist_home` | `attack-target` with fastest melee pawn (existing rule) |
| Downed hostile | `downed_ids()` non-empty | `strip-pawn`, `Capture` job |
| Downed colonist | `colonists.downed` | `rescue` (existing reflex); mid-fight: `ui.job Rescue` w/ shield-bearer |
| Bleeding-out fighter | `state.pawn.bleeding`/`needs_tending` | drafted `TendPatient` on the field, or rescue to safety |
| Pawn manually ordered | (touch tracking — steward-side today) | skip pawn in pack rules for the cooldown window |

## 10. Capability primitive spec

Proposed catalog entries (`kind` per capability-catalog conventions).
Existing: `draft-pawn`, `attack-target`, `strip-pawn`, `rescue`, `firefight`,
`assign-job`, `equip-pawn`, `wear-apparel`, `answer-letter`; selectors
`hostiles`/`living_hostiles`/`downed_hostiles`/`fleeing_hostiles`; fns
`nearest_hostile`, `downed_ids`, `fleeing_ids`, `drafted_ids`, `armed_ids`,
`armed_count`, `living_hostiles`, `home`, `near_home`, `hostile_faction`,
`best`, `pos`, `terrain_at`, `zone_at`, `roofed`.

**New templates** (all bridge methods already sealed):
- `move-pawn` → `ui.goto` {pawn, cell, draft?} — reposition/retreat/kite step.
- `cancel-job` → `ui.cancel_job` {pawn, drafted?} — peel/interrupt.
- `set-area` → `ui.set_policies` {pawn, area} — shelter non-fighters.
- `set-hostility` → `ui.set_policies` {pawn, hostility: Flee|Attack|Ignore} — undrafted threat response.
- `press-gizmo` → `ui.press` {thing, label} — fire-at-will, trap auto-rearm, hold-position toggles.
- `order-pawn` → `ui.order` {pawn, at, label} — float-menu (Capture, melee-attack-specific, etc.).
- `field-tend` → `ui.job` {job: TendPatient} — drafted in-field medical.
- `capture-pawn` → `ui.job`/`ui.order` {job: Capture} — downed-hostile capture.
- `ingest-drug` → `ui.job` {job: Ingest} — combat drugs (go-juice).
- `animal-guard` → `ui.animal` {follow_draft, master} — animal escort/release.
- `rally-set` → `steward.orders.rally` {rect} — move the hold position.
- `order-run` → `steward.orders.run` {order} — force a standing-order pass (e.g. rescue now).
- `combat-release` → `steward.orders.release` — explicit stand-down of the order.

**New selectors/fns**:
- `engaged_hostiles` / `watching_hostiles` — classify per §6 rules (needs
  `lord`/`mental` fields + `map.cell.home`; `[fn]` over existing data).
- `hostiles_in_home` / `hostiles_within(cell, r)` — overrun + engage-radius
  predicates.
- `fighters()` / `draftable()` — eligibility predicate set (weapon, downed,
  juvenile, violence-capable via `disabled_work`, health ≥ cfg, needs).
- `rally_cell(pawn)` — distinct cover-first cell in rally rect (port
  `RallyLogic.Spread` + cover score from `map.cell.things` × defs.get
  coverEffectiveness, or bridge-side `[bridge-gap]` for the real
  `CoverUtility` score).
- `weapon_range(thingId|def)` — `defs.get` verbs.range; also
  `weapon_stats(def)` → {range, warmup, cooldown, burst, acc bands, dps}.
- `outranges(pawn, hostile)` — our range/speed vs theirs (kite eligibility).
- `speed_of(id)` — `state.pawn.capacities.Moving` × 4.6 + trait offsets
  (approx; exact stat `[bridge-gap]`).
- `los(from, to)` — `[bridge-gap]` (no LOS RPC; derive from `map.view`
  buildings layer meanwhile).
- `cover_at(cell, from)` — `[bridge-gap]` preferred (CoverUtility); client
  approximation possible via `map.cell` things.
- `time_since_engaged` / engagement bookkeeping — pack-side via mode vars +
  `@fn:` counters (`dist_trend` precedent in `fleeing_ids`).

**Predicate additions**: none required — `eq/gt/lt/in/contains/empty/present`
+ `all/any/not` cover every trigger above; ranges expressed as
`{field: "@var:it.dist_home", op: lte, value: "@cfg:combat.engage_radius"}`.

## 11. Pack skeleton (fair class — no dev.*)

```yaml
combat:
  rally_anchor: base            # anchor name or steward rally
  engage_radius: 40             # ThreatRules.EngageRadius
  overrun_radius: 5             # CombatTimers.OverrunRadius
  near_hostile: 30              # relief suppression radius
  release_ticks: 600            # hostile-free stand-down delay
  hold_polls: 4                 # ~250-tick position re-issue at live poll rate
  prolonged_ticks: 30000
  min_health: 30                # draft floor, percent
  relief: {food: 15, rest: 15, recover: 50}
  assault_duties: [AssaultColony, PrisonerAssaultColony, Breaching, Sapper,
                   Escort, Kidnap, Steal, HuntEnemiesIndividual, AssaultThing,
                   NestAssault]
  watch_lords: [LordJob_Siege]
  manhunter_mental: Manhunter

rules:
  - id: shelter-noncombatants
    for_each: colonists
    when: {all: [{field: "@fn:count(@fn:living_hostiles())", op: gt, value: 0},
                 {field: "@var:it.weapon", op: absent}]}
    try: [{template: set-area, params: {pawn: "@var:it.id", area: Home}}]
  - id: draft-fighters
    for_each: "@fn:draftable()"
    when: {field: "@fn:count(@fn:engaged_hostiles())", op: gt, value: 0}
    cooldown: {polls: "@cfg:combat.hold_polls"}
    try:
      - {template: draft-pawn, params: {pawn: "@var:it", drafted: true}}
      - {template: move-pawn, needs: "@fn:rally_cell(@var:it)",
         params: {pawn: "@var:it", cell: "@fn:rally_cell(@var:it)"}}
  - id: overrun-all-in
    for_each: "@fn:armed_ids()"
    when: {field: "@fn:hostiles_in_home()", op: not_empty}
    try: [{template: attack-target, needs: "@fn:nearest_hostile(@var:it)",
           params: {pawn: "@var:it", target: "@fn:nearest_hostile(@var:it)"}}]
  - id: relieve-exhausted        # hysteresis: only when nothing near
    for_each: "@fn:drafted_ids()"
    when: {all: [{field: "@fn:count(@fn:hostiles_within(@var:it, @cfg:combat.near_hostile))", op: eq, value: 0},
                 {any: [{field: "@fn:need_of(@var:it, Food)", op: lt, value: "@cfg:combat.relief.food"},
                        {field: "@fn:need_of(@var:it, Rest)", op: lt, value: "@cfg:combat.relief.rest"}]}]}
    try: [{template: draft-pawn, params: {pawn: "@var:it", drafted: false}}]
  - id: stand-down               # hostile-free streak → release + rescue
    when: {all: [{field: "@fn:living_hostiles()", op: empty},
                 {field: "@fn:ticks_since_hostile()", op: gte, value: "@cfg:combat.release_ticks"}]}
    try:
      - {template: combat-release}
      - {template: strip-pawn, when: {field: "@fn:downed_ids()", op: not_empty},
         params: {designator: strip, things: "@fn:downed_ids()"}}
  - id: chase-fleeing            # existing universal rule shape
    for_each: fleeing_hostiles
    try: [{template: attack-target,
           params: {pawn: "@fn:best(@cfg:universal.chase_skill)",
                    target: "@var:it.id"}}]
```

(`draftable`, `engaged_hostiles`, `hostiles_in_home`, `hostiles_within`,
`rally_cell`, `need_of`, `ticks_since_hostile` = the new fns above.)

## 12. Fastbrain alignment — per-pawn action lists

The decide stage (`select.py`, feature 017) is the per-pawn executor this
primitive plugs into: `decide.select.pawn_scope` compiles candidates
`for_each` pawn × `options`, bounds the whole list (colony + pawn) to ≤20,
batches one `q.pawn.<id>` choice question per pawn into a single systemone
call, and applies the pick by direct dispatch. Fallback is `priority_head`
— the highest-priority offered candidate — so **compile-time pruning +
priority scoring is the deterministic policy; the model only arbitrates
among already-viable options.** Per-pawn optimization is therefore
expressed entirely in pack data:

- `when`/`needs` = eligibility gates (pawn fit × enemy mix × mode).
- `priority` = fitness score for this pawn in this fight — resolve to a
  number via `@fn:` so the fallback is the best deterministic pick.
- `params` = resolved targets/cells at compile time (`@fn:` on `@var:it`).

### Mode var (colony-level)

`combat_mode()` `[fn]` classifies once per poll — `watch | engage |
overrun | hold` — using §6 rules (Home containment, engage radius, lord
duty, manhunter-conditional, overrun radius). Pawn-option `when` gates
read it so per-pawn choices stay consistent with the colony plan; the
colony-scope goal list still owns mode-level goals (siege sortie,
defense build) separately.

### Option vocabulary (per pawn, gated so each pawn sees ≤3–4)

| id | template | when (all w/ `living_hostiles` non-empty) | priority |
|---|---|---|---|
| `shelter` | `set-area` Home | non-fighter (`disabled_work` violence, juvenile, unarmed-and-no-spare) or mode=watch | `100` for non-fighters |
| `hold-rally` | `move-pawn` `@fn:rally_cell(it)` | mode∈{engage,hold}, fighter, health≥min | `@fn:shoot_fit(it)` when enemy melee-heavy |
| `attack-nearest` | `attack-target` `@fn:nearest_hostile(it)` | mode=overrun, or engaged && `@fn:in_range(it, nearest)` | `@fn:dps_fit(it)` |
| `kite-step` | `move-pawn` `@fn:kite_cell(it, nearest)` | ranged && `@fn:outranges(it, nearest)` && dist < safety | `@fn:kite_fit(it)` |
| `melee-block` | `move-pawn` `@fn:block_cell(it)` | melee_fit high, choke exists, enemy melee-heavy, few enemy shooters | `@fn:block_fit(it)` |
| `chase-fleeing` | `attack-target` `@fn:nearest_fleeing(it)` | target in `fleeing_ids` && pawn fastest melee | `melee_fit` |
| `field-tend` | `field-tend` casualty | doctor-capable && bleeding colonist in reach | `skill_of(it, Medicine)` |
| `rescue-downed` | `rescue` job | downed colonist && route safe-ish | fixed high |
| `retreat` | `move-pawn` home/doctor cell | health<floor \|\| bleeding critical \|\| outranged&&outspeeded | fixed very high |
| `relieve` | `draft-pawn` false | food\|rest <15 && no hostile within 30 && mode≠overrun | fixed mid |

Auto-draft folds into `ui.goto`/`ui.attack`/`ui.job` (`draft=true` default
in goto; attack drafts) so single dispatch = complete action — no
composite template needed for the common case.

### Fit / threat fns (the optimizer)

Pawn side (`state.pawn` detail + `defs.get` weapon stats):
`skill_of(id, skill)`, `weapon_stats(def)` → {class, range, dps, warmup},
`shoot_fit` = Shooting + weapon dps + Manipulation + Sight;
`melee_fit` = Melee + weapon + armor/shield-belt + Manipulation;
`kite_fit` = `weapon_range` − `enemy_max_range` margin × speed margin;
`block_fit` = Melee + armor class + shield + (fast enemy? −);
`pawn_power(id)` = combat-power estimate (wiki table §7).

Enemy side (`state.threats` + `defs.get` on hostile `weapon`/`def`):
`enemy_mix()` → {melee, ranged, turret, manhunter counts};
`enemy_max_range()`, `nearest_enemy_dist(cell)`, `threat_power()` =
Σ hostile combat power vs Σ fighter `pawn_power` (odds ratio feeds
`combat_mode` — unwinnable ⇒ watch/shelter instead of engage);
`engaged_count`, `in_home` flags.

### Budget discipline (≤20 hard bound)

Non-fighters offer 1 option (`shelter`); fighters 2–3 (mode-dependent);
combat options carry a `+combat_weight` cfg bump so they outrank routine
options during engagement. `compile_actions` sorts by priority then order
— combat `when` gates must prune *before* the bound, not rely on ranking.
`cadence_polls: 1` while engaged; `batch_pawns: true` keeps it one call.

### Pack fragment

```yaml
decide:
  select:
    role: rimbrain.select
    batch_pawns: true
    fallback: priority_head
    cadence_polls: 1
    pawn_scope:
      for_each: colonists
      options:
        - id: retreat
          template: move-pawn
          when: {any: [{field: "@fn:health_of(@var:it)", op: lt, value: "@cfg:combat.min_health"},
                       {all: [{field: "@fn:outranged_by(@var:it)", op: eq, value: true},
                              {field: "@fn:outrun_by(@var:it)", op: eq, value: true}]}]}
          priority: 90
          params: {pawn: "@var:it.id", cell: "@fn:safe_cell(@var:it)"}
        - id: kite-step
          template: move-pawn
          when: {all: [{field: "@fn:combat_mode()", op: in, value: [engage, hold]},
                       {field: "@fn:outranges(@var:it, @fn:nearest_hostile(@var:it))", op: eq, value: true}]}
          priority: "@fn:kite_fit(@var:it)"
          params: {pawn: "@var:it.id", cell: "@fn:kite_cell(@var:it)"}
        - id: hold-rally
          template: move-pawn
          when: {all: [{field: "@fn:combat_mode()", op: in, value: [engage, hold]},
                       {field: "@fn:draftable(@var:it)", op: eq, value: true}]}
          priority: "@fn:shoot_fit(@var:it)"
          params: {pawn: "@var:it.id", cell: "@fn:rally_cell(@var:it)"}
        - id: shelter
          template: set-area
          when: {field: "@fn:draftable(@var:it)", op: eq, value: false}
          priority: 100
          params: {pawn: "@var:it.id", area: Home}
```

### Coordination caveats

Per-pawn picks are independent — no joint constraint (e.g. "exactly 3
blockers") can be enforced by the question. Encode quotas in compile-time
gates instead: `block_cell` returns none once `@fn:count_assigned(role)`
hits the cap (runtime fn over `rule_state`), or a colony-scope
`combat-plan` goal writes role assignments into `vars` that pawn options
read. `rally_cell` already returns *distinct* cells (OrderLogic spread),
so spacing emerges from the fn, not the model. Pawn picks are manual
touches → steward order skips them (~2500t): with fastbrain driving
per-pawn combat, the steward `combat` order should be off or in
delegate-mode (§13 risk).

## 13. Risks / open questions

- **Two combat writers**: steward `combat` order vs pack rules will fight over
  the same pawns — the manual-touch system arbitrates (order skips touched
  pawns ~2500t; brain touches pause it ~1 h). Pack must choose: delegate to
  the order (`steward.orders.set`/`rally`) and only handle exceptions, or
  disable the order and own everything. Mixing = thrash. Recommend: pack
  drives *decisions* (engage? rally where? overrun response), order owns the
  tick-level babysitting.
- **LOS/cover are bridge gaps** — `map.cell`/`map.view` approximations work at
  pack level but a real `map.los`/`cover` RPC would make `rally_cell` and
  "in range and visible" exact.
- **Hostile speed/range**: `weapon` def → `defs.get` gives range; move speed
  needs race def + health approximations — kiting checks stay heuristic until
  a `pawn.stats` surface exists.
- **Poll-vs-tick accounting**: rules count polls; game thresholds are ticks
  (release 600t, auto-undraft 10000t, morale 26-38k t). Packs should carry
  `poll_ticks` cfg so rule cooldowns express intent in ticks.
- **Fair-class boundary**: combat *testing* (spawn/heal/incident) stays in
  `dev-lab-v0`; the defense policy itself is fair — keep the split.

## 14. Design decisions (Phase 0 consolidation)

- **Decision**: Delegate — the Steward `combat` order remains the base executor; pack steers it via `steward.orders.*`; order state is exposed into observation; per-pawn options are surgical overrides honored via manual-touch windows.
  **Rationale**: Order_Combat is proven and already handles the tick-level state machine (rally spread, overrun, release hysteresis, area restore, rescue); duplicating it in rules would fight the touch interlock. Per-pawn overrides (retreat/focus/block) are exactly what touches were designed to protect.
  **Alternatives**: pack-owns-everything (rejected: reimplements the order in YAML, doubles the writer-conflict surface); full delegate with no pawn options (rejected: loses the fastbrain per-pawn fit that motivated the feature).

- **Decision**: Optimization at compile time — `when`/`needs` prune ineligible options; `priority` encodes per-pawn-vs-threat fitness; `priority_head` fallback = deterministic optimum.
  **Rationale**: the ≤20 bound and single-pick-per-pawn contract make the compiler the policy; the model arbitrates among viable choices only.
  **Alternatives**: free-form model orders (rejected: violates bounded-authority invariant); per-pawn scoring inside the model prompt (rejected: unverifiable, non-deterministic fallback).

- **Decision**: No bridge changes in v1 — LOS/cover approximated from `map.cell`/`map.view`; enemy weapon range via `defs.get` on the hostile's `weapon` def; enemy speed approximated (race def + capacities).
  **Rationale**: every required signal exists or approximates; bridge work is separable follow-up.
  **Alternatives**: `map.los`/`cover` RPC first (rejected: unnecessary coupling; approximate checks are conservative).
