# End-to-End Test Environment Requirements

**Status:** READY  
**Scope:** everything required to take the RimBrainAgent fork from spec-only to a running,
observable, testable system against a live RimWorld instance — plus the development loops
(think/replay/shadow/matched-trial) and graphs/observability needed to iterate.

Requirement IDs `TE-###`. Environment prerequisites marked **[MISSING]** are not yet satisfied on
the current dev machine.

## 1. Platform prerequisites

| ID | Requirement | Detail |
|---|---|---|
| TE-001 | Windows dev machine with RimWorld 1.6 via Steam | Steam must be running; Workshop mods only load through a Steam launch |
| TE-002 | Harmony mod present | Steam Workshop `2009463077`, subscribed and enabled; hard dependency of RimBridge |
| TE-003 | .NET SDK | 10.0.401 installed 2026-09-22; RimBridge 26/26 + Steward 78/78 tests pass |
| TE-004 | Python 3.12+ + `uv` | Python 3.13.14 + uv 0.12.17 installed 2026-09-22; suite 160/161 — one env-limited failure (symlink privilege, WinError 1314; enable Developer Mode or run elevated). Git identity must be set via env vars for watchdog commit tests |
| TE-005 | Git | present (`C:\Program Files\Git`) |
| TE-006 | RimWorld Mods dir + Player.log located | Windows Player.log: `%LOCALAPPDATA%Low\Ludeon Studios\RimWorld by Ludeon Studios\Player.log` (upstream docs assume macOS path — Windows adaptation required) |

## 2. Game-side deployment (mod chain)

| ID | Requirement | Detail |
|---|---|---|
| TE-010 | Build `mod/` (RimBridge) from pinned source `3c1e4c7` | upstream `script/build.sh` assumes macOS `DOTNET_ROOT=/opt/homebrew/...` — **Windows build script needed** |
| TE-011 | Build order: RimBridge before Steward | `mod-steward` references `mod/1.6/Assemblies/RimBridge.dll` |
| TE-012 | Deploy both mods into RimWorld Mods dir | names `RimBridge`, `RimBridgeSteward`; Windows: directory junction works without admin where symlinks don't; copy acceptable for test env |
| TE-013 | Load order + compat | Harmony → RimBridge → RimBridgeSteward; `zorrobyte.autopilot` and `mcocdaa.RimMindCore` must not be loaded |
| TE-014 | Launch via Steam | `steam://rungameid/294100`; upstream `script/restart-game.ps1` already handles Windows kill/relaunch; DLLs load at startup only — every mod rebuild needs a game restart |
| TE-015 | Bridge health gate | `GET 127.0.0.1:8765/health` ok **and** `GET /methods` inventory matches the baseline bundle's 115-method manifest before any test run counts |

## 3. Agent runtime configuration

| ID | Requirement | Detail |
|---|---|---|
| TE-020 | `config.local.yaml` (gitignored) | OpenAI-compatible endpoint for live model runs; **not required** for offline tiers, replay, or rules-only operation |
| TE-021 | Two run modes available | legacy upstream mode (`rimagent play` semantics — the migration escape hatch, constitution VIII) and framework mode; never sharing write authority |
| TE-022 | Deterministic scenario pinning | upstream defaults: `scenario: Crashlanded`, `storyteller: Cassandra`, `difficulty: Rough`, `seeds: [rimagent-1..5]` — a test series MUST pin all four |
| TE-023 | Speed/wake config recorded per run | `play.speed`, `think_speed`, `danger_think_speed`, `wake_hours`, `alert_wake_priorities`, `critical_kinds` — all land in the run manifest |
| TE-024 | Save hygiene | per-series save naming/family; autosave cadence on; test saves isolated from user saves |

## 3a. Local model services

| ID | Requirement | Detail |
|---|---|---|
| TE-073 | Laya decision server installed | `tools/setup-laya.ps1` (idempotent): ggmlc v0.9.2 `laya.exe` + `ggmlc-run.exe` (cuda-sm89), `laya_english_q8_0.gguf` (~431MB), CUDA-12 runtime DLLs via pip wheels under `J:\RimAgent\models\laya\.venv` — **installed + verified 2026-09-22**; full guide: `tools/LAYA-SETUP.md` |
| TE-074 | Laya serving | `tools/serve-laya.ps1` → `GET 127.0.0.1:8780/health` returns `{"status":"ok"}`. Note: first `POST /v1/systemone` after boot takes ~9 s (CUDA graph compile); warm latency ~55 ms/4-question batch on RTX 5060 Ti |
| TE-075 | Laya decision contract probe | `POST /v1/systemone` `{state, questions}` returns typed `answers` (choice/score/noul) with probabilities + `usage.latency_ms`; `GET /v1/presets` lists named workflows (incl. `harness` — act/tool/ask_user/stop agent gate) |
| TE-076 | Endpoint registry + bindings valid | `profiles/endpoints.yaml` + `profiles/bindings.yaml` parse; `api` discriminator (`openai-compat`/`systemone`) resolves per entry; secrets only via `api_key_ref` (env var / `config.local.yaml`), never inline (spec 002, UR-MOD-011..017) |
| TE-077 | Remote endpoint health | Gemini `gemini-3.5-flash-lite` probe verified 2026-09-22 (chat + tool_calls via `/v1beta/openai` shim); `gemma-4-31b-it` demand-limited (503) on free tier — probes must classify 503 as `retryable` |

