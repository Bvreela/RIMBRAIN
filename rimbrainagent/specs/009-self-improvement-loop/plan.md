# Implementation Plan: Self-Improvement Loop

**Branch**: `feature/009-self-improvement` | **Spec**: `specs/009-self-improvement-loop/spec.md`

## Summary

`runtime/improve.py` — a deterministic improvement cycle over the canonical stores: diagnose (replay `events.jsonl` for defect patterns) → propose (candidate pack via existing pipeline or rules-only) → audit (code/policy/UX checks, verdict events) → validate (metrics on replayed evidence) → decide (promote at episode boundary / reject / defer). `runtime/feed.py` — a thought-feed renderer narrating every canonical decision event into `state/feed.md`. `runtime/metrics.py` — per-episode learning metrics folded from evidence. Customization guide documents the editable brain surface.

## Technical Context

- Stores exist (feature 006): `EventStore.load()` replays `state/events.jsonl`; ledger folds `state/tasks.jsonl`.
- Candidate pipeline exists (feature 005): `packs/candidates/` + deterministic gate — promotion must NOT auto-activate.
- Verifier/ledger exist (feature 007); StartMode shows the phase-driver pattern (feature 008).
- Feed = pure function of canonical events → degradable to structured echo when no narrator bound (fail-closed).
- Audit checks reuse existing tooling: pytest suite, corpus runner, `validate_components.py`, pack inventory cross-check — all fail-closed subprocess-free where possible (import the validators directly).

## Constitution Check — PASS

Single writer untouched; typed proposals only; active-pack immutability at episode boundary; canonical records authoritative; fail-closed; feed never leaks secrets (same classification rules).

## Structure

```
components/runtime/src/runtime/feed.py       event -> narrative entry renderer + state/feed.md writer
components/runtime/src/runtime/metrics.py    episode metrics fold -> episode.metrics event
components/runtime/src/runtime/improve.py    cycle driver: diagnose/propose/audit/validate/decide
components/runtime/src/runtime/audit.py      code/policy/UX checks -> audit.verdict events
components/contracts/schemas/events/types/   selfcheck.diagnosed, audit.verdict,
                                             improvement.promoted, improvement.rejected,
                                             episode.metrics schemas
components/contracts/registry/event-map.yaml + examples corpus
components/rimbrain/packs/improve-v0.yaml     cycle config: cadence, metrics, audit gates, defect patterns
docs/brain-customization.md (or components/rimbrain/CUSTOMIZE.md)
components/runtime/tests/test_{feed,metrics,improve,audit}.py
```

## Decisions

- **Loop is a ledger-driven driver like StartMode** — cycles are durable; crash mid-cycle reconciles and resumes; `--mode improve` CLI wiring, iterations-bounded (FR-808).
- **Feed degrades gracefully**: renderer has deterministic templates per event type; a narrator model binding is optional and advisory — missing binding → structured echo, never blank.
- **Audit verdicts are canonical events** — the check mechanism is internal but the contract is evidence; unsafe candidates die at the audit gate regardless of metric gains.
- **Promotion = copy candidate → active packs dir at episode boundary** — recorded in `improvement.promoted`; runtime never hot-swaps mid-episode.
- **Metrics are a pure fold** — same input events → identical metrics event (determinism aids tests + replay).

## Phases

1. Contracts: 5 new event-type schemas + event-map + corpus cases.
2. `feed.py` + `metrics.py` (pure functions first).
3. `audit.py` + `improve.py` + `improve-v0.yaml` + `--mode improve` wiring.
4. Customization guide + tests (planted-defect diagnosis, unsafe-candidate refusal, feed coverage, metrics determinism) + polish.
