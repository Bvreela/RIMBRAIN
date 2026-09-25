# Implementation Plan: Fast-Evolve Play Mode

**Branch**: `021-fast-evolve` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-fast-evolve/spec.md`

## Summary

A new `fastevolve` run mode on the unified loop (`runtime/loop.py`). Per
in-game day the mode anchors to the autosave nearest day start (detected via
`game.list_saves` + a pack-configured name pattern). Each poll, day-failure
triggers evaluate from two pack-declared sources: colony-level predicates
(`policy.check` over obs) and the existing goal-level failure/near-failure
set (`evolve.check_triggers` on a day-scoped `PassState`). On a trigger with
reload budget remaining the mode pauses the game, runs the reflect pass
(`evolve.maybe_trigger` with a `day_failure` reason), promotes any gated
candidate **mid-run** (shared install half of `evolve.boundary`), reloads the
anchor via the single-writer dispatch path, reinitializes run state with the
brain-reset sequence, and resumes. Default budget: 2 reloads/day (3 attempts).
Exhausted days still evolve but do not reload; the last evolved pack carries
forward. Save/load is unlocked by a new scoped dispatcher grant
(`allow_save_load`) — `--dev` stays off, so `dev.*` methods remain refused.

## Technical Context

**Language/Version**: Python 3.13 (toolchain pinned 2026-09-22)

**Primary Dependencies**: PyYAML, jsonschema (existing); no new deps

**Storage**: flat files — `state/fastevolve.json` (day session, durable across
reload/restart), `state/mutations.jsonl` (existing lineage log),
`state/events.jsonl` (canonical events)

**Testing**: `uv run pytest -q` → `components/runtime/tests/test_fastevolve.py`;
SimGame + fixed clock + injected reflect for deterministic streams

**Target Platform**: Windows, RimWorld 1.6 via RimBridge HTTP
`http://127.0.0.1:8765`; frozen single-exe via `rimbrain.py`

**Project Type**: cli / agent runtime

**Performance Goals**: reflection pass is wall-clock bounded by the model
endpoint; game paused during evolve+reload; `game.list_saves` polled at a
pack-bounded cadence (default every 10 polls)

**Constraints**: fair mode stays on — `dev.*` refused, dev-class packs refused
at load; save/load permitted only in this mode; scored episodes never enable
it; pack drift detection must survive mid-run promotion

**Scale/Scope**: one new runtime module (~350 lines) + edits to
`loop.py`/`dispatch.py`/`simgame.py`/`feed.py`/`views.py` + pack config +
tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Note |
|-----------|---------|------|
| I Deterministic before probabilistic | PASS | triggers and budgets are code; the model only proposes mutations |
| II One writer (NON-NEGOTIABLE) | PASS | save/load go through `Dispatcher.dispatch` (`save-game`/`load-game` templates); no raw bridge writes |
| III Spec-first (NON-NEGOTIABLE) | **GATED** | mid-run pack promotion + save/load under a fair-class run deviate from ADR-018/UR-CTL-009 → **ADR-020 must land before code** |
| IV Explicit compatibility | PASS | `fastevolve.json` + new events declare `schema_version`; unknown fields ignored by readers |
| V Policy revisable, immutable during scored runs | PASS w/ ADR | fast-evolve refuses scored/fair-scored contexts; promotion mechanics + lineage shared with `evolve.boundary` |
| VI Staged promotion | PASS | candidates still pass the one deterministic gate; promotion is unpack-rollback-able via parent backup |
| VII Build for diagnosis | PASS | `fastevolve.*` events + feed narration + `planning.json` block |
| IX Policy is data (NON-NEGOTIABLE) | PASS | entire retry policy lives in the pack `fastevolve:` section |
| X Lifecycle residue-free (NON-NEGOTIABLE) | PASS | reload reinit reuses the brain-reset full wipe (`rs.reset`, `ledger.reset_ns`, fresh engine + PassState) |

**Gate resolution**: ADR-020 (mid-run candidate promotion + scoped save/load
grant for unscored play modes) is a prerequisite task, not a waiver.

## Project Structure

### Documentation (this feature)

```text
specs/021-fast-evolve/
├── plan.md              # this file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── fastevolve.md    # CLI surface + pack schema + event payloads
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
components/runtime/src/runtime/
├── fastevolve.py         # NEW — DayState, autosave tracker, trigger eval,
│                        #       evolve+reload orchestration, promote_now
├── loop.py              # EDIT — --mode fastevolve, allow_save_load wiring,
│                        #       per-poll fastevolve.tick + reload reinit
├── dispatch.py          # EDIT — allow_save_load ctor flag scoped grant
├── evolve.py            # EDIT — factor boundary()'s install half into a
│                        #       shared promote path; day_failure reason
├── simgame.py           # EDIT — game.save/load/list_saves snapshot slots
├── feed.py              # EDIT — fastevolve.* narration
├── views.py             # EDIT — fastevolve block in phase_snapshot
components/rimbrain/packs/start-mode-v0/pack.yaml   # EDIT — fastevolve: section
components/runtime/tests/test_fastevolve.py          # NEW
specs/90-decisions/ADR-020-fast-evolve-midrun.md    # NEW — gate for Principle III
```

**Structure Decision**: single runtime package; the mode is a controller
module (`fastevolve.py`) hooked into the unified poll loop, mirroring how
`evolve.maybe_trigger` plugs in today. No new component, no cross-boundary
dependency changes.

## Complexity Tracking

> No unjustified violations — the one gate item is resolved by ADR-020 as a
> prerequisite, not waived.

## Phase 1 design summary

See `research.md` (all decisions resolved), `data-model.md` (DaySession,
anchor, attempt, pack schema), `contracts/fastevolve.md` (CLI + pack +
events), `quickstart.md` (sim + live validation runs).
