# Research: building/room capability primitive

Research extract for a room-building capability/pack design (UR-BRN-011/013:
archetypes, sizes, furnishing lists, and thresholds are pack data; runtime
supplies capability primitives). Tagged `[have]` (works today) / `[fn]` (needs
a runtime resolver) / `[bridge-gap]` (needs bridge work). Companion to
`019-combat-capability/research.md`.

## Sources

- rimworldwiki.com: Rooms/Room stats (enclosure rules, roles, all four stat
  formulas + band tables), Space, Beauty, Impressiveness.
- `CantBeLucifer/RealisticRoomsRewritten` GitHub — `RealisticRoomsSettings.cs`
  (authoritative settings list; workshop table values are stale).
- `upstream/rimagent/mod/Source/` — `StateRpc.cs` (`state.rooms`, `state.base`),
  `UiRpc.cs` (`ui.build`/`ui.build_many`), `MapRpc.cs` (`map.cell`,
  `map.open_rects`), `DefsRpc.cs` (`defs.get`/`defs.buildable`).
- `components/rimbrain/packs/start-mode-v0/pack.yaml` — existing build
  vocabulary: `build-layout` (ui.build_many ops), `build-one`, `lay-floor`,
  `roof-rect`, `set-anchor`, `enclosed_at`, `open_rects`, `rank_site`.

## 1. Observable state

| Signal | Source | Fields |
|---|---|---|
| Live rooms | `state.rooms` | `id`, `role` (defName), `cells`, `outdoors`, `temp`, `at`, `impressiveness`, `beauty`, `cleanliness`, `owners` — **`space` and `wealth` are NOT exposed** `[bridge-gap]` (space approximable client-side from `map.cell` walkable/standable + things; wealth via `defs.get` costs) |
| Cell interior | `map.cell` | `terrain` (floor def), `roof`, `room`, `home`, `things`, `standable`, `walkable`, `light`, `temperature` |
| Def stats | `defs.get`/`defs.buildable` | furniture size/cost/beauty/comfort/linkable stats, floor beauty+cleanliness+workToMake, `scoreStages` on RoomStatDefs |
| Colonist needs | `state.pawn` | `thoughts`/`mood` (drives upgrade triggers: "ate without table", "awful bedroom", "disturbed sleep"), `bed` assignment |
| Mod presence | none | `[bridge-gap]` — no mod-list RPC; **workaround: `defs.get` the `Space` RoomStatDef and read its `scoreStages[].minScore` — modded thresholds differ from vanilla, so tier values are self-reporting** |

## 2. Control surface

Existing `[have]` templates cover placement: `build-layout`
(`ui.build_many` — walls as rect outlines, floors filled rects,
doors/furniture single cells, `dry_run`), `build-one` (`ui.build`),
`lay-floor`, `roof-rect`/`no-roof`, `ui.designate` (`deconstruct`,
`uninstall`, `mine`), `set-anchor`, `create-stockpile`, `expand-home`.
Missing piece is not verbs but a **layout compiler**: `plan_room(rect,
archetype)` `[fn]` → the ops array (wall outline + door cell + floor fill +
furniture cells honoring size/link/adjacency rules), so packs declare
archetypes as data instead of hand-writing per-op cell math.

## 3. Mechanics — enclosure & indoors

- A room = space fully enclosed by impassable objects: walls, doors (open or
  closed), vents, natural rock, coolers, vac barriers. **Corners need not be
  filled** (diagonal seals). Fences do NOT enclose.
- Max room = 36 map regions ≈ 50×50 empty square; larger → non-room indoors.
- Indoors tests (three independent): temperature isolation breaks at ≥25%
  unroofed or open to map edge; `OutdoorsForWork` (>25% unroofed or >100
  unroofed tiles) gates surgery/research/gene speed factors and the outdoor
  0.8× work penalty; `PsychologicallyOutdoors` (≥300 unroofed, or map-edge +
  ≥50% unroofed) gates beauty/recreation/rituals.
