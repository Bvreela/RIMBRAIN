# Feature Specification: Live-Run Pack Mutation — Failure-Triggered Self-Improvement

**Feature Branch**: `016-live-pack-mutation`

**Created**: 2026-09-24

**Status**: Implemented (T030 live smoke pending)

**Input**: "I want more mutation and self improvement in every live run. I want failure and near failure states to trigger mutation by the brain ai on the pack file. I want pack improvement after every 10 goals are tried. The Brain agent should first think about any potential failure paths that look likely or have triggered, or look at why goals are failing and make a best change to have a better outcome next run."

## Purpose

Feature 009's improvement loop is an offline pass — it runs as its own mode over recorded evidence, proposes rules-only remediations, and promotes at an episode boundary. Between those passes, a live run that starts failing keeps failing with the same pack.

This feature moves mutation **into** the live run. Goal failures, near-failures (requeues, stalls, escalations, refusals), and a periodic every-N-goals cadence each trigger a reflection pass: the `rimbrain.improve` model analyzes which failure paths have triggered or look likely, why goals are failing, and emits one bounded pack-mutation proposal. A deterministic gate validates it; accepted proposals materialize as candidate packs. Promotion happens only at the **run boundary** — the next launch validates the pending candidate, installs it over the active pack, and records lineage so a regressed episode auto-reverts to the parent.

Decisions confirmed with the operator: promotion at next-run boundary only (never mid-run — `dispatch.pack_drift` stays absolute); mutation scope is the **full pack** (any section, gated by schema/policy/inventory validation); a promoted pack that regresses auto-reverts to its parent; the analysis uses a new `rimbrain.improve` role binding.

Constitution hooks: Principle I (code decides legality, model advises), II (model never holds a write path — it proposes data), V (policy activates at boundaries, immutable during runs), VI (staged promotion: candidate → validation → boundary → revert-on-regression), VII (every trigger/proposal/verdict/promotion/revert is a canonical event), IX (mutation cadence, trigger thresholds, and mutable policy all live in pack data — code provides primitives only).

## User Stories *(mandatory)*

### User Story 1 - Failure Triggers a Reflection Pass (Priority: P1)

During a live `--live-mutate` run, when a goal reaches `failed`/`expired`, or shows a near-failure signal (requeue after a verify miss, escalation steps firing, dispatch refusals, a phase stuck `blocked`, or a pack-declared defect pattern hitting over recent events), the runtime runs a reflection pass: it assembles a failure digest (which goals failed and why, recent refusals, defect findings, the relevant pack sections) and asks the `rimbrain.improve` model for the single best pack change that would produce a better outcome. The model's proposed mutations are deterministically validated; a passing proposal is written as a candidate pack. The running colony is never interrupted — mutation is a side-channel, not a pause.

**Why this priority**: This is the core ask — the brain reacting to its own failures instead of repeating them until an offline improve run happens.

**Independent Test**: Run a live run against a scripted/degraded scenario where a goal fails; assert a `mutation.triggered` → `mutation.proposed` → `mutation.candidate` event chain and a candidate file on disk, while dispatch evidence shows the active pack untouched.

**Acceptance Scenarios**:

1. **Given** a live run where `govern.<id>` transitions to `failed`, **When** the next poll evaluates triggers, **Then** a reflection pass runs and emits `mutation.triggered` with the failing goal evidence.
2. **Given** a goal requeued after `effect_absent_retry` (near-failure), **When** the configured near-failure threshold is met, **Then** a reflection pass runs naming that goal's stall as the failure path.
3. **Given** the model returns mutations that fail validation, **When** the gate runs, **Then** `mutation.rejected` records the violations and no candidate is written.
4. **Given** the model endpoint is unreachable, **When** a trigger fires, **Then** the degraded path applies the pack's rules-only remediations (or records `mutation.degraded` if none apply) — the run continues unimpaired.

---

### User Story 2 - Periodic Improvement Every N Goals (Priority: P2)

Independent of failures, every N goals reaching a terminal state (default 10, pack-configurable) triggers an improvement pass over accumulated evidence — the brain looks for likely failure paths and soft regressions, not just hard failures, and may propose a mutation or explicitly decline (`noop`).

**Why this priority**: The standing cadence guarantees self-improvement pressure even on clean runs; P1 already proves the reflect→gate→candidate pipeline.

**Independent Test**: Drive a run past 10 terminal goal transitions with no failures; assert exactly one periodic `mutation.triggered` (reason `cadence`) fires and the counter resets.

**Acceptance Scenarios**:

1. **Given** a run where 10 goals reach terminal states since the last pass, **When** the poll boundary is reached, **Then** a reflection pass runs with the window's goal outcome summary.
2. **Given** the model proposes no change (or `noop`), **When** the pass completes, **Then** `mutation.noop` records the analysis rationale and the cadence counter resets.
3. **Given** a pass already ran this window, **When** the next 10-goal boundary arrives, **Then** the counter restarts from zero — passes don't accumulate debt.

---

### User Story 3 - Boundary Promotion With Auto-Revert (Priority: P1)

Candidates never touch the live run. At the next run start, before the pack loads, a pending candidate is re-validated and installed over the active pack file (atomically), with its parent hash and the pre-promotion episode metrics recorded. When the following run ends (or at the subsequent boundary), the episode's metrics are compared against the recorded baseline; a regression restores the parent pack and marks the mutation reverted.

**Why this priority**: Without promotion the feature is a proposal generator; without revert it can ratchet the pack downhill. Together they make the loop safe to leave on every run.

**Independent Test**: Seed a pending candidate + a regressed episode log; start a run; assert the parent pack content is restored and `mutation.reverted` is emitted. Separately: a non-regressed run leaves the promoted pack in place.

**Acceptance Scenarios**:

1. **Given** a validated pending candidate, **When** the next run starts, **Then** it is installed as the active pack before any dispatch and `mutation.promoted` records `{candidate, parent_hash, baseline_metrics}`.
2. **Given** a promoted pack whose episode scores worse than baseline, **When** the boundary evaluation runs, **Then** the parent pack content is restored and `mutation.reverted` records the score comparison.
3. **Given** a candidate that fails re-validation at boundary (e.g. inventory drift), **When** the boundary check runs, **Then** it is discarded with `mutation.rejected` and the incumbent pack loads unchanged.
4. **Given** a mid-run file edit to the active pack (operator or defect), **When** dispatch runs, **Then** `dispatch.pack_drift` still refuses — mutation machinery never weakens the drift invariant.

---

### User Story 4 - Mutation Transparency (Priority: P3)

Every trigger, proposal, gate verdict, candidate, promotion, and revert is a canonical `mutation.*` event narrated to the feed; `planning.json` carries a mutation section (passes run, candidates pending, last verdict) so the overlay shows the loop working.

**Why this priority**: Diagnosis is a constitution principle and cheap once events exist, but the feature is playable without the view polish.

**Independent Test**: After a triggered pass, `events.jsonl`/`feed.md` contain the event chain and `planning.json` shows the mutation block.

**Acceptance Scenarios**:

1. **Given** any mutation pass, **When** it completes, **Then** the feed narrates trigger reason, proposed change, and gate outcome in plain language.
2. **Given** a promoted candidate, **When** the next run's views render, **Then** `planning.json` identifies the active mutation lineage (pack revision + parent).

---

### Edge Cases

