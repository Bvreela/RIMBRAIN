# ADR-017: Fair/dev pack classes and post-start governance boundary

**Status:** ACCEPTED
**Date:** 2026-09-23
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** UR-BRN-018; UR-RUN-009; specs/015-post-start-governance; ADR-015

## Context

Two structural problems surfaced after feature 012's full policy externalization:

1. **Dev tooling inside the gameplay pack.** `start-mode-v0` carried `dev.*` templates (spawn-hostile, heal-pawn) and the scripted `combat` section. Under `--fair`, dispatch refused them per-call — but the methods still sat in the loaded template registry, one code path away from a scored write. Test tooling and gameplay policy had identical trust footing.
2. **`start.completed` was an exit.** The bootstrap graph ended the run exactly when the colony became interesting: baseline met, nothing directing what comes next. Post-start direction existed only as outside-the-run callers (cycle phases), not as pack policy.

## Decision drivers

- Fair runs must **structurally lack** debug capability: absent tooling beats refused tooling — a `dev.*` action in a fair run should be `unknown_action`, not a policy refusal.
- The refusal must happen **at pack load**, before any write authority exists (CONFIG-AND-PACK §3: failure is explicit and precedes write authority).
- Post-start goals are **pack data**, per ADR-015: sustainment and ambition objectives share the phase machinery — ordered, `when`-gated, verifier-checked — no new engine concept.
- Completion semantics stay honest for bounded callers: cycles and tests still stop at `start.completed`.

## Options considered

### Option A — Keep dev methods, rely on dispatch refusal

Rejected: the registry still contains the methods; every future dispatch path must remember to refuse them. Fairness becomes a convention, not a property.

### Option B — Separate dev pack + `class` load gate (chosen)

`class: fair|dev` on the pack; `Dispatcher(fair=True)` rejects any pack declaring `dev.*` methods at load (`pack.not_fair`). Dev tooling and combat scripting move to `dev-lab-v0` (`class: dev`); `start-mode-v0`, `core-survival-v0`, `improve-v0` become `class: fair`. `--mode combat`/`cycle` load the dev pack.

### Option C — Post-start goals as a new engine subsystem

Rejected: `govern.goals` reuse the phase interpreter exactly — `requires`/`when`/`effect`/`steps`/`repeat` through the same TaskLedger lifecycle with `govern.` task ids. A terminal goal re-arms only while its observed effect has lapsed, which covers both sustainment (beds, meals) and long-horizon ambitions (research queue, mission letters) without a second engine.

## Decision

**Options B + C.** Pack classes gate tooling at load; `govern` extends the phase machinery past `start.completed` on held runs (`run_start(hold=True)`, `--no-hold` to opt out, `cycle` passes `hold=False`). The overarching strategy option space ships as pack data too: `packs/colony-goals-v0.yaml` + per-pack `goal_options` — annotated choices the planner may promote into `govern.goals`, never auto-executed.

## Consequences

### Positive

- A fair run provably cannot spawn/heal/save-load: the methods are not in its registry (SC-1303).
- Dev tooling lives in one place (`dev-lab-v0`) and stays editable without touching the scored pack.
- `start.completed` is a handoff: the agent keeps sustaining and advancing the colony on the same verified ledger machinery — evidence continuity is unbroken.
- Goal options give the planner a wealth/raid-threat-annotated choice set without expanding the engine.

### Negative

- Two pack artifacts to maintain in parallel (`start-mode-v0`/`dev-lab-v0` share start+universal policy) — drift risk accepted; dev-lab is the superset.
- `goal_options` is duplicated across three packs and the standalone catalog; the catalog is the authoring source.
- Held runs never self-terminate: a `--mode start` live run now runs until interrupted — intended, but callers that assumed completion = exit must pass `--no-hold`.

## Compatibility and migration

- `class` is optional in the schema; absent = unclassified (legacy packs still load, fair runs treat undeclared dev methods by the same load check).
- `goal_options`/`govern` are additive pack sections; pre-015 packs load unchanged.
- Tests that exercised combat scripting moved to `dev-lab-v0`; no runtime API break — `run_start` gained a defaulted `hold` kwarg.

## Revisit/kill criteria

- If more than two pack classes emerge (e.g. `lab`), extend the enum — do not add per-method flags.
- If `goal_options` needs machine-checkable eligibility, move `phase`/`prerequisites` to predicate form in a schema minor version.