- Temperature equalizes through open doors/vents — vent pairs link rooms into
  one climate zone; doors on busy corridors bleed heat every open.

## 4. Mechanics — the four room stats

**Space** = `1.4 × standable tiles + 0.5 × pass-through-only tiles`.
Occupied tiles (beds, tables, benches, lamps, heaters, art — anything you
can't stand on) cost 0.9 each vs empty. **Chairs/stools are free** (standable
furniture). Tier bands (vanilla → mod default):

| tier | vanilla minScore | RR-Rewritten default |
|---|---|---|
| cramped | <12.5 | <6.5 |
| rather tight | 12.5 | 6.5 |
| average-sized | 29 | 16.5 |
| somewhat spacious | 55 | 28.5 |
| quite spacious | 70 | 49.5 |
| very spacious | 130 | 84.5 |
| extremely spacious | 349.5 | 174.5 |

**Wealth** = market value of contents + enclosing walls/doors/columns/corners.
Bands: <500 impoverished, <700 somewhat poor, <2k mediocre, <4k somewhat
rich, <10k rich, <40k luxurious, <100k very luxurious, <1M extremely.

**Beauty** = avg beauty of interior + enclosing cells, with a small-room
penalty: `WeightedSize = size if size>40 else 20 + size/2` — every room under
40 tiles pays it. Bands: <−3.5 hideous, <0 ugly, <2.4 neutral, <5 pretty,
<15 beautiful, <50 very beautiful, <100 extremely, ≥100 unbelievably.

**Cleanliness** = avg per-tile cleanliness (flooring + filth + dirty
buildings; dirt/sand filth −12 beauty, −4 with RR filth tweak). Bands:
<−1.1 very dirty, <−0.4 dirty, <−0.05 slightly dirty, <0.4 clean, up to ~+0.6
sterile. Direct work factors: **surgery success, research speed, food
poisoning chance, gene assembly** — kitchen/lab/hospital are cleanliness
rooms, not impressiveness rooms.

**Impressiveness** = `65 × avg(Wm,Bm,Sm,Cm) + 35 × min(...)` where
`Wb=wealth/1500`, `Bb=beauty/3`, `Sb=space/125`, `Cb=1+clean/2.5`, each
curved `m = 1+ln(b)` above 1; then soft-capped: `I' = 0.25I + 0.75×(500·Sm)`
when I > 500·Sm. The **minimum stat carries 51.25%** — so the optimal build
raises the lowest stat, never stacks the best one. Space and cleanliness are
the usual binders; ~85-120 ("very impressive") is the practical ceiling
before sterile-floor economics. Mood bands: <20 awful (−2, bedrooms only),
20 dull 0, 30 mediocre (+1 bedrooms), 40 decent +2, 50 slightly +3, 65
somewhat +4, 85 very +5, 120 extremely +6, 170 unbelievably +7, 240 wondrous
+8. Moodlets last ~24h, granted when the room is *used* for its role.

## 5. Room roles (scoring → requisites → which stats matter)

| Role | Trigger buildings | Breaks when | Stats that matter |
|---|---|---|---|
| Bedroom | 1 assigned human bed | medical/prisoner bed present, >1 unassigned bed, non-cluster co-assignment | Impressiveness (mood) |
| Barracks | ≥2 human beds | a prisoner bed present; a valid bedroom inside | Impressiveness + disturbed-sleep hits |
| Dining room | tables (1x2/2x2/2x4/3x3; 12 pts each) | — | Impressiveness |
| Rec room | joy sources (7 pts each: horseshoes, chess, billiards, poker, TV, telescope, harp…) | — | Impressiveness |
| Hospital | medical human beds | prisoner bed present | Cleanliness (surgery/infection) + Impressiveness |
| Prison cell | exactly 1 prisoner bed | any colonist bed | Impressiveness (prisoner mood/recruit) |
| Prison barracks | ≥2 prisoner beds | colonist bed present | Impressiveness |
| Kitchen | stove (28 pts) | — | Cleanliness → food poisoning |
| Laboratory | research bench/drug lab/gene gear (60 pts) | — | Cleanliness → research/gene speed |
| Workshop | production benches (27 pts) | — | none |
| Storeroom | shelves | — | none |
| Tomb | sarcophagus | — | — |
| Barn | animal beds | — | — |
| Throne room (Royalty) | meditation/grand throne | workstations inside = invalid for titles | Impressiveness + **space tier per title** |
| Temple (Ideology) | altar | — | — |
| Nursery/Playroom/Classroom (Biotech) | baby beds / baby toys / blackboard | adult beds | — |
| Deathrest (Biotech) | deathrest casket | — | — |

