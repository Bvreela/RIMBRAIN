# Specification index

## Status vocabulary

- `DRAFT`: incomplete or contains unresolved design questions.
- `READY`: sufficient for implementation planning and test design.
- `ACCEPTED`: approved architecture decision.
- `IMPLEMENTED`: code exists and all declared verification gates pass.
- `SUPERSEDED`: retained for lineage but no longer authoritative.

All documents created in this preparation pass are `READY` for review, not implementation approval.

## Foundation

- [Unified requirements](00-foundation/UNIFIED-REQUIREMENTS.md)
- [Engineering principles](00-foundation/ENGINEERING-PRINCIPLES.md)
- [Upstream baseline audit](00-foundation/UPSTREAM-BASELINE-AUDIT.md)

## Architecture

- [System architecture](10-architecture/SYSTEM-ARCHITECTURE.md)
- [Repository topology](10-architecture/REPOSITORY-TOPOLOGY.md)
- [Dependency and authority rules](10-architecture/DEPENDENCY-AND-AUTHORITY.md)

## Submodule specifications

- [Contracts](20-submodules/CONTRACTS.md)
- [Runtime](20-submodules/RUNTIME.md)
- [RimBrain](20-submodules/RIMBRAIN.md)
- [Steward](20-submodules/STEWARD.md)
- [RimBridge integration](20-submodules/RIMBRIDGE.md)
- [Lab](20-submodules/LAB.md)
- [Dashboard](20-submodules/DASHBOARD.md)

## Cross-component contracts

- [Interface catalog](30-contracts/INTERFACE-CATALOG.md)
- [Data ownership and persistence](30-contracts/DATA-OWNERSHIP.md)
- [Event and export contracts](30-contracts/EVENT-AND-EXPORT.md)
- [Configuration and pack contracts](30-contracts/CONFIG-AND-PACK.md)

## Delivery

- [Upstream migration map](40-work-packages/UPSTREAM-MIGRATION.md)
- [Implementation plan](40-work-packages/IMPLEMENTATION-PLAN.md)
- [Requirements traceability](40-work-packages/TRACEABILITY.md)

## Verification

- [Test strategy](50-verification/TEST-STRATEGY.md)
- [End-to-end test environment](50-verification/E2E-TEST-ENVIRONMENT.md)
- [Release acceptance](50-verification/RELEASE-ACCEPTANCE.md)

## Feature specs

- [001 — Fork bootstrap and contract foundation](001-fork-bootstrap-contracts/spec.md) (spec → plan → tasks complete; analyze remediated)
- [002 — Model endpoint registry and role bindings](002-model-endpoints/spec.md) (implemented; UR-MOD-011..017; 5 live endpoints probed 2026-09-22)

## Implemented artifacts (feature 002)

- `components/runtime/` — `registry.py` (schema-checked endpoints/bindings CRUD over `profiles/*.yaml`), `secrets.py` (`env:`/`config:` refs), `probe.py` (capability+transient classification, strict-aware), `discover.py` (local port scan), `bindings.py` (role resolution + degraded chains + capability gates), `client.py` (openai-compat/systemone adapters), `provenance.py` (episode manifests); CLI `python -m runtime`
- `components/dashboard/` — stdlib settings UI `:8771` + JSON API; YAML authoritative, secrets never in responses
- `components/contracts/schemas/runtime/endpoints.schema.json` + `bindings.schema.json`
- [003 — Checkpoint-reload retry loops](003-checkpoint-retry/spec.md) (implemented; debug/eval mode per UR-RL-001..006; live smoke + speed/pause restore landed)
- [004 — Dispatcher (single writer) + core-survival pack v0](004-dispatcher-single-writer/spec.md) (implemented 2026-09-22; FR-301..309, SC-301..305)
- [005 — Planner/review loop (typed proposals, deterministic gate, candidate packs)](005-planner-review/spec.md) (implemented + live-verified 2026-09-23; FR-401..409, SC-401..405)
- [006 — Canonical event and state stores (durable JSONL, torn-tail recovery, projection)](006-event-state-stores/spec.md) (implemented 2026-09-23; FR-501..507, SC-501..505)
- [007 — Objective/task/lock model (lifecycle, verifier-only success, expiring locks, restart reconcile)](007-objective-task-model/spec.md) (implemented 2026-09-23; FR-601..608, SC-601..605)
- [008 — Fresh-start mode (deterministic bootstrap graph, per-colonist exit contract, established-colony skip)](008-fresh-start-mode/spec.md) (implemented 2026-09-23; FR-701..709, SC-701..705)
- [009 — Self-improvement loop (evidence diagnosis, audit gates, bounded promotion, thought feed, learning metrics)](009-self-improvement-loop/spec.md) (implemented 2026-09-23; FR-801..810, SC-801..805)
- [010 — Iterated improvement cycles (save→start→combat→improve, checkpoint restore, cycle.completed)](010-iterated-cycles/spec.md) (implemented + live-verified; combat cleared real hostiles)
- [011 — Universal pawn rules + Start Mode v2 (no idle pawns, downed/fleeing discipline, strip sweeps, arming, rice, overflow)](011-universal-pawn-rules/spec.md) (implemented + live-verified)
- [012 — Brain policy engine (all gameplay policy in packs; generic resolver/predicate/step-rule engine; ADR-015)](012-brain-policy-engine/spec.md) (implemented + live-verified; full start mode completed on a real colony)
- [013 — Agent transparency views (Planning & Goals + Quick-Action Matrix, per-poll decision records)](013-agent-transparency-views/spec.md) (implemented; live-verified renders)
- [014 — Capability catalog (audited mechanic coverage over the bridge surface; wiki-cited gap inventory)](014-capability-catalog/spec.md) (implemented; audit 115/115 mapped)

