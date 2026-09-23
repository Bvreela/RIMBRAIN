# Feature Specification: Post-Start Governance — Standing Goals, Pack Classes, Goal Options

**Feature Branch**: `015-post-start-governance`

**Created**: 2026-09-23

**Status**: In Progress

**Input**: `start.completed` must be a handoff, not an exit — after the bootstrap contract holds, the agent keeps running the colony under standing pack goals (UR-RUN-009). Dev/test tooling must never be loadable in a fair run (UR-BRN-018). And the planner needs an overarching strategy option space — what helps the colony survive longer, what investment each option needs, and its effect on colony wealth and raid threat — to choose objectives from.

## Purpose

Three coupled changes:

1. **Post-start governance** (UR-RUN-009): `run_start(hold=True)` continues past `start.completed`, evaluating the pack's `govern.goals` each poll — ordered standing objectives with `when` engagement gates, verifier-checked `effect`s, and re-arm-on-lapse sustainment. Bounded callers (`cycle`, `--no-hold`, tests) still stop at completion.
2. **Fair/dev pack classes** (UR-BRN-018): packs declare `class: fair|dev`; a fair pack carries zero `dev.*` methods end to end; `Dispatcher(fair=True)` refuses a dev-class pack at load (`pack.not_fair`). Spawn/heal/combat scripting moved to `dev-lab-v0` (`class: dev`); `start-mode-v0`, `core-survival-v0`, `improve-v0` are `class: fair`.
3. **Colony-goals option catalog** (`goal_options`): `packs/colony-goals-v0.yaml` holds 19 overarching strategy options annotated `{survival_benefit, investment, wealth_impact, raid_threat_impact, phase, prerequisites, sources}` over the wiki-verified raid-points economy; the same list is embedded in the gameplay packs so the planner weighs options against observed state and promotes a subset into `govern.goals` or plans. Options are data — never auto-executed.
4. **Brain lifecycle** (UR-BRN-019..023): the RimBrain is a single loadable/unloadable entity — `brain_reset.request` drives refresh, pack swap, unload, and full reinit (tombstoned task namespaces, rebuilt mode/rule state), verified by a continuous-loop test.
5. **Obstruction-aware power siting** (UR-BRN-024): wind-turbine placement validates a pack-declared airflow corridor — buildings/walls/natural objects veto the site, vegetation is cut-designated first, and the corridor is suppressed (flooring or growing zone) against regrowth. Step `when`/`needs` evaluate per `for_each` candidate.

The research/letters/quests capabilities the govern goals consume (`state.research`, `state.quests`, `state.letters`, `ui.set_research`, `steward.research`, `ui.letter` plus the matching `@fn:`s and templates) landed with this feature and flipped their capability-catalog entries `gap` → `implemented`.

### Field observations (live colony, 2026-09-23)

A fair live run exposed two bad-build classes the goals must not produce:

