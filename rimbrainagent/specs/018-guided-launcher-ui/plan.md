# Implementation Plan: Guided Launcher UI

**Branch**: `feature/018-guided-launcher-ui` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/018-guided-launcher-ui/spec.md`

## Summary

Extend the existing Tkinter overlay into a three-screen supervisor window — Setup (declarative parameter grid + pack list + live brain checks), Monitor (existing views + loop process status), and a guided Pack Editor (outline tree + typed forms + predicate builders). `rimbrain.py` spawns the overlay as supervisor; GO spawns the loop child via a `RIMBRAIN_LOOP_CMD` argv prefix. Two additions to the `runtime.api` facade: `probe_live(role)` (role-shaped verification call against the bound model) and `validate_pack_doc(doc)` (loader-identical validation for editor saves). Guided saves always materialize a new sibling pack with `derived_from` lineage.

## Technical Context

**Language/Version**: Python 3.13 (baseline 3.12+); Tkinter (stdlib) — the existing overlay stack, no new UI framework.

**Primary Dependencies**: PyYAML (already used across runtime); `runtime.api` facade extended in-place. No new dependencies.

**Storage**: Flat files — `profiles/*.yaml` (bindings/endpoints, read via facade), `packs/<id>/pack.yaml` (policy data, editor writes new siblings only), `state/` (existing request/status channels reused unchanged).

**Testing**: `pytest` — `components/dashboard/tests/` (new: param-spec/argv assembly, brain verdict classification, editor doc transforms) and `components/runtime/tests/` (new: `probe_live` cases with stubbed transports). Tk widgets kept thin; all logic in testable pure functions.

**Target Platform**: Windows desktop (primary), same code path frozen (`dist/rimbrain.exe`) and dev (`python rimbrain.py`).

**Project Type**: Single-process desktop UI supervising a child loop process.

**Performance Goals**: Probes bounded (connect ≤5s, HTTP ≤10s — existing probe timeouts); screen never blocks >timeout; monitor refresh stays at 1s cadence.

**Constraints**: Dashboard component MUST NOT import runtime internals — all probing/validation goes through `runtime.api`. Sim mode must never reach a real bridge (unchanged). Fair-mode refusal, pack-drift, and single-writer guarantees unchanged. Frozen exe resolves writable/bundled roots identically.

**Scale/Scope**: ~4 new dashboard modules + overlay rework, 2 facade additions, launcher arg-routing; ~1 flags surface, 5 brain roles, 6 packs on disk.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Deterministic before probabilistic | PASS | UI mirrors the loop's deterministic fail-closed flag validation; no model involvement in constraint checks. |
| II. One writer, bounded model authority | PASS | The UI never holds a bridge handle; it spawns the same loop entry point and uses the existing request-file channels. |
| III. Spec-first | PASS | This spec + contracts; FR IDs stable. |
| IV. Explicit compatibility | PASS | Pack files stay schema v0; `derived_from` is additive metadata; no consumer changes. |
| V. Evidence immutable; policy revisable | PASS | Editor writes only `packs/` policy data as new siblings; `state/` channels unchanged; `packs/candidates/` stays mutate-pipeline-owned. |
| VI. Staged promotion | PASS | No selector authority change. |
| VII. Build for diagnosis | PASS | Assembled argv shown on the setup screen; probe verdicts and loop exit codes surfaced, not swallowed. |
| VIII. Migration escape hatch | N/A | |
| IX. Policy is data; code is capability | PASS — aligned | The editor's entire purpose: pack data editable through forms; validation reuses the loader's own checks so forms can never emit a pack the engine would reject. |
| X. Brain lifecycle explicit & residue-free | PASS | Pack swap and overwrite+reset ride the existing `brain_reset.request` channel — full state wipe, no partial reloads. |
| Boundaries | PASS | Dashboard imports `runtime.api` only (precedent: `dashboard/server.py`); new facade entries live in runtime where internals are legal. |
| Single-executable | PASS | `RIMBRAIN_LOOP_CMD` env var carries the frozen `rimbrain.exe loop` prefix; writable roots resolve beside the exe as today. |

No violations → no Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/018-guided-launcher-ui/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
│   ├── launch-cli.md
│   ├── probe-live.md
│   └── pack-edit-save.md
└── tasks.md             # /speckit-tasks output (not this command)
```

### Source Code (repository root)

```text
rimbrain.py                        # arg routing: bare/-y/flags; RIMBRAIN_LOOP_CMD env
components/dashboard/src/dashboard/
├── overlay.py                     # screen stack (Setup/Monitor), loop child owner, existing views
├── paramspec.py                   # declarative flag table → widgets, argv assembly, constraint mirror
├── brains.py                      # role list → resolve → live probe → verdict (worker-threaded)
├── packedit.py                    # pack doc → outline/form model, edits → doc, save-as-new
└── server.py                      # unchanged (endpoint settings UI)
components/runtime/src/runtime/
├── api.py                         # +probe_live(role), +validate_pack_doc(doc)
└── probe.py                       # +role-shaped live calls (chat ping / decide probe)
components/dashboard/tests/
├── test_dashboard.py              # existing
├── test_paramspec.py              # argv assembly + constraint mirror vs loop rules
├── test_brains.py                 # verdict classification (stubbed facade)
└── test_packedit.py               # doc→forms, save-as-new write, validation wiring
components/runtime/tests/
└── test_probe_live.py             # verdict matrix with stubbed transports
```

**Structure Decision**: Dashboard gains pure-logic modules (`paramspec`, `brains`, `packedit`) with thin Tk glue in `overlay.py` so every rule is pytest-covered without a display. Runtime gains the two facade entries so the dashboard boundary rule holds. `rimbrain.py` changes are limited to arg routing and one env var.

## Complexity Tracking

No constitution violations — table intentionally empty.
