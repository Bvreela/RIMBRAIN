# Lab submodule build specification

**Status:** READY  
**Future path:** `components/lab`  
**Future remote:** `rimbrainagent-lab`  
**Owns:** offline export, replay, evaluation, calibration, benchmark, and promotion evidence

## 1. Purpose

Lab turns canonical episode evidence into verifiable exports, replay fixtures, metrics, calibration reports, matched comparisons, and policy-promotion evidence. It is offline-first and cannot control a live colony in normal operation.

## 2. Scope

- Export profiles and redaction.
- Canonical JSONL verification and optional Parquet projection.
- Decision, plan, failure, and trace replay.
- Training trajectory generation.
- Selector calibration and drift baselines.
- Matched trial manifests/results/statistics.
- Community benchmark result envelopes.
- Pack diff, validation orchestration, proposal evidence, monitored cohort/yank reports.
- Data cards and quality reports.

## 3. Non-goals

- Live scheduling/dispatch.
- Provider authority in the running game.
- Pack activation.
- Automatic model fine-tuning in initial releases.
- A centralized marketplace/server.
- Treating correlated decisions as independent experiment samples.

## 4. Planned layout

```text
src/rimbrainlab/
  cli/
  ingest/
  validate/
  export/
    profiles.py
    redaction.py
    trajectories.py
    parquet.py
  replay/
    decisions.py
    plans.py
    failures.py
  evaluation/
    metrics.py
    matched.py
    survival.py
    calibration.py
    drift.py
    statistics.py
  packs/
    verify.py
    diff.py
    proposal.py
    promotion.py
  benchmark/
    manifest.py
    runner.py
    sanitize.py
  reports/
tests/
fixtures/
```

## 5. Export behavior

Input is a closed episode or consistent read-only snapshot. Lab validates source events before projection. Export profiles are allowlists:

- `audit-full`: local, most complete, provider terms permitting;
- `analysis`: normalized decisions/actions/outcomes with private text removed;
- `training`: trajectories, candidate masks, outcomes, horizons/censoring, split metadata;
- `community`: minimal sanitized evidence/benchmark result.

The exporter never mutates source records. Every projection records source hashes and transformation version.

## 6. Replay

Decision replay loads exact pack/model renderer qualifications, features, candidates, and expected route. It can run deterministic rules without model access and optionally invoke a configured selector in an isolated benchmark. Plan replay validates schema, references, DAGs, assumptions, and predicates. Failure replay asserts a proposed patch changes/prevents the intended diagnosis class.

A changed policy may produce a declared equivalent choice; equivalence must be explicit in fixture metadata, not guessed.

## 7. Calibration

Calibration key is matrix row × selector/model revision × renderer/prompt revision × context family. Lab stores predicted distributions where available and scored observed outcomes with missing/censored status. It compares against deterministic fallback, computes declared metrics, and emits qualification/demotion recommendations. Runtime consumes signed/frozen results but performs immediate safety fallback independently.

## 8. Evaluation

Metrics are lexicographic. Trial unit is episode/start-save family, not decision. Comparison manifests predeclare arms, metrics, guardrails, sample/sequential stopping, environment hashes, machine/game timing, intervention policy, and eval budget. Reports show distributions and uncertainty; no best-of-N filtering.

## 9. Community benchmark

A one-command harness eventually starts a declared profile on a licensed local game/save, records hashes and assistance flags, then produces a sanitized signed result bundle. No raw save or proprietary game content is redistributed. Server aggregation is deferred; static bundles/indexes suffice.

## 10. Upstream migration

`export_sft.py` and `llm.py` captures are legacy input adapters only. The current exporter selects by scalar score and can include hidden reasoning; the new training export instead consumes canonical decisions/outcomes, respects assistance and family splits, and excludes chain-of-thought by default. Legacy captures may be converted only with explicit incomplete-lineage labels.

## 11. Tests

- Golden profile exports and manifests.
- Secret/path/operator-text redaction corpus.
- Referential integrity and checksum tamper tests.
- Deterministic replay reproducibility.
- Missing/censored outcome handling.
- Start-family split leakage tests.
- Calibration baseline/demotion fixtures.
- Statistical tests with known synthetic distributions.
- Bad pack/proposal rejection and rollback lineage.
- Windows path and large/torn JSONL handling.

## 12. Delivery increments

- **L0:** canonical validation and audit/analysis export.
- **L1:** training trajectories, redaction, data cards, optional Parquet.
- **L2:** decision/plan/failure replay and pack diff.
- **L3:** matched evaluation, survival reports, calibration/drift.
- **L4:** promotion evidence and community benchmark bundles.

## 13. Acceptance

An independent consumer can verify an export, reconstruct decision lineage, replay deterministic routing, train from nonleaking trajectories, and reproduce reported metrics. Lab cannot mutate active runtime policy or issue live game writes.
