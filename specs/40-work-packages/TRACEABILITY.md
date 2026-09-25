# Requirements traceability matrix

**Status:** READY  
**Rule:** This matrix is updated with concrete test/report links during implementation.

| Requirement set | Owning component | Primary work packages | Required evidence |
|---|---|---|---|
| UR-CTL-001..002 | Runtime | WP-100, WP-200, WP-201 | import/capability audit; action log writer identity |
| UR-CTL-003..004 | Contracts, Runtime | WP-002, WP-201 | schema tests; dispatcher validation fixtures |
| UR-CTL-005..008 | Runtime, Steward | WP-103, WP-200, WP-203, WP-402 | emergency no-provider audit; stale result and controller isolation tests |
| UR-RUN-001..004 | Runtime | WP-101, WP-102, WP-104 | forced crash/recovery and lifecycle fixtures |
| UR-RUN-005..007 | Runtime | WP-103, WP-400 | dead-man, circuit breaker, hysteresis/dwell tests |
| UR-RUN-008 | Runtime, Contracts | WP-301 | cancel/timeout/stale correlation fixtures |
| UR-RUN-009 | Runtime, RimBrain | feature 015 | `startmode._govern_step` + `run_start(hold=)`/`--no-hold`/`cycle hold=False`; `test_hold_governs_after_completed` (govern goals dispatch/verify/re-arm on lapse); `govern.*` rows in planning view; `colony-goals-v0` catalog embedded as `goal_options` (19 annotated strategy options; inert data — promotion via govern/plans only) |
| UR-SUR-001..004 | Runtime | WP-103, WP-400, WP-600 | labeled-save TTC/runway/site fixtures |
| UR-SUR-005..006 | Runtime, RimBrain | WP-103, WP-203, WP-300 | posture transitions; dispatcher invariant rejection |
| UR-SUR-007 | Runtime, Lab | WP-202, WP-400, WP-501 | death/near-miss post-mortem fixture creation |
| UR-SUR-008..009 | Lab, Runtime | WP-400, WP-601 | lexicographic report; progress/pause/stall results |
| UR-MOD-001..003 | Runtime, Contracts | WP-301 | provider swap and closed-choice tests |
| UR-MOD-004..005 | Runtime, Lab, RimBrain | WP-302, WP-601 | row qualification/calibration/demotion/fallback fixtures |
| UR-MOD-006 | Runtime | WP-303 | planner-trigger audit |
| UR-MOD-007..008 | Runtime, Contracts | WP-301, WP-303 | packet budget/freshness/hash/injection fixtures |
| UR-MOD-009..010 | Runtime, RimBrain | WP-303 | proposal schema, pre-mortem, critique, repair tests |
| UR-BRN-001..003 | RimBrain, Contracts | WP-300 | pack validation/reference/canonicalization tests |
| UR-BRN-004..006 | Runtime, RimBrain | WP-300, WP-602 | scored freeze, proposal isolation, atomic activation/rollback |
| UR-BRN-007..009 | RimBrain, Lab | WP-300, WP-501, WP-602 | hash/signature/trust and fixture-ratchet CI |
| UR-BRN-010 | Runtime, Lab | WP-202, WP-602 | 100% due predictions scored/clustered without model call |
| UR-BRN-011..014 | Runtime, RimBrain, Contracts | feature 012 (T155..T162), ADR-015 | `policy.py` engine + pack-driven start/combat/universal; pack-mutation tests (SC-1001..1003); `validate_policy` fail-closed; `policy_version` in pack schema; live: pack-driven start mode completed all exit conditions on a real colony (shelter/beds/food/meals/recreation), pack idle-rule assigned real jobs |
| UR-BRN-015..017 | RimBrain, Runtime, Contracts | feature 014 (T167..T170) | `capability-catalog.yaml` (170 entries / 33 domains, wiki-cited); `capability_audit.py` baseline+live diff (115/115 mapped, 0 drift); registry↔catalog consistency tests; schema forbids policy fields |
| UR-BRN-018 | RimBrain, Runtime, Contracts | feature 015, ADR-017 | `class: fair|dev` in `pack.schema.json`; `dispatch.load_pack` refuses dev-method packs under fair (`pack.not_fair`); `dev-lab-v0` owns spawn/heal/combat scripting; `test_fair_mode_denies_debug` (dev actions = `dispatch.unknown_action`, dev pack refused at load) |
| UR-BRN-019..023 | Runtime, RimBrain, Dashboard | feature 015 | `brain_reset.request`/`brain_status.json` channel (refresh/swap/unload, fail-closed); `ledger.reset_ns` tombstones; `test_brain_reset_unload_reload_loop` (5 cycles: refresh → unload → reload → swap → durable replay); live reset via overlay channel dropped 28 tasks and re-derived cleanly |
| UR-BRN-024 | Runtime, RimBrain | feature 015 | `wind_path`/`obstructions`/`wind_obstructions`/`turbine_site`/`turbine_site_blocked`/`find_defs`/`pos`/`terrain_at`/`zone_at` fns; `clear-vegetation`+`lay-floor` templates; `govern.power.wind` cfg owns corridor geometry/kinds/designator/suppression; `run_steps` evaluates `when`/`needs` per `for_each` candidate; `test_turbine_sited_cleared_and_windpath_suppressed` (site veto, cut-designation, corridor flooring) |
| UR-ARC-009 | Runtime, Dashboard, RimBrain, Contracts | feature 015 | `rimbrain.py` unified launcher (`run`/`loop`/`overlay`; bare `run` = fair live-brain start pass); `runtime/_root.py` `repo_root()`/`bundle_root()` split; templates/dispatch/store/registry/eventmap frozen-aware; `tools/rimbrain.spec` + `tools/build-exe.ps1` → `dist/rimbrain.exe` with writable `state/ packs/ profiles/` beside it; sim smoke + lifecycle loop identical frozen vs dev |
| UR-RL-007 | Runtime, RimBrain | feature 021, ADR-020 | `fastevolve.py` day-session controller; `Dispatcher(allow_save_load=)` scoped grant; `evolve.promote_candidate` shared mid-run install; `fastevolve:` pack section + schema/validator; `test_fastevolve.py` (24) |
| UR-VIEW-001..004 | Runtime | feature 013 (T163..T166) | `views.py` planning/actions renders + `decisions.jsonl` per-poll records wired into start/combat/loop; live start run rendered real goals/matrix; fail-open render test |
| UR-DAT-001..003 | Runtime, Contracts | WP-101 | durability/torn-tail/atomic Windows tests |
| UR-DAT-004..005 | Runtime, Lab | WP-104, WP-202, WP-500 | complete decision projection; unchosen-label check |
| UR-DAT-006 | All | WP-002, WP-300, WP-500 | secret/path scans and malicious pack/export cases |
| UR-DAT-007 | Runtime, Lab, Dashboard | WP-101, WP-500, WP-502 | rebuild-from-canonical tests |
| UR-EXP-001..004 | Lab, Contracts | WP-500 | schema-valid profile and trajectory golden tests |
| UR-EXP-005..008 | Lab | WP-500 | redaction, checksum, data card, assistance, split leakage, immutability tests |
| UR-EXP-009 | Lab | WP-500, WP-501 | independent verifier/reconstruction/replay report |
| UR-ARC-001 | All | WP-000, WP-100 | dependency graph/static import tests |
| UR-ARC-002 | Superproject | WP-000 | clean recursive checkout/release manifest check |
| UR-ARC-003 | RimBridge, Steward, Runtime | WP-203, WP-402 | capability-gap review and bridge policy scan |
| UR-ARC-004 | Contracts, all consumers | WP-002 onward | shared corpus provider/consumer CI |
| UR-ARC-005 | Superproject, Steward | WP-000, WP-402 | license/notice audit |
| UR-ARC-006 | Superproject | all | work-package gates and this matrix |
| UR-ARC-007 | Dashboard, Lab | WP-500, WP-502 | no-internal-import/direct-control tests |
| UR-ARC-008 | Superproject, Runtime | WP-000, WP-601 | ranked dirty-state rejection fixture |