Role is awarded to the highest scorer; ties go to the earlier role. One room
can still *grant* moodlets for roles it doesn't display (dining+rec in one
room works — the common "dining/rec hall" archetype).

## 6. Optimal archetypes

Worked examples (empty space = 1.4×cells; each non-standable furnishing −0.9):

- **Bedroom, vanilla "decent+"**: 4×6 (24 cells, ~33.6 empty space; bed 2 +
  dresser + end table + lamp + plant ≈ −5.4 → ~28, "rather tight"; art +
  carpet lift beauty/wealth to clear "decent"→"slightly impressive"). 5×5
  furnished ≈ 27.8 — same band; 4×4 is hard to get past "decent".
- **Bedroom, RR-modded**: tier targets shift, NOT impressiveness — a 3×4 or
  4×4 reaches the mod's "average-sized" tier (16.5) where vanilla needs ~21
  empty tiles for "average". Use for noble/title tier requirements; mood
  still needs real stat investment.
- **Barracks (early)**: 5×6+, N beds, accept disturbed-sleep; convert to
  bedrooms later (walls only).
- **Dining/rec hall**: dining + rec cohabit (tables 12pts vs joy 7pts — rec
  usually displays); chairs are space-free so seat capacity is cheap;
  ~6×8+ handles 8-10 pawns; place adjacent to kitchen (table-search radius
  ~20-25 cells → kitchen/freezer within that of dining, dining central to
  bedrooms).
- **Kitchen**: stove + separate dirty side (butcher table → own room or far
  corner; its filth hurts cleanliness → food poisoning); sterile floor when
  rich, else smooth/paved. Adjacent freezer (door chain: kitchen ↔ freezer ↔
  raw stockpile).
- **Hospital**: med beds + sterile floor (+0.6/tile cleanliness → surgery
  success, infection) + vitals monitor inside link radius of beds + lamp +
  no prisoner beds; quiet edge placement.
- **Workshop**: benches + tool cabinets (≤2 links each, +6% work speed,
  within link radius) + chairs at seats (comfort, free space) + lamps (lit
  work speed) + heater; near the raw-material stockpile.
- **Prison**: small cells (2×3) near the map-edge entrance for capture runs;
  separate from bedrooms.
- **Bedroom furnishings**: bed → linked dresser + end table (rest
  effectiveness/comfort bonuses, quality-scaled, within link radius — exact
  numbers via `defs.get`); light + plant + sculpture/armchair to push the
  beauty/wealth stats that bottleneck below space.
- **Floors**: floor every lived-in room (dirt path −1 beauty; constructed
  floors add beauty — carpet +2, flammable; sterile +0.6 cleanliness,
  expensive; smooth stone = free-ish, neutral); floors also fix move speed
  (rough ground ~87%).
- **Doors**: autodoor on high-traffic rooms (open speed); wood early.
- **Temperature**: heater/cooler per lived-in room, vents to share one
  climate block across adjacent rooms; ~1 vent per wall segment.

## 7. Realistic Rooms Rewritten — cfg profile

Authoritative settings (`RealisticRoomsSettings.cs`; packageId
`Lucifer.RealisticRooms`):

