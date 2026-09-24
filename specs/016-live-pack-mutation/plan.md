# Implementation Plan: Live-Run Pack Mutation — Failure-Triggered Self-Improvement

**Branch**: `016-live-pack-mutation` | **Date**: 2026-09-24 | **Spec**: `specs/016-live-pack-mutation/spec.md`

## Summary

`runtime/mutate.py` — a reflection pass invoked inside the live run loop: per trigger, assemble a failure digest → `rimbrain.improve` model call → deterministic gate → `packs/candidates/cand-mut-*.yaml`. `runtime/packmut.py` — shared pack-mutation ops engine (feature-009 `_apply_ops` generalized to full-pack, id-keyed paths). Boundary promotion + auto-revert at next run start (`mutate.boundary` before `load_pack`). Trigger policy lives in the pack's `mutate:` section.

## Technical Context

- Goal outcomes exist (feature 007/015): `task.transition` terminal states for `start.*`/`govern.*`/`combat.*` flow through the run sink; `requeued`/`escalate` are the near-failure signals.
- Candidate pipeline exists (feature 005): `packs/candidates/` + `templates.validate_pack` + inventory check; `planloop._materialize_candidate` is the model for re-validation.
- Defect diagnosis exists (feature 009): `improve.diagnose` runs pack-declared `defect_patterns` over an event list — reusable on a sliding window.
- Model roles exist (feature 002): `resolve_role("rimbrain.improve")` + `openai_compat_chat` — same shape as `planning.propose`; `rules-only` sentinel degrades to deterministic remediation.
- Boundary safety exists (feature 015): `dispatch.pack_drift` makes mid-run pack-file writes freeze dispatch — therefore candidates promote only at next run start, before `load_pack`, when no dispatch can interleave.
- `improve.score`/`episode_metrics` (feature 009) provide the regression comparison for auto-revert.
- Python 3.13, pytest, Windows dev / single-exe frozen via `rimbrain.py`; `_root.py` resolves writable `packs/` beside repo/exe.

## Constitution Check — PASS

- **I deterministic-before-probabilistic**: gate, triggers, promotion, revert are code; the model only proposes data.
- **II one writer / bounded model**: mutation writes pack files, never the bridge; model output is a typed proposal validated before any file lands.
- **V policy at boundaries**: promotion only at run start, pre-`load_pack`, atomic; active pack immutable during the run — `pack_drift` untouched.
- **VI staged promotion**: candidate → re-validation → boundary install → auto-revert on regression.
- **VII diagnosis**: every trigger/proposal/verdict/promotion/revert emits a canonical `mutation.*` event; `planning.json` exposes the loop.
- **IX policy is data**: cadence, near-failure thresholds, cooldown, budget in the pack's `mutate:` section; ops engine is strategy-agnostic.
- **X lifecycle**: boundary install happens before pack load — no mid-run reinit needed; tombstone machinery unaffected.

## Structure

```
components/runtime/src/runtime/packmut.py    # full-pack ops engine: set/append/remove/upsert, id-keyed paths
components/runtime/src/runtime/mutate.py     # triggers, digest, model call, gate, candidate write, boundary promote/revert
components/runtime/src/runtime/improve.py    # _apply_ops delegates to packmut (behavior preserved)
components/runtime/src/runtime/startmode.py  # per-poll trigger hook + event window ring buffer
components/runtime/src/runtime/loop.py       # --live-mutate flag; boundary() before load_pack
components/runtime/src/runtime/views.py      # planning.json mutation block
components/runtime/src/runtime/feed.py       # narration for mutation.* types (if needed)
components/contracts/schemas/runtime/mutation.schema.json   # rimbrain.improve output contract
components/contracts/schemas/events/types/mutation.*.schema.json + event-map.yaml + corpus
components/rimbrain/packs/{start-mode-v0,improve-v0}.yaml   # mutate: config blocks
profiles/bindings.yaml                       # rimbrain.improve role + degraded path
rimbrain.py                                  # --live-mutate in default run args
components/runtime/tests/test_mutate.py      # triggers, gate, boundary promote/revert, flag-off
```

## Decisions

See `research.md` — headline choices: **boundary promotion over mid-run swap** (pack_drift stays absolute; operator-confirmed), **full-pack ops vocabulary** (id-keyed paths subsume both existing mutation engines), **new `rimbrain.improve` role** (rules-only degraded path reuses 009 remediations), **revert via recorded lineage + episode-metrics regression**.

## Phases

1. Contracts: `mutation.schema.json` + `mutation.*` event-type schemas + event-map + corpus cases.
2. `packmut.py` ops engine + refactor `improve._apply_ops` onto it.
3. `mutate.py`: trigger evaluator, digest builder, `rimbrain.improve` call, gate, candidate materialization, boundary promote/revert.
4. Wiring: `startmode` poll hook, `loop --live-mutate` + boundary call, `rimbrain.py` default, bindings role, pack `mutate:` blocks, views block.
5. `test_mutate.py` + regression suite; ADR-018; AGENTS.md phase note.