## Acceptance scenario trace

| Scenario | Requirements demonstrated | Planned rung |
|---|---|---|
| Forced crash after uncertain write | CTL-004/006, RUN-003/004, DAT-001..003 | integration fault injection |
| Bleeding pawn during provider timeout | CTL-005, SUR-001..003, MOD-005 | emergency fixture + live bounded scenario |
| Laya returns unoffered option late | CTL-006, RUN-008, MOD-003/005 | provider contract fixture |
| Cold snap invalidates crop plan | SUR-004/005, MOD-006/009, BRN-003 | replay + matched scenario |
| Community pack path escape/tamper | BRN-007/008, DAT-006 | pack security test |
| Export training split leakage | EXP-004..007 | export golden/privacy test |
| Dashboard resume with independent hold | CTL-007, ARC-007 | API/UI E2E |
| Pack regression after activation | BRN-004..006/009 | monitored cohort rollback exercise |

## Evidence format

Each implemented row eventually links:

- component version/commit;
- test ID and CI run artifact;
- fixture/save family/hash;
- result summary and date;
- known limitations/waivers;
- approving reviewer for human gates.

No requirement moves to `IMPLEMENTED` from code presence alone.

## Feature 017 — unified phase engine (FR-1401..1430)

| Requirement | Evidence |
|---|---|
| FR-1401 single loop, fixed stage pipeline | `runtime/loop.py::run()`; `test_phase.py`, `test_loop.py` (polls drive observe→reflex→rules→plan→select→phase→views→reflect) |
| FR-1402 start behaviors inside the loop | `phase.py` prescriptive steps + exit conditions + standing goals; ported `test_phase.py` (45); brain-reset/vitals/reflect in `run()` (`test_brain_reset.py`, `test_evolve.py`) |
| FR-1403 ordered `phases`, prescriptive init | `pack.schema.json` v1 roots; `phase.py`; `test_phase.py` |
| FR-1404 v0 namespace auto-migration | `templates.migrate_v0`; `test_pack_migration.py` |
| FR-1405 one predicate dialect | `dispatch.py` reflexes evaluate via `policy.check`; `test_dispatch.py` reflex cases |
| FR-1406 canonical observation | `observe.py::sections`; consumed by reflexes/rules/select/planstage/views |
| FR-1407 ≤20-item candidate list | `select.py::compile_actions` cap; `test_select.py` cap tests |
| FR-1408 offered-ids-only + fallback | `select.py` invalid/absent pick → `fallback` flag + `select.invalid` event; `test_select.py` |
| FR-1409 select inputs from canonical obs+ledger | `select.py` digest ctx (stocks/pawns/metrics/plan); `test_select.py` |
| FR-1410 prescriptive init deterministic + select-driven pawns | `PhaseEngine.goal_sources` empty colony scope while prescriptive active; `test_phase.py`, `test_select.py` |
| FR-1411 select decision logging | select rows carry `offered`/`pick`/`applied`/`fallback`/`shadow`/`inputs_hash`; `test_select.py` |
| FR-1412 plan cadence/boundary/event triggers | `planstage.tick`; `test_planstage.py` (first-fire/cadence/boundary/events) |
| FR-1413 plan reorder/activate/deactivate/promote | `planstage` gate+apply, `PhaseEngine.apply_plan`; `test_planstage.py::test_activate_deactivate_and_promote`, `test_goal_order_feeds_select_scoring` |
| FR-1414 planner failure → last plan in force | `test_planstage.py::test_outage_degrades_and_prior_plan_stands`, `test_gate_rejects_unknown_ids_and_last_plan_stands` |
| FR-1415 gate before adoption | `planstage._gate`; `test_planstage.py::test_gate_rejects_bad_params_and_dev_class` |
| FR-1416 one reflection pipeline | `evolve.py` digest→propose→compile→`validate_candidate`→boundary; `test_evolve.py` (32) |
| FR-1417 whitelist covers all surfaces | `packmut.py` whitelist `phases`/`action_list`/`decide`/`reflexes`/`rules`/`options`/`senses`/`metrics`; `test_evolve.py` surface round-trips |
| FR-1418 boundary-only promotion + auto-revert | `evolve.boundary`/`materialize_candidate`; `test_evolve.py` lineage/revert tests |
| FR-1419 improve preserved as evidence | `improve.py` reduced to `diagnose`/`score`/`predict_metrics`; `test_improve.py` green |
| FR-1420 sim: zero endpoints, identical streams | `test_determinism.py::test_sim_episodes_bit_identical`, `test_sim_never_resolves_an_endpoint` |
| FR-1421 live model assistance always wired | `run()` injects resolved caller for `--game live`; select live-rung path in `test_select.py` |
| FR-1422 mode surface | `loop.main` `--mode run|cycle|improve` × `--game sim|live` × `--stage`; deprecated aliases warn; `test_loop.py` flag matrix |
| FR-1423 flag interaction fail-closed | `test_loop.py` invalid-combination cases (cycle/combat need `--dev`, `--live-mutate` only run+live) |
| FR-1424 selector authority ladder | `select.py` rungs shadow→trial→live, per-tuple `_note_pick` persistence; `test_select.py` rung tests |
| FR-1425 duplicate engines deleted | `universal.py`/`combatmode.py`/`mutate.py` removed; `startmode.py` shim only; suite green post-deletion |
| FR-1426 gates merged | `evolve.validate_candidate` shared by pass-gate/boundary/materialization; `test_evolve.py` |
| FR-1427 consolidated run state | `runstate.py::RunState` owns vars/phase/plan/rule/improve/vitals; persisted per run |
| FR-1428 unified views | `views.phase_snapshot` select/plan/reflection fields; overlay renders them; `test_views.py` |
| FR-1429 combat pack-ified | `kind: combat` phases driven by `run(stage="combat")`; `combatmode.py` deleted; `test_combat.py`, `test_cycle.py` green |
| FR-1430 select cadence skip-not-queue | `decide.select.cadence_polls` in `select.decide`; `test_select.py` cadence case |