## Implemented artifacts (feature 009)

- `components/runtime/src/runtime/improve.py` — bounded cycle: `diagnose` (pack-declared defect patterns over canonical events) → `propose` (rules-only candidate pack — quarantine chronically-refused templates) → `audit_policy` gate → evidence-floor defer → weighted-score metrics validation → promote at episode boundary only
- `components/runtime/src/runtime/audit.py` — `audit_code` (pytest + corpus, fail-closed), `audit_policy` (schema + inventory + no model executors), `audit_ux` (feed coverage + readable refusals); all emit `audit.verdict`
- `components/runtime/src/runtime/feed.py` — `render_event` deterministic narratives per type (structured echo fallback) + `FeedWriter` → `state/feed.md` keyed by event_id; `--feed` CLI flag composes with any mode
- `components/runtime/src/runtime/metrics.py` — pure `episode_metrics` fold (refusal/verify-failure/completion rates, ticks, span) + `episode.metrics` envelope
- `components/rimbrain/packs/improve-v0.yaml` — defect patterns, metric weights, audit gates, cadence (reviewable data)
- `components/rimbrain/CUSTOMIZE.md` — user-facing brain-customization guide
- Contracts: `selfcheck.diagnosed`, `audit.verdict`, `improvement.promoted`, `improvement.rejected`, `episode.metrics` schemas + event-map + corpus (50/50)
- `loop.py` — `--mode improve` (read-only over evidence; no `--live` needed) + `--feed`

## Implemented artifacts (features 010/011/012)

- `components/runtime/src/runtime/policy.py` — capability-primitive policy engine: resolvers, predicates, selectors, step/rule runners, `validate_policy` (ADR-015)
- `components/runtime/src/runtime/startmode.py` — generic phase interpreter over `pack.start.phases[]` (no gameplay policy in code)
- `components/runtime/src/runtime/combatmode.py` — declarative `pack.combat` script executor (checkpoint, spawn, engage rules, cleanup)
- `components/runtime/src/runtime/universal.py` — thin `apply_rules` wrapper over `pack.universal.rules[]`
- `components/runtime/src/runtime/cycle.py` — save→start→combat→improve iterated cycles (`cycle.completed` contract)
- `components/rimbrain/packs/start-mode-v0.yaml` — full declarative policy: 13 start phases, exit conditions, universal rules, combat script; `policy_version: 1`
- `components/contracts` — `combat.completed`, `cycle.completed` schemas; `pack.schema.json` policy sections; corpus 54/54
- `specs/90-decisions/ADR-015-brain-policy-boundary.md` — strategy-in-packs / primitives-in-code boundary

## Implemented artifacts (features 013/014)

- `components/runtime/src/runtime/views.py` — Planning & Goals (`state/planning.{json,md}`) + Quick-Action Matrix (`state/actions.md`) renders; `decisions.jsonl` canonical per-poll dispatch records (fail-open, UR-VIEW-001..004)
- `components/rimbrain/capability-catalog.yaml` — versioned audited inventory: 170 entries over 33 domains; every baseline bridge method mapped or declared `gap`; wiki-cited (UR-BRN-015..017)
- `tools/capability_audit.py` — baseline/live bridge-surface diff vs catalog + per-domain coverage
- `components/contracts/schemas/rimbrain/capability-catalog.schema.json` — schema forbids policy fields by construction; corpus 57/57

## Implemented artifacts (feature 008)

- `components/runtime/src/runtime/startmode.py` — `StartMode` phase driver over `TaskLedger` (superseded by feature 012 pack-driven interpreter)
- `components/rimbrain/packs/start-mode-v0.yaml` — bootstrap templates (`set-anchor`, `create-stockpile`, `create-growing`, `unforbid-all`, `haul-all`, `build-shelter`, `build-one`, `roof-rect`) + `start` config (site weights, exit defs); all methods inventory-cross-checked
- `components/contracts/schemas/events/types/start.completed.schema.json` + event-map entry + corpus cases
- `components/runtime/tests/test_startmode.py` — `StartSim` scripted stub; ordered trace to `start.completed`, restart resume, established-colony zero writes, partial coverage, site-ranking determinism
- `loop.py`/`__main__.py` — `--mode start` wiring (live-gated; observe → reconcile → reflex → phase step)

## Implemented artifacts (feature 006)

