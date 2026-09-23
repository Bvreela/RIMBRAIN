# RimBrainAgent project rules

## Current phase

Features 001-005 implemented 2026-09-22: 001 fork bootstrap + contracts + sealed baseline; 002 model-endpoint registry + role bindings; 003 checkpoint-retry debug loops (live smoke passed); 004 dispatcher single-writer + core-survival pack v0 (`python -m runtime loop --mode sim` - sim loop must never wire to the real bridge; dispatcher writer target = SimGame in sim mode); 005 planner/review loop (`python -m runtime plan --mode sim` - typed PlanProposals via rimbrain.plan, deterministic review gate is decisive (code decides, model advises), accepted mutations materialize `packs/candidates/` never the active pack, plan actions dispatch through the single writer only, `rules-only` fallback = pack `fallback_plan`). 006 event/state stores (`runtime/store.py` append-only canonical JSONL + torn-tail recovery + `recovery.jsonl`; `project.py` disposable projection; loop/plan persist by default under `state/`); 007 task ledger (`runtime/tasks.py` declared lifecycle `proposed->locked->dispatched->verifying->succeeded|failed|expired`, verifier-only success via `{field,op,value}` effect specs, all-or-nothing tick-expiring resource locks, `task.transition` log in `state/tasks.jsonl` + `cursor.json`, `run_loop(ledger=)` reconciles before attend); 008 fresh-start mode (`runtime/startmode.py` deterministic bootstrap graph over the TaskLedger — `site->zone->unforbid->shelter->roof->haul->beds/food/recreation`, per-phase effect specs verified against observed state, site ranking over `map.open_rects` persisted via `anchor.set` + `startmode.json`, established-colony skip = zero writes, `start.completed` only on the verified exit contract; `python -m runtime loop --mode start --live`; pack `components/rimbrain/packs/start-mode-v0.yaml`); 009 self-improvement loop (`runtime/improve.py` bounded diagnose→propose→audit→validate→promote-at-boundary cycles over canonical evidence; `audit.py` code/policy/ux verdicts; `feed.py` thought feed `--feed` → `state/feed.md`; `metrics.py` episode learning metrics; `improve-v0.yaml` pack; `components/rimbrain/CUSTOMIZE.md`). 010 iterated cycles (save→start→combat→improve per iteration, checkpoint restore, `cycle.completed`); 011 universal pawn rules + start-mode v2 (no idle pawns, downed/fleeing discipline, strip sweeps, arming, fertile rice, overflow stockpile); 012 brain policy engine — `policy.py` capability primitives, all gameplay policy in packs (ADR-015); 013 transparency views (`views.py` — `state/planning.{json,md}` goals view + `state/actions.md`/`decisions.jsonl` quick-action matrix, fail-open per-poll renders); 014 capability catalog (`components/rimbrain/capability-catalog.yaml` audited wiki-cited inventory + `tools/capability_audit.py` baseline/live diff). Upstream stays read-only. Next: observation/shadow controller (WP-103/104) or Steward protocol extraction (Phase 4).

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