Suite evidence: 239/239 green at Phase 5 checkpoint; focused evolve/planstage/select suites green per phase.

## Feature 021 — fast-evolve play mode (FR-2101..2112; ADR-020)

| Requirement | Evidence |
|---|---|
| FR-2101 `fastevolve` play option, non-default, scored-refused | `loop.main` `--mode fastevolve`; `loop.fastevolve_scored`/`loop.fastevolve_requires_fair`/`loop.live_requires_confirmation`; `test_fastevolve.py` CLI cases |
| FR-2102 durable day session | `fastevolve.DayState` -> `state/fastevolve.json` (outside RunState); `test_daystate_roundtrip` |
| FR-2103 autosave anchor via `game.list_saves` | `fastevolve.AutosaveTracker` (pattern filter, earliest day-start match wins, stale fallback bounded by `max_anchor_age_days`); tracker tests |
| FR-2104 dual trigger sources, all pack data | `fastevolve.check_day_triggers` — `fail_when`/`near_when` via `policy.check` + `evolve.check_triggers` under `triggers.use_mutate`; `test_use_mutate_*` |
| FR-2105 pause -> reflect -> mid-run promote -> reload -> reinit | `FastEvolve.tick` orchestration; `evolve.promote_candidate(mid_run=True)` + `load_pack` rebind; loop reinit = brain-reset wipe; `test_failure_trigger_evolves_and_reloads`, `test_pause_during_evolve`, `test_midrun_promotion_installs_and_rebinds` |
| FR-2106 <=2 reloads/day, exhausted days evolve-only | `DayState.reloads_used`/`exhausted`; `test_two_reloads_then_exhausted`, `test_zero_reload_budget_evolves_only` |
| FR-2107 scoped save/load grant, single writer | `Dispatcher(allow_save_load=)` lifts only `game.save`/`game.load`; `dev.*` stays refused; `test_fair_grant_is_scoped` |
| FR-2108 mid-run promotion integrity | `evolve.promote_candidate` (revalidate, parent backup, `mid_run` lineage row, `mutation.promoted`); hash rebind; `test_midrun_promotion_installs_and_rebinds` |
| FR-2109 canonical events + status view | six `fastevolve.*` events -> feed narration; `planning.json` `fastevolve` block + overlay `fe:` tag; `test_event_sequence_and_planning_block` |
| FR-2110 retry policy is pack data | `fastevolve:` pack section + `pack.schema.json` property + `templates._fastevolve_problems` validation; `test_invalid_predicate_fails_pack_load` |
| FR-2111 deterministic sim exercise | `SimGame` named save/load + `game.list_saves` `{name, modified}` + `sim_autosave` hook + `game.pause`/`game.speed`; `test_simgame_save_load_roundtrip` |
| FR-2112 failure-triggered-only passes | `run()` bypasses generic per-poll `maybe_trigger` under `fast_evolve`; only `FastEvolve.tick` invokes the pass; `test_no_trigger_is_inert` |