```yaml
mods:
  realistic_rooms_rewritten:
    package_id: Lucifer.RealisticRooms
    detect: {via: defs.get, def: Space, field: scoreStages}   # self-reporting
    settings:
      minSpaceRatherTight: 6.5        # vanilla 12.5
      minSpaceAverageSized: 16.5      # vanilla 29
      minSpaceSomewhatSpacious: 28.5  # vanilla 55
      minSpaceQuiteSpacious: 49.5     # vanilla 70
      minSpaceVerySpacious: 84.5      # vanilla 130
      minSpaceExtremelySpacious: 174.5# vanilla 349.5
      filthTweakEnabled: true         # dirt/sand beauty -12 -> -4
```

Design consequences:
- The mod mutates `RoomStatDef.Space.scoreStages` — **tier labels only**.
  Impressiveness consumes the raw space number (`space/125`) unchanged, so
  mood economics are identical with/without the mod.
- Tier-gated consumers get easier: Royalty title bedroom/throne minimum
  space tiers, any tier-checking mechanic. Size targets for *those* reqs
  must read the cfg tier table, not hardcode vanilla.
- Filth tweak: tracked dirt costs −4 beauty instead of −12 inside rooms →
  floors/cleaning urgency drops slightly; keep as cfg since it shifts the
  beauty ledger.
- Detection: `defs.get` on the `Space` RoomStatDef returns the live
  `scoreStages` — packs can auto-select the tier profile without a mod-list
  RPC. `[fn]` `space_tier(score)` + `space_target(tier)` resolve against
  whichever table the def currently carries.

## 8. Capability primitive spec

**New fns**:
- `space_score(rect)` — `1.4·standable + 0.5·passable` from `map.cell` rows
  (computable today; `[bridge-gap]` for the live `RoomStat_Space` value).
- `space_tier(score)`, `space_target(tier)` — threshold lookup via `defs.get`
  scoreStages (auto mod-aware).
- `room_at(cell)` / `rooms_matching({role, min_cells})` — wrap `state.rooms`
  `[have]` data.
- `room_stat(room_id, stat)` — impressiveness/beauty/cleanliness `[have]`;
  space/wealth `[bridge-gap]`.
- `plan_room(rect, archetype)` `[fn]` — compile an archetype (wall material,
  door side, floor def, furniture placement rules: size, link-radius,
  adjacency, standable constraints) into `ui.build_many` ops. This is the
  primitive the archetype table hangs off.
- `bed_demand()` — colonists + couples − existing valid bedrooms (from
  `state.pawn` assignments + `state.rooms` role==Bedroom).
- `pawns_with_thought(def)` — upgrade triggers ("ate without table",
  "awful bedroom", "disturbed sleep") from `state.pawn.thoughts`.
- `enclosed_at(rect, min_cells)` `[have]`, `blueprints_in` `[have]` —
  effect verification stays verifier-only (`room_role_at` +
  `impressiveness ≥ X` as goal `effect` specs).

**Templates**: existing build verbs suffice. Optional `deconstruct-rect`
/`uninstall` wrapper (`ui.designate`) for room conversion (barracks →
bedrooms).

## 9. Fastbrain alignment (colony scope)

Rooms are colony-scope work, not per-pawn: archetype goals become
`standing_goals`/`decide` candidates — `priority` = need score
(`bed_demand`, thought counts, threat-tier pressure), `effect` =
`enclosed_at` + role/impressiveness predicates, `steps` = `plan_room` →
`build-layout` → `roof-rect` → furnish ops → `ui.job` bed assignment.
Per-pawn scope only enters for the *builders* (construction priority via
`ui.job` Build/haul already handled by Steward stock/work).

