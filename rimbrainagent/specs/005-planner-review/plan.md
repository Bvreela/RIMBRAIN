# Implementation Plan: Strategic Planner / Review Loop

**Branch**: `005-planner-review` | **Spec**: `specs/005-planner-review/spec.md`

## Summary

Wire the planning tier: `rimbrain.plan` (OpenRouter/Gemini) consumes state + active pack → typed PlanProposal (schema-validated) → deterministic review gate + optional `rimbrain.review` critique → accepted proposals write candidate packs under `packs/candidates/` and may dispatch through the feature-004 single writer. Canonical `plan.*` events carry endpoint/model/usage provenance; endpoint failure degrades to a rules-only fallback plan.

## Technical Context

- Runtime feature 002: `resolve_role` (degraded paths), `build_client` (openai-compat chat honoring strict), UsageTracker, pinned manifests.
- Runtime feature 004: `templates.load_pack` (schema+inventory+hash), `Dispatcher` (single writer, drift guard), `loop.py` pattern.
- Planner needs no bridge client — dispatch only (FR-406). Model is advisory; code decides (FR-403).

## Constitution Check — PASS

- Models propose typed plans only; deterministic gate decides (I, FR-403).
- Active pack immutable; candidates never auto-active (I/IV).
- One writer: plan actions route through Dispatcher only (II).
- Degraded paths honored; no hangs (UR-MOD-017).

## Structure

### Contracts

```
components/contracts/schemas/runtime/plan.schema.json
components/contracts/schemas/events/types/plan.{proposed,reviewed,accepted,rejected}.schema.json
registry/event-map.yaml += plan.*
corpus: plan.valid.01, plan.invalid.01-03
```

### Runtime

```
runtime/planning.py    prompt builder, chat call via bindings, JSON extraction
                       (fenced/bare), schema validation, rules-only fallback
runtime/review.py      deterministic gate + optional model critique -> ReviewVerdict
runtime/planloop.py    orchestrator: status -> plan -> review -> candidates/dispatch
                       + canonical events + usage; CLI `python -m runtime plan`
components/rimbrain/packs/candidates/   materialized revisions
tests/test_planning.py test_review.py test_planloop.py
```

### Pack addition

`core-survival-v0.yaml` += `fallback_plan:` (deterministic rules-only plan) — additive data, same schema (extra key allowed).

## Phases

1. Contracts: plan.schema.json, plan.* event schemas, event-map, corpus.
2. `planning.py`: prompt builder (state+pack digest), client call, extractor, validator, fallback.
3. `review.py`: deterministic checks (templates/params/mutation legality) + optional critique.
4. `planloop.py` + CLI: orchestration, candidates writer, events, `--live` opt-in, scored guard.
5. Tests: stub-decider offline matrix, override-model-approval, malformed, bit-identical runs, candidate load, degraded path.

## Decisions

- **Deterministic gate is code**: the review model's verdict is advisory text; acceptance requires checks to pass. SC-401 test pins an *approving* stub over a violating plan → still rejected.
- **JSON extraction**: fenced ```json → bare-object scan → fail. No partial parsing.
- **Candidates naming**: `<pack_id>-<sha8>.yaml` under `candidates/`; sha8 from canonical hash of materialized pack → collision-free, content-addressed.
- **Fallback plan**: declared in pack (`fallback_plan`) so rules-only is pack-authored data, not hardcoded behavior — pack diff shows what degraded mode does.
- **Usage**: planning calls fold into the session UsageTracker; events carry per-call prompt/completion tokens.
- **No subagents**: single coherent module set; I'll implement directly.
