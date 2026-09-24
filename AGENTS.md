# RimBrainAgent project rules

## Current phase

Features 001-005 implemented 2026-09-22: 001 fork bootstrap + contracts + sealed baseline; 002 model-endpoint registry + role bindings; 003 checkpoint-retry debug loops (live smoke passed); 004 dispatcher single-writer + core-survival pack v0 (`python -m runtime loop --mode sim` - sim loop must never wire to the real bridge; dispatcher writer target = SimGame in sim mode); 005 planner/review loop (`python -m runtime plan --mode sim` - typed PlanProposals via rimbrain.plan, deterministic review gate is decisive (code decides, model advises), accepted mutations materialize `packs/candidates/` never the active pack, plan actions dispatch through the single writer only, `rules-only` fallback = pack `fallback_plan`). 006 event/state stores (`runtime/store.py` append-only canonical JSONL + torn-tail recovery + `recovery.jsonl`; `project.py` disposable projection; loop/plan persist by default under `state/`); 007 task ledger (`runtime/tasks.py` declared lifecycle `proposed->locked->dispatched->verifying->succeeded|failed|expired`, verifier-only success via `{field,op,value}` effect specs, all-or-nothing tick-expiring resource locks, `task.transition` log in `state/tasks.jsonl` + `cursor.json`, `run_loop(ledger=)` reconciles before attend); 008 fresh-start mode (`runtime/startmode.py` deterministic bootstrap graph over the TaskLedger — `site->zone->unforbid->shelter->roof->haul->beds/food/recreation`, per-phase effect specs verified against observed state, site ranking over `map.open_rects` persisted via `anchor.set` + `startmode.json`, established-colony skip = zero writes, `start.completed` only on the verified exit contract; `python -m runtime loop --mode start --live`; pack `components/rimbrain/packs/start-mode-v0.yaml`); 009 self-improvement loop (`runtime/improve.py` bounded diagnose→propose→audit→validate→promote-at-boundary cycles over canonical evidence; `audit.py` code/policy/ux verdicts; `feed.py` thought feed `--feed` → `state/feed.md`; `metrics.py` episode learning metrics; `improve-v0.yaml` pack; `components/rimbrain/CUSTOMIZE.md`). 010 iterated cycles (save→start→combat→improve per iteration, checkpoint restore, `cycle.completed`); 011 universal pawn rules + start-mode v2 (no idle pawns, downed/fleeing discipline, strip sweeps, arming, fertile rice, overflow stockpile); 012 brain policy engine — `policy.py` capability primitives, all gameplay policy in packs (ADR-015); 013 transparency views (`views.py` — `state/planning.{json,md}` goals view + `state/actions.md`/`decisions.jsonl` quick-action matrix, fail-open per-poll renders); 014 capability catalog (`components/rimbrain/capability-catalog.yaml` audited wiki-cited inventory + `tools/capability_audit.py` baseline/live diff). 015 post-start governance (UR-RUN-009/UR-BRN-018): `run_start(hold=True)` continues past `start.completed` into pack `govern.goals` — ordered standing objectives with `when` gates + verifier-checked `effect`s that re-arm on lapse (research via `ui.set_research`/`steward.research`, mission offers via `state.letters`/`ui.letter`); `start-mode-v0` is `class: fair` (zero `dev.*`), combat/spawn tooling moved to `dev-lab-v0` (`class: dev`, refused at load under `--fair`); `colony-goals-v0.yaml` is the planner's strategy catalog. Upstream stays read-only. Next: observation/shadow controller (WP-103/104) or Steward protocol extraction (Phase 4).