Suite evidence: 266/266 runtime tests green post-implementation (248 prior + 18..24 fast-evolve cases).

## Feature 018 — guided launcher UI (FR-001..024)

| Requirement | Evidence |
|---|---|
| FR-001 menu by default, `-y` skip, flags headless | `rimbrain.py` arg routing (bare/`run` → setup overlay + return; `run -y` sole-arg → fair preset; `-y` + flags → exit 2); smoke: `python rimbrain.py` → live `--setup` window, `run -y --mode sim` → exit 2 |
| FR-002 declarative param grid | `dashboard/paramspec.py::PARAM_SPEC` (all 16 loop flags); `test_paramspec.py::test_every_loop_flag_has_a_row` |
| FR-003 fair-run defaults | `paramspec.defaults()`; `test_paramspec.py::test_defaults_match_fair_preset`, `test_argv_defaults_equal_run_y` |
| FR-004 constraint mirror | `paramspec.violations()` mirrors `loop.main` fail-closed checks + dev-pack gate; `test_paramspec.py` violation matrix (cycle/dev, live confirm, live-mutate gate, fastevolve fair/scored, combat stage, dev pack) |
| FR-005 GO spawns visible argv | `SetupFrame._go` → `RunHandle.spawn(paramspec.argv(cfg))`; verbatim preview label on Setup |
| FR-006..008 role rows + live role-shaped verdicts + fallbacks | `runtime/probe.py::probe_live` (decide/chat/embeddings shapes; verdicts answered/model_failed/unreachable/missing_secret/fallback_only/unbound + `fallbacks` verbatim); `test_probe_live.py` (9) |
| FR-009 off-thread checks, checking state, never blocks GO | `brains.check_all` thread-per-role → `queue.Queue` drained on refresh; `test_brains.py::test_check_all_*` |
| FR-010 facade-only probing | `runtime/api.py::probe_live`; dashboard imports `runtime.api` only (`_RUNTIME_OK` guard, same as `server.py`) |
| FR-011..012 pack list w/ class badges + lineage, dev gating | `scan_pack_descriptors` (class/pack_id/derived_from, fail-open fair); Setup radio list disables dev under fair + `violations` blocks GO; `test_paramspec.py::test_dev_pack_blocked_under_fair` |
| FR-013 mid-run swap via reset channel | Setup "Use (live swap)" + monitor Use → `write_reset_request({"pack": id})` (unchanged channel) |
| FR-014 outline by pack structure | `packedit.build_outline` (v0→v1 label map; v1 sections when present); `test_packedit.py` outline cases |
| FR-015 typed forms | `PackEditor` dispatch: scalars→typed controls, predicates→builder, steps→template dropdown + `params_schema` param rows, lists→add/del/reorder |
| FR-016 freeform + insert-assist | string fields keep text entry; insert combobox fed by `api.policy_vocabulary()` only (no copied table) |
| FR-017 helper text | template `description:` rendered under step; field hints on Setup rows |
| FR-018 loader-identical save gate | `api.validate_pack_doc` runs migrate→schema→inventory→policy as a pure fn; `test_packedit.py::test_validate_wiring_via_facade` |
| FR-019 save-as-new + lineage | `packedit.save_as_new` → `packs/<name>/pack.yaml` (`pack_id: pack.<name>`, `derived_from`, slug `[a-z0-9-]+`, candidates refused); `derived_from` added to `pack.schema.json`; `test_packedit.py` save cases |
| FR-020 raw mode retained | PackEditor "Raw YAML" tab (in-place write + reset when active) |
| FR-021 window owns loop child | `RunHandle` (spawn/poll/terminate-kill); monitor status line each refresh; close → terminate |
| FR-022 mid-run setup, params read-only | running greys argv controls + "applies to next run"; pack/brains/editor live; `_refresh` flips editability on state change |
| FR-023 restart applies edited argv | GO → "Restart run" (confirm → terminate → respawn); monitor Restart → Setup |
| FR-024 overwrite-active pairs write+reset | `PackEditor._save_new` active-name path: confirm "hot-swaps the live brain" → write + `brain_reset.request {}` |

