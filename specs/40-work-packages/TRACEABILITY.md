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

