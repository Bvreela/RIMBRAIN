# Upstream baseline audit

**Status:** READY  
**Reviewed upstream:** `zorrobyte/rimagent` at `85cb050`  
**Reviewed nested RimBridge:** `zorrobyte/rimbridge` at `3c1e4c7`

## 1. Repository composition

Upstream is a mixed repository:

- `agent/`: Python 3.12 package `rimagent`, built with Hatch and managed with `uv`;
- `mod/`: nested Git submodule containing generic RimBridge C# code;
- `mod-steward/`: embedded C# RimBridge add-on containing agent-specific deterministic policy;
- `brain/`: mutable Markdown skills, Python tools/watchers, and memory;
- `knowledge/`: wiki/source material;
- `script/`: build, launch, reload, and game restart scripts.

The upstream root is MIT licensed. Steward includes vendored Free Will and Colony Manager Redux-derived logic whose notices must remain intact.

## 2. Existing strengths to retain

- Loopback HTTP bridge and player-parity RPC coverage.
- Main-thread queue isolation inside RimBridge.
- Dynamic RPC registration and add-on hooks.
- Event ledger, state summary, map/base views, dialogs, and screenshots.
- Steward work-priority scorer, stock jobs, research queue, and standing orders.
- Event-driven wakes, autosave, episode lifecycle, dashboard bus, and operator controls.
- Tool/result capture, LLM call capture, score history, and an SFT exporter.
- Test isolation through `RIMAGENT_ROOT` and pure-logic C# tests.
- Existing Windows portability fixes around content-based reload.

## 3. Current architecture and coupling

### Python runtime

`runner.Runner` constructs concrete `Bridge`, `LLM`, `Registry`, and `Context` objects directly. Its main loop is synchronous and thread-based. The same shared context exposes bridge, LLM, and registry to tool execution.

`loop.think` gives a general model a broad generated tool registry. Bridge RPCs become `rw_*` tools with `additionalProperties: true`. A model can call write RPCs, generic `rpc`, and an unsandboxed persistent `run_python` in legacy play.

`roles.py` can fan a calm wake into four concurrent model threads. Role regexes reduce tool overlap but multiple streams still write the same live game and share mutable runtime facilities.

`reflect.py` performs mid-episode and end-episode LLM passes that edit hot-loaded Python/Markdown brain files and commit them. Active policy is therefore nonstationary.

`bus.py` is a useful in-process stream but its envelope contains only process-local sequence/time/kind/data. It is not episode-causal, schema-versioned, durable-by-contract, or sufficient for the unified export.

Persistence uses direct `write_text` and append writes without atomic replacement/fsync. Startup restores only limited episode counters and does not reconcile pending writes, locks, tasks, or workflow cursors.

### RimBridge

RimBridge is already correctly separated as a generic submodule. It exposes approximately 96 RPCs across game/state/map/UI/engine/definition/developer/anchor groups. `Rpc.RegisterAssembly` and `Hooks` let add-ons extend behavior without coupling core bridge code to policy.

The generic reflective engine surface is useful for legacy/operator development but cannot be exposed to framework model roles. The runtime must enforce that distinction; RimBridge need not remove the capability.

### Steward

Steward is a natural independent component but currently lives inside upstream RimAgent. It references the pinned RimBridge DLL and registers 18 `steward.*` RPCs. It already owns high-frequency deterministic work and many reflexes.

Missing unified-spec capabilities include explicit desired-state/idempotency metadata, action ownership contracts, richer safety/vitals events, dispatcher intent correlation, and framework-facing capability/version reporting.

## 4. Upstream file disposition

| Upstream area | Fork disposition |
|---|---|
| `agent/rimagent/runner.py` | Keep legacy behavior behind `legacy`; reduce to composition root and controller selection; framework loop moves to new packages |
| `loop.py` | Preserve for legacy; extract observation gathering; framework packets use typed feature renderers |
| `llm.py` | Preserve legacy adapter; replace direct singleton use in framework with provider protocols/adapters |
| `registry.py` | Preserve legacy dynamic tools; framework uses explicit read capability catalog and action-template registry |
| `context.py` | Legacy-only; framework receives role-specific dependency objects with no shared write handle |
| `bus.py` | Adapt as dashboard projection; canonical event store becomes separate durable service |
| `roles.py` | Disable write-capable parallel mode in framework; optional advisers must be read-only |
| `reflect.py` | Disable live brain mutation in framework/scored mode; emit proposals only |
| `watchers.py` and `brain/watchers` | Legacy-compatible; framework watchers are typed read-only alerts or audited deterministic orders |
| `memory.py`, `braingit.py` | Keep legacy; structured state/pack stores replace them as framework authority |
| `export_sft.py` | Retain legacy command; new lab exporter consumes canonical event contracts and excludes hidden reasoning by default |
| `dashboard/app.py` | Split UI from runtime internals; consume read-model and audited command contracts |
| `mod/` | Keep pinned generic upstream dependency; contribute only generic missing observations/actions upstream |
| `mod-steward/` | Extract to independent Steward fork/submodule and extend through versioned contracts |
| `brain/` | Migrate reusable data to RimBrain pack; executable tools/watchers remain legacy or reviewed runtime extensions |

## 5. Gaps against unified requirements

- No structural single-writer boundary (`UR-CTL-001/002`).
- Emergency behavior may wake a model and current runner unpauses after every think step (`UR-CTL-005/007`).
- No durable objective/plan/goal/task graph, locks, pending action journal, or verifier authority (`UR-RUN-*`).
- No pawn TTC, site runway, crisis ladder, hysteresis framework, spiral detector, or post-mortem contract (`UR-SUR-*`).
- One concrete LLM config and free-form tool loop rather than role adapters and row qualification (`UR-MOD-*`).
- Mutable executable `brain/` rather than immutable scored packs and reviewed proposals (`UR-BRN-*`).
- Existing logs/capture are useful inputs but do not meet durability, causal lineage, redaction, or training trajectory requirements (`UR-DAT-*`, `UR-EXP-*`).
- Embedded Steward and dashboard prevent independent releases (`UR-ARC-*`).

## 6. Verification baseline

Documented commands:

- Python: `cd agent && uv run pytest -q`
- RimBridge: `dotnet test mod/Tests`
- Steward: `dotnet test mod-steward/Tests`
- Build: RimBridge first, then Steward.

The preparation environment had neither `uv` on `PATH` nor an installed .NET SDK, so these suites were not run. This is an environment gap, not a recorded test failure. Phase 0 must reproduce the baseline before fork implementation.

## 7. Migration conclusion

Do not replace upstream in one rewrite. Add framework mode beside legacy mode, introduce contracts and canonical evidence first, run shadow, then grant the dispatcher bounded authority domain by domain. Extract Steward and dashboard only after contract seams exist. Keep RimBridge pinned and generic.