Suite evidence: `test_probe_live.py` (9), `test_paramspec.py` (14), `test_brains.py` (10), `test_packedit.py` (12); combined dashboard+runtime run 324/324 green (also fixed `api.probe_cache` returning a copy — `.clear()` callers got a no-op — and catalogued the 021 `upgrade_*`/`equip_pending` fns). Frozen parity: rebuilt `dist/rimbrain.exe` — bare exe spawns `overlay --setup` beside `dist/state|packs`, `run -y --mode sim` exits 2, `run --mode sim` headless run identical to dev.

## Feature 020 — building / room capability (FR-2001..2009, SC-2001..2006)

| Requirement | Evidence |
|---|---|
| FR-2001 declarative room archetypes | `rooms:` pack block (`pack.schema.json` `room_archetype` with `size`/`tier_target`/`stat_target`/`wall`/`door`/`floor`/`furniture` incl. `count`/`anchor`/`linked_to`/`adjacent_to`/`separate`/`optional`/`links`/`at`); `start-mode-v0` ships `bedroom`/`dining_hall`/`hospital`/`kitchen`/`workshop`; `test_room_contract.py::test_room_archetype_field_validation`, `test_shipped_pack_rooms_cfg_validates` |
| FR-2002 deterministic `plan_room` compile | `policy._fn_plan_room` — walls as outline line segments (door cell excluded), perimeter door, floor fill, furniture honoring link radius (`def_stats.linkable_range`)/adjacency/separation/optionality; null on unfit rect/unknown def/region bound; existing-structure merge/split safety; `test_rooms.py::test_plan_room_*` (compile, unfit null, unknown def, optional skip, overlap/re-issue, region bound, determinism) |
| FR-2003 space-tier profiles | `rooms.tier_table` + `mods.realistic_rooms_rewritten.settings`; `_tier_profile` resolution live `defs.get(Space).scoreStages` → cfg → vanilla with one `rooms.profile_fallback` event per run; `space_tier`/`space_target`; `test_rooms.py::test_space_tier_profile_vanilla_vs_modded`, `test_tier_cfg_override_honored`, `test_detection_failure_falls_back_to_vanilla_once` |
| FR-2004 bedroom demand + right-sizing | `bed_demand()` (residents − couples − owner-assigned private bedrooms, per-poll pawn-detail cache); `expand-housing` demand-gated `plan_room` goals; `test_bed_demand_counts`, `test_material_delta_30pct_and_equal_mood` |
| FR-2005 barracks → private conversion | atomic target-bed-first owner assignment in sim materialization + `assign-job` LayDown reassignment path; `private-bedrooms` goal; `test_conversion_zero_bedless_ticks` |
| FR-2006 archetypes are pure pack data | archetype additions need data edits only; `test_synthetic_archetype_data_only` (workroom archetype absent from shipped packs loads + compiles); no runtime change |
| FR-2007 idempotent re-issue | `ui.build_many` bridge semantics (same-blueprint/building skip); `plan_room` same-bounds re-issue compiles; `test_plan_room_existing_structure_merge_split_safety` |
| FR-2008 housing as standing goals | `expand-housing`/`private-bedrooms`/`build-dining-room`/`build-hospital`/`build-workshop`/`enclose-kitchen` — `when` gates on `bed_demand`/`pawns_with_thought`/`pawns_wounded`/cookstation, `effect` on role+stat predicates; `test_dining_goal_fires_on_thought_and_verifies`, `test_hospital_goal_fires_on_wounded_and_verifies`, `test_kitchen_butcher_separate_placement` |
| FR-2009 single-writer dispatch | room ops go through `build-layout`/`assign-job` templates on the existing dispatcher; no new dispatch authority; phase-engine sim run completes shelter via `plan_room` ops (`test_bedroom_builds_in_sim_and_verifies_role_stat`, full-suite phase tests) |
| SC-2001 zero hand-written op coordinates | pack room goals pass `ops: "@fn:plan_room(...).ops"` — no coordinates in pack data; `test_bedroom_builds_in_sim_and_verifies_role_stat` |
| SC-2002 ≥30% wall-material savings at equal mood | `test_material_delta_30pct_and_equal_mood` — tier-targeted 4×3-class bedroom (mod profile) vs legacy 7×7 expansion geometry, impressiveness ≥ legacy band |
| SC-2003 correct profile selection | `test_space_tier_profile_vanilla_vs_modded` (29.0 vs 16.5 average thresholds, differing footprints), `test_tier_cfg_override_honored` |
| SC-2004 role+stat verification only | `templates._room_goal_problems` lint rejects `enclosed_at`-only room-goal effects at load; `test_enclosed_at_only_room_goal_rejected`, `test_role_stat_effect_accepted`, `test_non_room_enclosed_at_goals_unaffected` |
| SC-2005 data-only archetype addition | `test_synthetic_archetype_data_only` |
| SC-2006 failed/undersized rects recorded | `plan_room` null on unfit rect → step `blocked`; `test_plan_room_unfit_rect_returns_null`; `rooms.plan_warning` decision events for non-fatal skips |