015 post-start governance + brain lifecycle + wind turbine + single-executable (in progress, 2026-09-23): `run_start` no longer stops at `start.completed` — standing govern goals (storage maintenance, hunting hysteresis, mining, housing, power, research, missions, stability) keep dispatching, re-arm on effect lapse, and back off after failed convergence (`retry_polls`) so no single blocked goal starves the poll. Steward stock targets are the lever for hunting/mining (`steward.stock.set`/`run`), not `ui.set_work` — the in-mod Steward owns work priorities; `stocks.nutrition` is the food-runway metric; `state.storage` lists live zones. Brain reset channel `state/brain_reset.request`→`brain_status.json` honors `{}` refresh / `{"pack": id}` swap / `{"unload": true}`; `ledger.reset_ns` tombstones are event-log durable; universal rules + `mode.step` + planning gate on loaded mode; `--live-brain` enables it (`test_brain_reset_unload_reload_loop`). Wind: `wind_path`/`obstructions`/`wind_obstructions`/`turbine_site`/`turbine_site_blocked`/`find_defs`/`pos`/`terrain_at`/`zone_at` fns + `clear-vegetation`/`lay-floor` templates; `govern.power.wind` cfg owns corridor geometry/kinds/suppression; `run_steps` evaluates `when`/`needs` per `for_each` candidate after `@var:it` binds (engine bug found + fixed). Single exe: `rimbrain.py` unified launcher (`run` = loop+overlay, defaults to fair live-brain start pass; `loop`/`overlay` subcommands); `runtime/_root.py` `repo_root()` (writable: exe dir frozen / repo dir dev → `state/`, external `packs/`+`profiles/`) vs `bundle_root()` (read-only MEIPASS → schemas, inventory, event map, bundled fallbacks); `tools/rimbrain.spec` + `tools/build-exe.ps1` → `dist/rimbrain.exe`; `contracts/eventmap.py` has its own frozen branch (contracts can't import runtime). Spec: UR-ARC-009 + UR-BRN-019..024, FR-1300..1316, constitution v1.2.0 (Principle X brain lifecycle + pack-class/single-exe/standing-goal constraints). Suite: **271 passed** 2026-09-23.

Packs are folder-per-pack: `packs/<id>/pack.yaml` (+ aux files inside; `colony-goals-v0/notes.md`); flat `<id>.yaml` is a fallback (`candidates/` materialize flat). `templates.pack_path(id)` resolves (folder first) + refuses `..`/absolute ids; `templates.list_packs()` discovers both forms. Overlay `--packs-dir` enables a pack picker — **Use** posts `{"pack": id}` to `brain_reset.request` = live swap with full state wipe (fresh-eyes reinit); Edit Brain edits the selected pack. `rimbrain.py` seeds `packs/` beside a frozen exe on first run.

**Launch:** dev `python rimbrain.py run` (or `python -m runtime loop --pack start-mode-v0 --mode start --live-flag --fair --live-brain --live-mutate --feed` + `python -m dashboard.overlay --state-dir state --packs-dir components/rimbrain/packs` with PYTHONPATH=`components/runtime/src;components/contracts/src;components/dashboard/src`); frozen `dist\rimbrain.exe run`. Bridge `http://127.0.0.1:8765` must be up; pack edits mid-run = `dispatch.pack_drift` freeze. **Fair is default-on for every live mode** (`--fair` default True in `runtime loop`/`plan`): dev.* + save/load dispatches refused, dev-class packs refused at load, in-game dev/god mode hidden. `--dev` opts out for development testing only; `--mode cycle` (checkpoint harness) requires `--dev`. Open work: FR-1315 bad-build fixes (blueprint def-field tolerance `def`/`build_def`/`entity_def`/`defName`, pending-frame `when` gates on build steps, housing door wall-row `min.1-2`, `build-layout` cooldown); `plan.md`/`tasks.md` for feature 015 then `/speckit-analyze` (prereq script resolved feature 012 — 015 artifacts missing); restart bridge + clean live fair run to validate turbine siting/clearing/suppression live.

016 live pack mutation (ADR-018): `--live-mutate` (on in `rimbrain run` defaults) runs a reflection pass inside `run_start` — pack `mutate:` triggers (goal failed/expired, near-failure requeue/refusal/stall/escalate/defect-pattern bursts, every `goals_per_pass` terminal goals) → bounded failure digest → `rimbrain.improve` proposal (`runtime/mutation.schema.json`) → deterministic gate (`mutate.gate`: budget/stale/vacuous/schema/policy/inventory/fair-class) → `packs/candidates/cand-mut-*.yaml` + `state/mutations.jsonl` lineage. Candidates install only at the NEXT run's `mutate.boundary` (before `load_pack`); a regressed promotion auto-reverts to the recorded parent backup. Active pack file is never touched mid-run. `runtime/packmut.py` is the shared ops engine (`set`/`append`/`remove`/`upsert`, id-keyed list paths); `improve._apply_ops` compiles the legacy vocabulary through it. `rules-only` fallback applies the pack's declared defect-pattern remediations. Events `mutation.*` → feed + `planning.json` mutation block. Tests: `test_mutate.py` (31).

## Sources of truth

1. `specs/00-foundation/UNIFIED-REQUIREMENTS.md` defines normative system requirements.
2. `specs/30-contracts/` defines cross-component interfaces and ownership.
3. `specs/20-submodules/` defines component responsibilities.
4. Accepted ADRs in `specs/90-decisions/` resolve architecture choices.
5. `specs/40-work-packages/TRACEABILITY.md` maps requirements to verification.

If documents conflict, use that order and fix the lower-priority document.

## Spec-driven development

- Every requirement uses a stable ID.
- Every implementation work package lists requirements, interfaces, tests, migration, rollback, and measurable exit criteria.
- Cross-component behavior begins with a versioned contract and consumer/provider tests.
- Implementation may not introduce an undeclared dependency direction.
- A feature is not complete until its traceability row links passing evidence.
- Architectural changes require an ADR before code changes.
- Unknowns stay explicit; do not silently convert assumptions into requirements.

## Architectural invariants

- One runtime dispatcher owns every framework game write.
- Models emit typed choices or proposals and never execute unrestricted game calls.
- Planner/review tiers act on observed colony state only — entity references (pawns, targets) must resolve to ids/names present in the polled `game.status`; invented entities are a deterministic review-gate violation, never a dispatched action.
- Emergencies never wait for a model.
- Active RimBrain policy is immutable during scored episodes.
- Flat-file canonical records are authoritative; indexes are disposable.
- Runtime, policy, evidence, and export data have separate ownership roots.
- RimBridge remains generic. Agent-specific deterministic policy belongs in Steward or runtime.
- **All gameplay policy lives in RimBrain packs.** Strategy, tactics, priorities, phase orderings, thresholds, and decision rules are pack data — never source code. Runtime code provides only capability primitives (generic predicates, selectors, interpreters, action templates) able to execute any pack-defined strategy; a pack can redefine, reorder, extend, or disable any behavior without code changes. Hardcoded gameplay direction is an antipattern.
- Legacy upstream mode remains available during migration but is not permitted in scored framework runs.
- Submodules are pinned to exact commits for releases.

## Upstream baseline

- `upstream/rimagent` is read-only migration input.
- Upstream revision reviewed: `85cb050`.
- Nested RimBridge revision reviewed: `3c1e4c7`.
- Python baseline tests: `cd agent && uv run pytest -q`.
- RimBridge tests: `dotnet test mod/Tests`.
- Steward tests: `dotnet test mod-steward/Tests`.
- Toolchain installed 2026-09-22: .NET SDK 10.0.401, `uv` 0.12.17, Python 3.13.14. Baseline suites verified: RimBridge 26/26, Steward 78/78, Python 160/161 — the one failure is `test_allowlist_rejects_symlink_escape` (WinError 1314: creating symlinks needs admin or Developer Mode; environmental, not a code defect). Watchdog commit tests need git identity env vars (`GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_*`) since no global git identity is configured.
- Machine quirks: git identity configured globally 2026-09-22 (fresh shells see `git`; stale shells may not — tools fall back to `C:\Program Files\Git\cmd\git.exe`); Developer Mode off — use directory junctions, not symlinks; game at `V:\SteamLibrary\steamapps\common\RimWorld`; **both** bridges live and coexisting (zorrobyte HTTP :8765 115 methods + pardeike GABP :5174 125 tools); Laya decision server :8780 (`tools/serve-laya.ps1`); LM Studio :1234; OpenRouter is the remote planner (key in user env `OPENROUTER_API_KEY` + gitignored `upstream/rimagent/config.local.yaml`). `tools/env-check.ps1` + `tools/dev.ps1` verify all of this.

## Repository boundaries

- `components/contracts` must not depend on any other project component.
- `components/runtime` may depend on contracts and RimBridge/Steward protocols, not dashboard or lab.
- `components/rimbrain` is validated data and may depend only on contracts/schemas.
- `components/steward` may depend on RimBridge and contracts generated for its RPC/events.
- `components/lab` may consume contracts, RimBrain packs, and exported records; it must not control a live game in evaluation/replay paths.
- `components/dashboard` consumes read/control APIs and contracts; it must not import runtime internals.

## Devin skills (`.devin/skills/`)

Installed 2026-09-22. These are project tooling, not runtime code — commit them.

- **Spec Kit SDD** (GitHub `spec-kit`, specify-cli 1.0.9, official Devin integration): `/speckit-constitution`, `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`, `/speckit-checklist`, `/speckit-implement`, `/speckit-converge`, `/speckit-taskstoissues`. Shared infra lives in `.specify/` (templates, PowerShell helper scripts, `memory/constitution.md`). Spec Kit feature workspaces go under `specs/<NNN>-<slug>/`; the existing numbered volumes (`00-foundation` … `90-decisions`, `templates`) are the project-level spec set — feature specs must not overwrite or renumber them.
- **Honey** (Green-PT `honey-for-devs`, MIT): token/context-economy skills — `/honey` (core; accepts `lite|full|ultra|off`), `/honey-ccr`, `/honey-compress`, `/honey-debt`, `/honey-design`, `/honey-hive`, `/honey-loop`, `/honey-memory`, `/honey-px`, `/honey-review`, `/honey-superpowers`. Devin has no SessionStart hook, so apply `honey`'s style by default (answer first, terse prose, minimum code) unless the user asks for explanation; `/honey off` suspends it. Skipped from the upstream family: `honey-chat` (claude.ai only), `honey-eco`/`honey-gain` (need the source repo's `bench/` data).

## Git and release rules

- Never edit inside `upstream/rimagent` for fork implementation.
- Future component directories become Git submodules only after portable remotes exist.
- Do not use local filesystem URLs in `.gitmodules`.
- Record submodule commits, schema versions, pack hash, model revisions, and build identity in release and episode manifests.
- Preserve upstream MIT notices and Steward third-party notices.