```yaml
rooms:
  tier_table: "@cfg:mods.realistic_rooms_rewritten.settings"  # or vanilla
  archetypes:
    bedroom:
      size: {w: 4, h: 6}          # vanilla; 3x4 under RR tier targets
      target_impressiveness: 40   # decent (+2)
      floor: Carpet               # stuff via @fn:stuff
      furniture:
        - {def: Bed, anchor: wall, count: 1}
        - {def: Dresser, linked_to: Bed}
        - {def: EndTable, linked_to: Bed}
        - {def: StandingLamp, count: 1}
        - {def: PlantPot, optional: true}
    dining_hall:
      size: {w: 6, h: 8}
      target_impressiveness: 50   # slightly impressive (+3)
      furniture:
        - {def: Table2x4, count: 1}
        - {def: DiningChair, count: 8}   # space-free
        - {def: HorseshoesPin, count: 1} # co-rec role
        - {def: Sculpture, optional: true}
    hospital:
      size: {w: 5, h: 7}
      floor: SterileTile
      furniture:
        - {def: HospitalBed, count: 2}
        - {def: VitalsMonitor, linked_to: HospitalBed}
    kitchen:
      size: {w: 5, h: 6}
      floor: PavedTile            # sterile when rich
      furniture:
        - {def: FueledStove, count: 1}
        - {def: ButcherTable, separate: true}
    workshop:
      size: {w: 7, h: 9}
      furniture:
        - {def: ToolCabinet, links: 2}
        - {def: DiningChair, at: each_bench}
        - {def: StandingLamp, count: 2}
```

## 10. Risks / open questions

- **`state.rooms` lacks space + wealth** — the two stats most useful for
  planning checks. Client-side space is computable (`map.cell` things +
  standable), wealth only coarsely; a `room.stat` (or including them in
  `state.rooms`) is the clean fix `[bridge-gap]`.
- **`plan_room` is the real work**: furniture placement rules (link radii,
  door-side, no-block-door, chair-needs-table) belong in pack-declared
  archetype data, not hardcoded — but the *interpreter* that compiles an
  archetype to ops is runtime code `[fn]`.
- **Blueprint verification lag**: `enclosed_at` sees rooms only once fully
  walled; goals need blueprint-aware effects (`blueprints_in` exists) plus
  build-completion waiting (`lease_ticks` pattern already in shelter).
- **Mod detection is indirect** — `defs.get(Space).scoreStages` trick is
  unverified against the live bridge; confirm the field serializes, else add
  `game.mods` `[bridge-gap]`.
- **Current packs over-provision**: `start.shelter`/`govern.expansion` use
  7×7 rooms for everything (~63+ space, "somewhat spacious") — well past the
  "decent" threshold a 4×6 reaches. Right-sizing archetypes is the immediate
  win: same mood, ~40% less wall/labor/wealth per bedroom.

## 11. Design decisions (Phase 0 consolidation)

- **Decision**: Archetype = pack data; `plan_room(rect, archetype)` = the one runtime interpreter that compiles footprint + furnishing rules into `ui.build_many` ops.
  **Rationale**: keeps Principle IX clean — packs author rooms as data; runtime owns generic placement rules (link radius, adjacency, standability), never room policy.
  **Alternatives**: hand-written ops per room in packs (status quo — verbose, brittle); bridge-side room planner (rejected: policy in mod code, wrong layer).

- **Decision**: Space/wealth estimated client-side for v1; `state.rooms` stats (impressiveness/beauty/cleanliness) are the verification surface.
  **Rationale**: space is computable from `map.cell` (1.4·standable + 0.5·passable) well enough for sizing decisions; observed stats close the loop.
  **Alternatives**: bridge `room.stat` RPC first (deferred — additive later, no schema break).

- **Decision**: Mod detection reads live `Space` scoreStages via `defs.get`; vanilla table is the fail-safe when detection is inconclusive.
  **Rationale**: the mod mutates the def's `scoreStages` at settings-apply — the live values are self-reporting; vanilla is strictly larger so failure is safe.
  **Alternatives**: mod-list RPC (none exists); cfg-only flag (works but drifts from in-game settings edits).