## 4. Test tiers

| ID | Tier | Game? | Content |
|---|---|---|---|
| TE-030 | A — offline | no | `uv run pytest -q`, `dotnet test` (both mod test projects), contract corpus, fixture replay — the only CI-runnable tier |
| TE-031 | B — loopback integration | yes | game + bridge + runtime; scripted scenarios driven via `dev.*`/setup RPCs (spawn hostiles, injure pawn, food scarcity, cold snap); assertions against canonical events |
| TE-032 | C — scored episodes | yes | seeded N-day runs, frozen policy pack, full canonical evidence capture; the only tier that produces qualification/calibration evidence |
| TE-033 | D — soak/recovery | yes | multi-episode runs; crash mid-episode → `recovery.started/completed`; watchdog passes; store torn-tail recovery |
| TE-034 | shadow mode | yes | framework observes and proposes while legacy mode drives; zero shared write authority — prerequisite for any live authority grant |

## 5. Observability — the "graphs"

| ID | Requirement | Detail |
|---|---|---|
| TE-040 | Dashboard parity during migration | upstream SSE dashboard `127.0.0.1:8770` (bus events) keeps working; framework adds its read model alongside, not instead |
| TE-041 | Canonical event store → queryable read model | every decision/action/verification queryable by episode, correlation, event_type |
| TE-042 | Metric graphs | survival days per seed/series, pawn deaths, dispatch success rate, verifier pass rate, wake/decision latency, token usage + cost per episode |
| TE-043 | Causal lineage graphs | per decision: attention reason → candidates/exclusions → route → intent → dispatch → verification → outcome, renderable as a chain |
| TE-044 | Calibration views | selector accuracy per (matrix row × model revision × context family); drift alarms |
| TE-045 | Matched-trial overlays | legacy vs framework on same seed family, overlaid survival/efficiency curves |

## 6. Development loops

| ID | Loop | Detail |
|---|---|---|
| TE-050 | Single-step | one reconcile → decide → dispatch → verify cycle on demand (framework equivalent of `rimagent think`) |
| TE-051 | Replay | offline fixture replay; deterministic; the default inner dev loop — no game needed |
| TE-052 | Bounded live | episode with dashboard pause/step/inspect; operator channel recorded |
| TE-053 | Self-improvement | upstream improvement pass (brain/, hot-reload) + watchdog (source patch, verify-then-commit, never deploys) — preserved, constrained to declared scope |
| TE-054 | Evaluation | matched trials harness: same seed family × {legacy, framework} × policy cohort |

## 7. Safety and isolation

| ID | Requirement |
|---|---|
| TE-060 | Loopback only — bridge binds 127.0.0.1; no remote game surface |
| TE-061 | Safe-pause + quit path verified at every tier-B+ session start (dead-man switch) |
| TE-062 | Secrets never enter fixtures, events, exports, or manifests; `config.local.yaml` stays gitignored |
| TE-063 | Emergency reflexes (Steward orders, safe-pause) must not depend on model availability in any tier |

## 8. Environment matrix

| Env | Tiers | Game | Models | Purpose |
|---|---|---|---|---|
| dev-local (this machine) | A, B, C | yes, one instance | endpoint optional | primary development |
| CI | A only | no | none | PR/release gates |
| eval rig | C, D, matched trials | yes, dedicated | provider matrix | scored series |

## 9. Known gaps to close (ordered critical path)

1. **Install `uv` + .NET SDK** (TE-003/004) — blocks upstream parity tests and all mod builds.
2. **Windows build script** for `mod/` + `mod-steward/` (TE-010) — upstream `build.sh` is macOS-shaped.
3. **Deploy + first bridge health check** (TE-012..015) — validates the 115-method inventory, closing
   `baselines/upstream-85cb050/gaps.yaml` live-capture items.
4. **`config.local.yaml`** with a model endpoint — needed only for Tier C+ and legacy-mode runs.
5. **Scenario library** — scripted `dev.*` setup sequences for Tier B (raid, injury, starvation,
   cold snap, fire) as reusable fixtures.
6. **Canonical store + read model** — lands with the runtime component (WP-1xx), prerequisite for
   all TE-04x graphs.