- **Crash between candidate write and boundary**: the pending-candidate record is a durable file; the next launch re-validates before installing — a torn candidate can never promote.
- **Model unavailable for the whole run**: every trigger degrades to rules-only remediation (feature-009 ops) or `mutation.degraded`; the run itself is unaffected.
- **Mutation storm**: per-run cap and inter-pass cooldown (pack-configured) bound how often the model is called; cadence + failure triggers share the same budget.
- **Bad mutation that still validates** (e.g. an impossible threshold): allowed through the gate but caught by regression revert — the revert is the safety net for semantically-bad-but-legal mutations.
- **Sim/determinism**: `--live-mutate` is never set for sim or scored runs; sim keeps bit-identical output (the chat call is injectable for tests only).
- **Mutation proposes dev tooling under `--fair`**: the candidate fails the class check — a fair run can never promote a dev-class pack.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-1401**: `runtime/mutate.py` — a reflection pass invoked inside the live run loop (start mode; wiring is loop-agnostic). Per trigger: build a failure digest → call `rimbrain.improve` → validate the returned mutation set → materialize `packs/candidates/cand-mut-*.yaml` → emit canonical events. `mutate` makes **no game writes** and never edits the loaded pack document or the active pack file.
- **FR-1402**: Trigger evaluation each poll under `--live-mutate`, driven by the pack's `mutate:` section: `goals_per_pass` (default 10 terminal `start.*`/`govern.*`/`combat.*` transitions since last pass), `on_failure` (immediate pass on goal `failed`/`expired`), `near_failure` (requeue count, escalation firing, `action.refused` burst, `blocked` dwell, and `improve.defect_patterns` hits over a sliding event window), `cooldown_polls`, `max_passes_per_run`.
- **FR-1403**: Failure digest (model input): failing/stuck goal ids + last transition reason + attempts + the goal's pack spec, recent `action.refused`/`action.failed` (template, error code), defect-pattern findings over the window, current pack id/hash, and the mutation op vocabulary — compact, bounded size.
- **FR-1404**: `rimbrain.improve` role in `profiles/bindings.yaml` (primary: the planner-grade remote model; degraded path ending in a `rules-only` sentinel). On `rules-only`, the pass applies the active pack's deterministic defect remediations (feature-009 ops) or emits `mutation.degraded` — never a silent skip.
- **FR-1405**: Mutation contract `contracts/schemas/runtime/mutation.schema.json`: `{schema_version, mutation_id, base_revision, analysis: {failure_paths[], likely_paths[]}, mutations[{op, path|target, value|patch}], rationale}`. Op vocabulary covers the full pack: `set`/`append`/`remove`/`upsert` addressed by dotted path with by-id list targeting (`govern.goals.<id>.retry_polls`, `templates.<id>.params_schema`, `emergency.<id>`), plus template add/drop. Unknown ops fail validation.
- **FR-1406**: Shared ops engine `runtime/packmut.py` (feature-009 `_apply_ops` refactored into it, behavior preserved) applies a validated mutation set to a candidate pack document; id-keyed paths resolve list elements by their `id` field.
- **FR-1407**: Deterministic gate before materialization: ops conform to the contract → mutated doc passes `templates.validate_pack` + `policy.validate_policy` + sealed-inventory method check + `class` consistency with the run's fairness mode → non-vacuous (the doc actually changed). Gate failures emit `mutation.rejected` with violations.
- **FR-1408**: Boundary promotion — at run start (before `load_pack`), `mutate.boundary()` inspects the pending-candidate record: re-validate → atomically install over the target pack file → record `{candidate_hash, parent_hash, parent_path, baseline_metrics}` lineage in `state/mutations.jsonl` → emit `mutation.promoted`. A candidate that fails re-validation is discarded (`mutation.rejected`, gate `boundary`).
- **FR-1409**: Auto-revert — at each boundary, score the just-finished episode (`improve.score` weights from the pack's `improve.metrics`) against the baseline recorded at the last promotion; on regression, restore the parent pack file and emit `mutation.reverted` with both scores. Revert never fires without a recorded lineage entry.
- **FR-1410**: Canonical events `mutation.triggered|proposed|rejected|candidate|promoted|reverted|degraded|noop` into the run's event stream (feed + store); `planning.json` gains a `mutation` block (last trigger, passes run, pending candidates, last verdict, active lineage).
- **FR-1411**: `--live-mutate` flag on `runtime loop` (default off; enabled in the `rimbrain run` default invocation). Sim and scored runs never enable it; the model call is injectable so tests are deterministic.
- **FR-1412**: `improve-v0.yaml` gains the `mutate:` config block (cadence, near-failure thresholds, cooldown, budget); `start-mode-v0` carries the live-run trigger policy. Mutation policy stays pack data (Principle IX).

### Key Entities

- **Mutation pass**: one trigger → digest → proposal → gate → outcome cycle, bounded in time and output.
- **Candidate pack**: a mutated pack document in `packs/candidates/` with provenance (`base_revision`, trigger reason, mutation id).
- **Pending-candidate record**: durable pointer (`state/mutations.jsonl` row) linking a candidate to its target pack file for next-boundary installation.
- **Mutation lineage**: parent hash + parent file path + baseline episode metrics — the rollback chain.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-1401**: In a live run where a goal fails, a reflection pass completes and records its outcome within the same run — zero operator intervention.
- **SC-1402**: Every 10 terminal goals triggers exactly one pass; 100 goals → 10 cadence passes (subject to per-run budget).
- **SC-1403**: A promoted pack that regresses is reverted at the next boundary — verified by pack hash returning to the recorded parent.
- **SC-1404**: Mid-run, zero `dispatch.pack_drift` events are caused by the mutation machinery (the active pack file is never written during a run).
- **SC-1405**: Sim mode remains bit-identical across repeated runs (mutation path never executes under sim).
- **SC-1406**: Every pass leaves a reconstructable evidence chain (`mutation.*` events + candidate file + lineage row).

## Assumptions

- "Every 10 goals tried" counts **terminal** goal transitions (succeeded + failed + expired) — proposals alone don't count toward the cadence.
- The `rimbrain.improve` primary binding reuses the verified planner model (OpenRouter nemotron); it is independently rebindable.
- One mutation set per pass ("a best change") — the model returns its single highest-confidence set, not a batch.
- Boundary = run start (pre-load), not process exit — durable against kills mid-run.
- `--mode improve` (offline diagnose→promote) remains available unchanged; live mutation is additive.
- Auto-revert uses the episode-metrics score already defined for the improve loop; "regression" = strictly worse score.