- `components/runtime/src/runtime/store.py` — `EventStore` (append-only canonical JSONL, torn-tail truncation + `recovery.jsonl` markers, gap/dup reporting) and `write_atomic` (tmp + `os.replace`)
- `components/runtime/src/runtime/project.py` — deterministic `project()` fold + `rebuild()` to `state/projection.json` (disposable index; log authoritative)
- `loop.py`/`planloop.py` — events persist to `state/events.jsonl` by default (`--no-store` opt-out)
- `tests/contract/corpus_runner.py` — `ev__<type>.valid.NN.json` escape resolves dotted event-payload schemas; corpus cases now cover `action.*`/`plan.*` payloads
- `components/runtime/tests/test_{store,project}.py` — round-trip, torn-tail, corruption-count, atomicity, determinism, disk persistence

## Implemented artifacts (feature 005)

- `components/contracts/schemas/runtime/plan.schema.json` — PlanProposal contract (actions + policy_mutations, 3 legal ops)
- `components/contracts/schemas/events/types/plan.*` — proposed/reviewed/accepted/rejected payloads, registered native in `registry/event-map.yaml`
- `components/runtime/src/runtime/{planning,review,planloop}.py` — prompt builder + JSON extraction + schema validation, deterministic review gate (code decides; model critique advisory), candidate-pack materialization under `packs/candidates/`, CLI `python -m runtime plan`
- `components/rimbrain/packs/core-survival-v0.yaml` — `fallback_plan` block (rules-only degraded path)
- `components/runtime/tests/test_{planning,review,planloop}.py` — SC-401 model-can't-override-gate, SC-402 malformed, SC-403 5× bit-identical, SC-404 loadable candidates, SC-405 degraded completion

## Implemented artifacts (feature 004)

- `components/contracts/schemas/runtime/pack.schema.json` — PolicyPack contract (templates/jobs/decision_map/emergency)
- `components/contracts/schemas/events/types/action.*` — five action event payloads, registered native in `registry/event-map.yaml`
- `components/rimbrain/packs/core-survival-v0.yaml` — v0 pack: 6 templates on the real bridge surface (`ui.set_work`, `ui.job`, `ui.designate`), decision_map, emergency reflexes
- `components/runtime/src/runtime/{bridgeclient,templates,dispatch,simgame,loop}.py` — single writer (fail-closed: unknown/invalid/unmapped/locked/pack-drift), inventory-cross-checked pack loading + canonical-hash drift guard, deterministic SimGame, poll loop CLI `python -m runtime loop`
- `components/runtime/tests/test_{dispatch,loop}.py` — fail-closed matrix, event-stream==write-stream, 5× bit-identical runs, reflex-zero-model-calls

## Implemented artifacts (feature 003)

- `components/contracts/schemas/runtime/retry-config.schema.json` - RetryConfig contract (window XOR, retry cap, checkpoint family, budgets, embedded gate/mutation space/candidate)
- `components/contracts/schemas/events/types/retry.*` - six canonical payload schemas; registered as `native` event types in `registry/event-map.yaml`
- `components/lab/src/lab/{bridge,gate,mutations,retryloop,retryfixture}.py` - GameCtl (`LiveBridge` + deterministic `SimBridge`), state-predicate gate, ordered mutation space, retry engine + CLI, US5 fixture exporter
- `configs/retryloop.example.yaml`, `components/lab/tests/test_retryloop.py`

## Implemented artifacts (feature 001)

- `components/contracts/` — schema package: canonical JSON hashing, common+event schemas, `registry/event-map.yaml` (18 upstream kinds), corpus + round-trip + drift tests (51 green)
- `components/lab/` — fixture replay harness (deterministic, fail-closed, quarantine salvage)
- `baselines/upstream-85cb050/` — sealed baseline bundle: `rpc-inventory.json` (115 methods), `event-corpus/bus-kinds.jsonl`, `automation-surface.yaml`, `MANIFEST.yaml` + `gaps.yaml`
- `tests/contract/corpus_runner.py`, `tests/acceptance/` — corpus validator, fork-checkout + integrity + capture acceptance tests, `run_quickstart.ps1`
- `tools/baseline_validate.py`, `tools/baseline_capture.py`, `tools/validate_components.py`

## Tooling docs

- [Laya decision server — Windows setup](../tools/LAYA-SETUP.md) (`rimbrain.select` local tier)
- [Bridge connectivity check](../tools/bridgecheck/README.md)

## Decisions and templates

- [Initial architecture decisions](90-decisions/INITIAL-ADRS.md)
- [ADR-013 — Bridge layer](90-decisions/ADR-013-bridge-layer.md) (zorrobyte HTTP primary, GABP diagnostics sidecar)
- [ADR-014 — Model serving stack](90-decisions/ADR-014-model-serving-stack.md) (Laya/OpenRouter/LM Studio bindings)
- [ADR-015 — Brain policy boundary](90-decisions/ADR-015-brain-policy-boundary.md) (gameplay policy in packs; engine exposes capability primitives only)
- [Feature specification template](templates/FEATURE-SPEC-TEMPLATE.md)
- [Contract template](templates/CONTRACT-TEMPLATE.md)
- [ADR template](templates/ADR-TEMPLATE.md)