- **Generator over-build** — `establish-power-grid` placed ~7 turbines in a column: the `repeat.while` blueprint gate never observed the pending frames (live `map.find kind=blueprint` rows don't expose a matching `def` field), so one blueprint issued per poll until the first completed. Build steps need their own pending-work gate, not just the loop's repeat guard (FR-1315).
- **Sealed housing shells + layout spam** — `expand-housing` doors resolve one row *outside* the room rect's wall edge (floating doors → sealed rooms), and the `enclosed_at` effect stays absent while frames stand, so `build-layout` re-issued every poll (~170 dispatches). Room ops need a pending-blueprint gate and door cells must land on wall cells (FR-1315).
- **Ruin furniture satisfies room-scoped goals** — unscoped `find_defs` matched a ruin table ~40 cells from the dining rect; chairs were designated around it. Room-scoped goals must scope `find_defs`/`blueprints` to their own rect (FR-1318).
- **Stuff-made defs need explicit `stuff`** — `TrapSpike` dry-runs silently fail without a material; every stuff-made build step passes resolved `stuff` (walls, doors, beds, traps).
- **Turbine corridor vs farmland** — a turbine sited so its wind corridor crossed the rice field: the agent cut its own crop and nearly floored the zone. Corridor scans must reject sites overlapping zones, not just buildings.
- **Single-chaser melee is a losing tactic** — one pawn forced `melee: true` while rifle-armed colonists idled; a mid-test raid wiped the colony. Defense must be coordinated: every armed colonist engages, and ranged pawns shoot rather than fist-fight (FR-1321).
- **Pack edits mid-run freeze dispatch** — `dispatch.pack_drift` refuses writes after the pack file changes; runtime must be restarted after pack revisions (operational constraint, not a bug).

## User Stories *(mandatory)*

### User Story 1 - Held Run Governs Past Completion (Priority: P1)

A `--mode start` run that reaches `start.completed` does not terminate: the interpreter evaluates `govern.goals` in declared order each poll. Sustainment goals (every colonist keeps a bed, the meal buffer never regresses) re-arm when their effect lapses; ambition goals (research bench → active research → mission offers) engage only when their `when` gate holds.

**Acceptance Scenarios**:

1. **Given** a completed start on a held run, **When** the next poll runs, **Then** the first unsatisfied govern goal proposes a `govern.<id>` ledger task and drives it through the normal lifecycle.
2. **Given** a terminal govern goal whose effect later lapses (a new mission letter arrives), **When** the effect check fails, **Then** the goal re-arms and dispatches its steps again.
3. **Given** `--no-hold` or a cycle's bounded start phase, **When** `start.completed` emits, **Then** the run/phase stops exactly as before.

### User Story 2 - Dev Tooling Cannot Enter a Fair Run (Priority: P1)

Every pack declares `class: fair|dev`. A fair run loads only packs with zero `dev.*` methods — the tooling is absent from the template registry entirely, so a dev action is `dispatch.unknown_action`, not a policy refusal. A dev-class pack is refused at load with `pack.not_fair`.

**Acceptance Scenarios**:

1. **Given** `Dispatcher(fair=True)` and `start-mode-v0`, **When** loaded, **Then** the pack loads cleanly and `spawn-hostile`/`heal-pawn` dispatch as unknown actions.
2. **Given** `dev-lab-v0`, **When** a fair dispatcher loads it, **Then** load raises `pack.not_fair` listing the dev methods — before any game write is possible.
3. **Given** `--mode combat`/`cycle`, **When** the pack loads, **Then** it is `dev-lab-v0` — scored paths never carry spawn/heal templates.

### User Story 3 - Planner Goal Option Space (Priority: P2)

The gameplay packs carry `goal_options`: 19 overarching colony goals spanning the survival arc (shelter → food → defense → stabilization → growth → wealth postures → endgame), each annotated with how it extends colony life, what it costs, and how it moves colony wealth and raid threat. The planner/model weighs them; committed objectives remain `govern.goals` or accepted plans.

Ten options are promoted into executable `govern.goals` in `start-mode-v0` (mirrored in `dev-lab-v0`), each carrying `option:` back to its catalog id: shelter, food security, arming, chokepoint traps, medicine plot, mood, power, research bench + progress, mission offers. The rest stay options pending capabilities (prisoner/trade/layout surfaces, a wealth signal); promoting them is planner work or human editing — no fake steps. `core-survival-v0` keeps the catalog only: it has no `start` config/`site` anchor, so the same goals can't resolve there.

**Acceptance Scenarios**:

1. **Given** any gameplay pack, **When** loaded, **Then** `pack.goal_options` lists the catalog goals with all annotation fields and resolvable prerequisite refs.
2. **Given** the wealth postures, **When** reviewed, **Then** `cap-idle-wealth` and `invest-wealth-in-defense` appear as distinct mutually-exclusive options, not merged policy.
3. **Given** `goal_options` data, **When** the interpreter runs, **Then** no goal executes — promotion into `govern.goals` or a reviewed plan is required first.

## Edge Cases

- **Established colony under hold**: sustainment effects already hold → goals skip-to-terminal with zero writes (same machinery as start phases).
- **Goal blocked on missing vars**: a goal with `requires:` entries that were never set reports `blocked` with the missing names, never dispatches.
- **Multiple lapsed goals**: declared order wins — the first active goal does work each poll.
- **Mission letter with no accept choice**: `for_each` filter finds no matching letter; the goal idles until its `when` gate or choices change.
- **Dev pack in a fair run via brain reset**: the reset path re-loads through the same dispatcher — `pack.not_fair` keeps the run fail-closed on the last valid pack.
- **Goal options vs govern drift**: `goal_options` is a catalog copy; divergence from `govern.goals` is expected (options ≠ commitments) and not an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-1301**: pack `govern.goals[]` — ordered `{id, option?, when?, requires?, need?, effect, steps, repeat?, escalate?}` evaluated in declared order every poll once the start exit contract holds and the run holds (UR-RUN-009). A terminal goal re-arms only while its observed `effect` has lapsed. `option` is a provenance link back to a `goal_options` catalog id when the goal is a promoted option. `escalate: {after_attempts, steps}` is the stall-remediation primitive shared by phases and goals (UR-RUN-006): after N `effect_absent_retry` cycles the blocker is structural, so remediation steps run alongside retries — each step's own `when` keeps it idempotent (e.g. haul stalls on a full stockpile → create the overflow zone, not more haul jobs).
- **FR-1302**: `run_start(hold: bool)` — `--mode start` defaults `hold=True`; `--no-hold` opts out; `cycle.py` start phase passes `hold=False`. Govern tasks share the TaskLedger lifecycle (`govern.<id>` ids, verifier-only success, `task.transition` log) and emit decision rows sourced `govern:<id>`.
- **FR-1303**: `pack.schema.json` gains `class: fair|dev`; `Dispatcher(fair=True).load_pack` refuses packs declaring `dev.*` template methods (`pack.not_fair` listing the methods). `start-mode-v0`, `core-survival-v0`, `improve-v0` declare `class: fair`; `dev-lab-v0` declares `class: dev` and owns spawn/heal templates + `combat`/`cycle` scripting (UR-BRN-018).
- **FR-1304**: `--mode combat` and `--mode cycle` load `dev-lab-v0`; tests using combat scripting switch to it. Fair runs never carry debug tooling.
- **FR-1305**: capabilities — bridge `state.research`, `state.quests`, `state.letters`, `ui.set_research`, `steward.research`, `ui.letter`, `steward.status`, `steward.stock.set`, `steward.stock.run`; policy fns `research()`, `research_current()`, `research_available()`, `quests()`, `letters(choice_only)`, `room_count(min_cells)`, `idle_count(patterns)`, `steward_stock(kind, field)`; templates `set-research`, `queue-research`, `answer-letter`, `set-stock-target`, `run-stock-job`; capability-catalog entries updated `gap` → `implemented`.
- **FR-1305a**: steward stock levers — pack goals steer the in-mod steward's stock jobs instead of duplicating them: `hunting-pause`/`hunting-scarce` suspend and resume `hunting`/`hunting_leather` jobs on `stocks.nutrition` hysteresis (full ≥ 12, scarce < 6 — wildlife is slow-farmed, not drained; over-hunting spoils and wastes work); `scale-mining` raises the `mining` ore target. No per-pawn `ui.set_work` — that removes the pawn from steward management.
- **FR-1305b**: storage self-repair — `maintain-storage`/`maintain-overflow` re-arm whenever `zone_named` lapses (construction deleting zones is an effect lapse like any other); `idle-work`'s `HaulToCell` alternative is gated on `zone_count > 0` so a missing stockpile doesn't spam un-completable assigns while the goals rebuild; `expand-housing` designates two extra enclosed rooms only while colonists are idle (temp activity while main goals wait on retry).
- **FR-1306**: `packs/colony-goals-v0.yaml` — standalone annotated catalog with the wiki raid-points mechanics baseline; `pack.schema.json` gains `goal_options` (array); the catalog list is embedded in `core-survival-v0`, `start-mode-v0`, `dev-lab-v0`.
- **FR-1307**: `views.py` goal rows cover `govern.<id>` goals after the start-phase rows, preserving pack order.
- **FR-1308**: `goal_options` are inert data — the interpreter never executes them; promotion into `govern.goals` or a reviewed plan is the only path to dispatch.
- **FR-1309**: brain lifecycle channel (UR-BRN-019) — `state/brain_reset.request` accepts `{}` (refresh active pack), `{pack: "<file-id>"}` (swap to a different pack — validation and `class` gate apply identically; a refused swap leaves the old brain active, fail-closed), and `{unload: true}` (halt: the brain stops evaluating rules/goals and every subsequent dispatch fails `dispatch.no_pack` until a pack is loaded again). `brain_status.json` reports `{ok, pack_id, pack_revision, loaded|unloaded, error}` for the overlay.
- **FR-1310**: full reinit on reset (UR-BRN-020) — `ledger.reset_ns` tombstones every task under the pack namespaces (`start.`, `govern.`, `combat.`) with a durable `task.transition` row that replays on restart; `StartMode` (vars, rule state, poll counter, completion flag), universal-rule cooldown state, and vitals diff state are all rebuilt; the dispatcher's hash becomes the newly loaded pack's so post-reset dispatches pass the drift check.
- **FR-1311**: pawn decision-matrix breadth (UR-BRN-021) — pack decision surfaces must cover per-pawn job assignment, work-type priorities, drafting, equipment/apparel, rescue, medical, and scheduling; pawn selection resolves through skill/trait/capability primitives (`best`, `arm_pawn`, per-pawn skill reads), never a fixed pawn.
- **FR-1312**: pack-controlled construction (UR-BRN-022) — site selection, build-space rects, layout direction, room orientation, and expansion geometry resolve from pack cfg/vars via primitives (`rank_site`, `fertile`, `free_cell`, `rect`/`cell`/`add` math); runtime code carries no layout constants.
- **FR-1313**: continuous-loop verification (UR-BRN-023) — a test cycles load → drive → unload → reload → drive repeatedly, asserting tombstoned namespaces, zero `dispatch.pack_drift`/`dispatch.no_pack` where writes are expected, and clean resume; failures are fixed, not tolerated.
- **FR-1314**: wind-turbine capability (UR-BRN-024) — policy fns `wind_path(cell, axis, half_width, depth, gap)` (the two corridor rects), `obstructions(rects, kinds)` (things inside rect(s) matching pack-chosen `map.find` kinds), `wind_obstructions(defs, …)` (union across every built generator's corridors), `turbine_site` / `turbine_site_blocked` (free_cell-style scans requiring a clear / an obstructed corridor), `find_defs`, `pos`, `terrain_at`, `zone_at`; templates `clear-vegetation` (`ui.designate` cut|harvest by things/cells/rect) and `lay-floor` (`ui.build` rect+fill). `govern.power.wind` cfg owns axis/half_width/depth/gap/site_kinds/clear_kinds/clear_designator/clear_cooldown/suppress/floor_def/grow_*. `establish-power-grid` clears a buildable-but-obstructed site before probing a clean one; `maintain-turbine-windpath` re-clears regrowth and suppresses it (floor → `lay-floor` both corridors per generator; grow → `create-growing` zones). `run_steps` evaluates `when`/`needs` per `for_each` candidate after `@var:it` binds — per-candidate predicates are first-class, not silently skipped.
- **FR-1315**: build-idempotency and placement correctness — a build step MUST gate on its own pending work (`blueprints(defs)` — matching `def`/`build_def`/`entity_def`/`defName` on blueprint rows, not the repeat guard alone) so an unbuilt frame never re-dispatches each poll; room-layout ops MUST skip while their wall/door frames stand; placement geometry MUST land cell targets (doors) on the structure's own wall cells. Field-verified against the 2026-09-23 over-build/sealed-room defects.
- **FR-1317**: post-start domestic build-out — once the start contract holds, govern goals build the mood/efficiency layer: a walled+roofed dining room with a table and chairs adjacent to it (`build-dining-room`, sized by `govern.dining`, chairs ≥ colonist count via `chair_offsets` probes around the table `pos`), an enclosed kitchen around the cook station (`enclose-kitchen`), one single bed per private bedroom (`private-bedrooms`), and floor maintenance over room interiors as a recurring mood buffer (`floor-rooms`, `lay-floor` per room, per-step `enclosed + terrain` gates + cooldown so it self-maintains as rooms appear). Central food/production, remote bedrooms, no maze geometry — layout is pack data (`govern.dining|kitchen|bedrooms|floors` cfg).
- **FR-1318**: room-scoped observation — `find_defs_in(defs, rect)` and `blueprints_in(defs, rect)` restrict thing/blueprint lookup to a rect so stray ruin furniture or remote frames never satisfy a room-local goal; `checker_cells(rect)` emits the alternating-parity cell set used for staggered trap floors that retain a diagonal colonist weave lane.
- **FR-1319**: declarative base blueprints — `govern.blueprints.<name>` carries named layout plans as pack data (rect, entrance gap, hallway depth, enclosure threshold); goals render a plan into build ops *and* verify effects from the same data, so construction and validation cannot silently disagree. `blueprints.compound` defines the killbox: a wall ring enclosing rooms/fields/power, exactly one open entrance (no door — the funnel) on the south wall row under the shelter door line, and a walled checkerboard-trap hallway outside the gap. `build-chokepoint-defense` designates the ring as wall segments (an `EdgeCells` rect cannot skip cells) + per-cell trap builds gated on `buildable_at` with `stuff`; effect = `enclosed_at(compound)` + scoped trap count.
- **FR-1320**: footprint-aware site selection — `site.search_w/search_h` size the `map.open_rects` query to the plan's bounding box and `anchor_dx/anchor_dy` shift `site.min` inside the chosen patch (each candidate stamped `anchor_off`) so negative-offset plan geometry lands on open ground; if no footprint-size patch exists the search falls back to the zone-size query with zero offset so cramped maps still bootstrap. Blueprints are sizes and offsets only — portable across maps, never absolute coordinates.
- **FR-1321**: coordinated colony defense — `defend-colony` orders every armed colonist onto their nearest living hostile in the same poll (`armed_ids`, `drafted_ids`, `nearest_hostile` fns); `ui.attack` is invoked without `melee` so the bridge auto-selects `AttackStatic` (shoot) vs `AttackMelee` from the equipped weapon; `chase-fleeing` drops its forced `melee: true`; `stand-down` undrafts when no living hostiles remain; `idle-work` skips drafted pawns so defenders aren't reassigned mid-fight.
- **FR-1316**: single-executable distribution (UR-ARC-009) — `rimbrain.py` is the one entry point: `run` launches the runtime loop and dashboard overlay together (overlay spawned as a subprocess, terminated on loop exit), `loop`/`overlay` run either side alone. `runtime/_root.py` splits roots — `repo_root()` (writable: repo dir in dev, exe dir frozen → `state/`, external `packs/`, external `profiles/`) vs `bundle_root()` (read-only: repo dir in dev, `sys._MEIPASS` frozen → schemas, RPC inventory, event map, bundled pack/profile fallback). `tools/rimbrain.spec` + `tools/build-exe.ps1` build `dist/rimbrain.exe` with the writable-side layout copied next to it. Bare `rimbrain run` defaults to the fair live-brain start pass.

### Success Criteria

- **SC-1301**: `test_hold_governs_after_completed` — held sim run continues past `start.completed`; all 10 `govern.*` goals (shelter, food, arming, chokepoint, medicine, mood, power, research-bench, research-progress, mission-offers) reach `succeeded` in declared order; a fresh letter re-arms the terminal goal on a subsequent held run. StartSim stubs cover trap/generator/healroot finds, Equip/Wear pool removal, and build pending types.
- **SC-1302**: `--no-hold` and cycle bounded start stop at `start.completed` with no `govern.*` tasks.
- **SC-1303**: `test_fair_mode_denies_debug` — fair dispatcher loads `start-mode-v0`; dev templates return `dispatch.unknown_action`; save/load refused per-dispatch; `dev-lab-v0` raises `pack.not_fair` at load.
- **SC-1304**: all packs pass `load_pack` validation with `goal_options` present; `improve-v0` unaffected.
- **SC-1305**: `test_views` — planning goals list ends with `govern.*` ids in pack-declared order.
- **SC-1306**: colony-goals catalog — 19 goals, all `prerequisites` resolve to catalog ids, every entry cites guide/wiki sources; uncertain claims documented in `colony-goals-v0.notes.md`.
- **SC-1307**: sim hold run verifies dining/kitchen/bedrooms/floors goals to `succeeded` — StartSim furnishes `built[]` rows via `furnish:` pending and answers `map.find` for `def`/`building` from them; compound goal verifies `enclosed_at` + scoped trap count (sim trap rows carry hall-rect `pos`).
- **SC-1308**: `test_site_ranking_applies_anchor_offset` — a footprint candidate stamped `anchor_off` yields `site.min = patch.min + offset`; sim `map.open_rects` returns empty over 9×9 so the fallback path is exercised every run.
- **SC-1309**: `test_all_armed_defend_together` — gun- and melee-armed colonists engage the same hostile in one poll (`melee` omitted → bridge auto-selects); unarmed pawns stay out; chase test asserts no forced melee.

## Constraints

- Govern work is ledger tasks through the single writer — no new write path; `govern:` sources appear in `decisions.jsonl` like any other pack element (UR-VIEW).
- Fair class is load-time enforced, not dispatch-time advisory: the tooling is absent, not merely refused (UR-BRN-018).
- `goal_options` carry strategy annotations (benefit/cost/threat), not executable steps — the catalog schema stays out of the policy engine; promoting an option is planner work or human editing.
- All wealth/raid-threat claims trace to the wiki mechanics baseline in the catalog header or to cited guide timestamps; unverifiable claims are recorded in the notes file, not asserted.

## Risks and open questions

- `goal_options` duplication across 3 packs + the standalone catalog drifts unless the catalog stays the authoring source (documented in pack comments).
- No observation signal for colony wealth yet — `cap-idle-wealth`/`invest-wealth-in-defense` can't be gated on observed wealth until a `state.wealth`-class capability exists (notes.md open question).
- `phase`/`prerequisites` are prose-level gating; predicate-form conditions (`{field,op,value}`) would let the review gate machine-check option eligibility.

## Traceability evidence

- `components/runtime/src/runtime/startmode.py` — `_drive` shared driver + `_govern_step`; `run_start(hold=)`; `loop.py --no-hold`; `cycle.py hold=False`.
- `components/runtime/src/runtime/dispatch.py` — `load_pack` fair-class dev-method refusal (`pack.not_fair`).
- `components/runtime/src/runtime/policy.py` — `research*`/`quests`/`letters` fns; `validate_policy` govern.goals checks.
- `components/runtime/src/runtime/views.py` — `govern.*` goal rows.
- `components/rimbrain/packs/dev-lab-v0.yaml` (new, `class: dev`; mirrors `start-mode-v0`'s `govern` block + research/letter templates); `start-mode-v0`/`core-survival-v0`/`improve-v0` `class: fair`; `colony-goals-v0.yaml` + notes; `goal_options` embedded in the three gameplay packs.
- `components/contracts/schemas/runtime/pack.schema.json` — `class`, `govern`, `goal_options` properties.
- `components/rimbrain/capability-catalog.yaml` — research/quests/letters entries `implemented`.
- Tests: `test_startmode.py::test_hold_governs_after_completed`, `test_universal.py::test_fair_mode_denies_debug`, `test_views.py` govern ordering, `test_combat.py`/`test_cycle.py` dev-lab loading; StartSim research/letters stubs.
- `components/runtime/src/runtime/startmode.py` — footprint-aware `map.open_rects` query + `anchor_off` stamping + 9×9 fallback; `policy.py` — `find_defs_in`, `blueprints_in`, `checker_cells`, `armed_ids`, `drafted_ids`, `nearest_hostile`, `rank_site` offset.
- `components/rimbrain/packs/start-mode-v0.yaml` — `govern.dining|kitchen|bedrooms|floors` cfg; `build-dining-room`, `enclose-kitchen`, `private-bedrooms`, `floor-rooms` goals; `govern.blueprints.compound` + rebuilt `build-chokepoint-defense` (wall segments, open entrance, checkerboard trap hall); `defend-colony`/`stand-down` rules + `chase-fleeing`/`idle-work` updates; `site.search_*`/`anchor_*`.
- Tests: `test_startmode.py` — StartSim `furnish:` pending → `built[]`, trap rows with hall pos, size-aware `open_rects`, `test_site_ranking_applies_anchor_offset`; `test_universal.py` — `test_all_armed_defend_together`, ranged-aware chase.
- **Live status**: compound/killbox implemented and sim-verified; live validation pending — bridge down at the time of this change (RimWorld not running). Pending live actions: cancel 8 stray trap designations inside the compound footprint, then resume the 10-iteration loop.
