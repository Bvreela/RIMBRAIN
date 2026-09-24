# ADR-018: Live-run pack mutation — trigger, gate, boundary promotion, auto-revert

**Status:** ACCEPTED
**Date:** 2026-09-24
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** UR-BRN-004/005/006 (immutability, proposal-only models, atomic activation with rollback lineage); UR-BRN-011..013 (policy is data); UR-RUN-006/007 (failure backoff, hysteresis); specs/016-live-pack-mutation; ADR-015, ADR-017

## Context

Feature 009's self-improvement loop is an offline pass: it diagnoses defect patterns in recorded evidence and promotes remediated packs at an episode boundary — but only when the operator runs `--mode improve`. A live run that starts failing keeps executing the same failing policy until someone intervenes. The operator requirement: **every live run mutates** — goal failures, near-failures (requeues, stalls, escalations, refusals), and a periodic every-10-goals cadence each trigger a `rimbrain.improve` reflection that proposes the best single pack change for a better outcome next run.

## Decision drivers

- `dispatch.pack_drift` re-hashes the active pack file on every dispatch — an in-place mid-run edit freezes the run. The active pack file must be write-never during a run.
- The brain-reset channel can hot-swap packs but tombstones every task namespace — too disruptive to fire on every mutation, and scored/immutable semantics argue against mid-run policy shifts anyway (UR-BRN-004).
- Two partial mutation engines already exist with different vocabularies: `improve._apply_ops` (cfg-path ops, dicts only — can't reach `govern.goals[i]`) and `planloop._apply_mutations` (add_template/edit_decision_map/add_emergency only). A full-pack scope needs one engine.
- A model-authored mutation that validates structurally can still be semantically wrong (impossible threshold, counterproductive goal edit). The gate cannot catch that — only observed regression can (Principle VI: bounded trials, staged promotion).

## Options considered

### Option A — Mid-run hot-swap via brain reset

Rejected: full task-namespace reinit per mutation; policy shifts mid-episode weaken evidence attribution (which pack produced which outcomes); operator chose boundary promotion.

### Option B — Offline improve pass only, run more often

Rejected: misses the ask — failure-triggered reaction inside the run, plus model-authored analysis rather than pack-declared remediations alone.

### Option C — Live reflection pass + boundary promote + lineage revert (chosen)

In-run triggers → `rimbrain.improve` proposal → deterministic gate → candidate file. Next run start (pre-`load_pack`) re-validates and installs over `pack_path(target)`; lineage + `improve.score` comparison auto-reverts a regressed promotion.

## Decision

**Option C.** `runtime/mutate.py` runs inside the live loop under `--live-mutate`: pack-configured triggers (`goals_per_pass` default 10 terminal goals; `on_failure`; `near_failure` signals) fire a reflection pass — failure digest → `rimbrain.improve` (degrades to `rules-only` remediations when no model) → gate (schema, base_revision freshness, non-vacuous, `validate_pack` + `validate_policy` + inventory + class) → `packs/candidates/`. `mutate.boundary` at next run start installs or discards the pending candidate and reverts on episode-score regression. `runtime/packmut.py` is the single full-pack ops engine (`set`/`append`/`remove`/`upsert`, id-keyed paths); `improve._apply_ops` refactors onto it. Trigger policy is pack data (`mutate:` section).

## Consequences

### Positive

- Failure-adaptive policy in every `--live-mutate` run; the loop learns during play, not only in post-hoc improve passes.
- `pack_drift` stays absolute — mutation machinery never writes the active file mid-run (SC-1404).
- One ops vocabulary for model + deterministic remediation paths; `improve.py` shrinks.
- Regressions self-heal at the boundary; lineage is canonical (`state/mutations.jsonl`).

### Negative / risks

- Model cost per pass is bounded by `cooldown_polls` + `max_passes_per_run` (pack data) but nonzero; a failing colony generates calls.
- A semantically-bad-but-valid mutation ships one episode before revert — acceptable: revert is automatic and evidence-backed.
- Boundary install touches the pack file outside a run — operators editing packs concurrently must expect promotion to overwrite; lineage keeps the parent.

## Verification

`test_mutate.py` (cadence/failure/near-failure triggers, gate rejections, boundary promote, regression revert, flag-off inert); contract corpus cases for `mutation.*` events; live smoke under `--fair --live-mutate` narrated in `feed.md`.