## Feature 019 — combat capability (FR-1901..1910, SC-1901..1906)

| Requirement | Evidence |
|---|---|
| FR-1901 catalog actions (move/cancel/set-area/hostility/gizmo/order/tend/capture/ingest/hunt/guard/rally/run/release) | `capability-catalog.yaml` +47 entries; pack `combat-defense-v0` `capabilities.templates`; `test_combat_capability.py` dispatch assertions |
| FR-1902 classification as data | `combat:` cfg block (`pack.schema.json` properties; `_combat_cfg` incl. `dev_combat:` fallback for harness packs); `templates._combat_script` shape-gate keeps cfg vs 010-script distinct; `test_combat_capability.py::test_*` classification rows |
| FR-1903 selectors/fns | `policy.py` combat fns + `_SELECTORS` (`fighters`/`draftable`/`engaged_hostiles`/`watching_hostiles`/`hostiles_in_home`/`manhunters`/`casualties`); `test_combat_capability.py` (classification/eligibility/mix/power/range cases) |
| FR-1904 pawn options + deterministic fallback | `decide.select.pawn_scope` in `combat-defense-v0` (7 options, `option_weights` priorities); `test_pawn_scope_*` (compile bound, priority-head fallback, direct dispatch) |
| FR-1905 state machine + hysteresis | `combat_mode` (watch/engage/hold/overrun) + `ticks_since_hostile` release window + `prolonged_ticks`; `test_combat_mode_watch_engage_hold_overrun`, `test_sim_delegate_combat_lifecycle` |
| FR-1906 fair-class | `combat-defense-v0` `class: fair`, zero `dev.*`; harness combat stays in `dev-lab-v0` (`combat:` script shape-gated) |
| FR-1907 touch interlock / delegate | `_pawn_touched` via `steward.orders.explain.hands_off`; absent steward → not touched, unreadable surface → excluded (conservative); `test_draftable_touch_interlock` |
| FR-1908 decision/lifecycle evidence | `combat-evidence` rule kind → posture snapshots; gate-transition clause rows (`check_detail`); `combat.overrun`/`combat.prolonged`/`combat.released` markers (duration/peak/casualties); `test_combat_evidence_rule_records_snapshot`, `test_gate_rows_carry_clause_reasons` |
| FR-1909 distinct rally cells | `rally_cell` cover-preferring greedy spread, persisted assignments; `test_rally_cells_are_distinct_per_fighter` |
| FR-1910 suppression of bad moves | `safe_cell`/`kite_cell` return null under `near_hostile`/outranged+outrun → option unoffered; `test_pawn_scope_retreat_suppression_and_offer`, `test_kite_suppressed_when_outranged` |
| SC-1901 delegate arm/engage/release lifecycle | `test_sim_delegate_combat_lifecycle` (SimGame order stub: set→draft→kill→600-tick release) |
| SC-1902 no attacks on downed/fogged/friendly | `_engage_kind`/`_is_friendly` exclusions; `test_excluded_hostiles_never_engage` |
| SC-1903 fallback = argmax-priority | `test_pawn_scope_fallback_is_priority_head` |
| SC-1904 fair/dev separation | schema `combat`/`dev_combat` props; `_combat_script` gate; `test_*` + `test_universal.py::test_phases_come_from_pack` (harness phases unchanged) |
| SC-1905 deterministic endpoint-down | caller=None → shadow → `priority_head`; `test_pawn_scope_fallback_is_priority_head` |
| SC-1906 recovery ordering | rescue → field-tend → capture(gated `free_beds('prison')`) → strip(when Home clear); `test_rescue_*`, `test_capture_*`, `test_strip_*` |

Suite evidence: `test_combat_capability.py` (28) + full runtime regression green vs T003 baseline (280/281; `test_phases_come_from_pack` intermittently flaky pre-019).
