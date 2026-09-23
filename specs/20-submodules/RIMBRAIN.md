# RimBrain submodule build specification

**Status:** READY  
**Future path:** `components/rimbrain`  
**Future remote:** `rimbrain-core`  
**Owns:** reusable human-readable policy and its replay fixtures

## 1. Purpose

RimBrain is the editable, forkable strategy and decision layer. It lets humans and reviewers improve gameplay without modifying runtime code. A release is an immutable pack identified by a manifest hash.

## 2. Contents

- objectives and plan templates;
- task templates and workflow DAGs;
- decision matrices and deterministic scoring/fallbacks;
- parameters, thresholds, hysteresis, budgets, cadence;
- planner/reviewer/critique/judge prompt artifacts;
- human-readable strategy rules and source priors;
- reviewed lesson snapshot with support/counterevidence;
- decision, plan, failure, injection, hazard, and regression fixtures;
- compatibility, provenance, license, manifest, and changelog.

## 3. Non-goals

- Per-episode active state.
- Private raw evidence.
- Credentials or endpoint URLs requiring secrets.
- Python/C#/JavaScript execution.
- Bridge RPC implementation.
- Evaluator or verifier code.
- Self-activation.

## 4. Layout

```text
MANIFEST.yaml
CHANGELOG.md
objectives/
plans/
tasks/
workflows/
matrices/
parameters/
prompts/
knowledge/rules/
lessons/snapshot.yaml
fixtures/
  decisions/
  plans/
  failures/
  hazards/
  injection/
compatibility/
licenses/
```

Schemas are consumed from Contracts; they are not forked locally except pinned references.

## 5. Matrix design

Each matrix row declares stable identity/revision, priority, typed conditions, required features/freshness, candidate generator/action template references, at most four productive options plus continuation/escalation, hard exclusions, deterministic score/fallback, cooldown/limits, predicted outcomes, verifier, and selector qualification metadata.

Rows must be mutually deterministic. Same-priority overlap is invalid. Candidate IDs are templates until runtime binds them to real targets; models never supply bindings.

## 6. Plan/workflow design

Plans carry horizons, assumptions/check predicates, alternatives, milestones, resource envelopes, progress floors, predictions, failure/replan triggers, and pre-mortem. Workflows are acyclic graphs of observe/verify/task/wait. Direct RPC nodes are invalid.

## 7. Prompts

Prompts are Markdown with structured frontmatter: role, schema contract, supported operations, packet version, token budget, safety posture, and revision. Prompt changes are pack changes and require replay evidence. Prompts may request concise claims/rationales but cannot weaken local validation.

## 8. Knowledge and lessons

Knowledge cards identify source, game/mod compatibility, context keys, recommendation, exceptions, and evidence status. Lessons include stable statement, applicability, support, counterevidence, provenance, status, and re-prove horizon. They never override legality, fresh observations, locks, or safety invariants.

## 9. Manifest and trust

Manifest includes pack ID/version/channel, schema release, RimWorld/runtime/Steward/RimBridge compatibility, dependencies, file hashes, authorship, licenses, provenance parent, fixture suites, prompt/model expectations, validation results, and optional signature. Signature authenticates origin only.

Channels:

- `dev`: proposal/experiment; not ranked;
- `stable`: reviewed release;
- `frozen`: exact scored snapshot.

## 10. Human editing workflow

1. Fork/checkout a working pack.
2. Create one scoped proposal with rationale and evidence refs.
3. Add or update fixtures demonstrating intended behavior.
4. Run schema/reference/DAG/bounds/replay validation.
5. Review a semantic diff, including route and threshold changes.
6. Run matched development trials when required.
7. Human approves/signs release.
8. Runtime pins new hash at episode boundary.

Runtime-generated proposals write outside the active pack and follow the same flow.

## 11. Qualification and calibration records

Pack content declares desired selector routing but live eligibility also needs an immutable calibration snapshot/result from Lab. A row without sufficient matching evidence remains rules-only even if policy asks for a model. Pack validation rejects qualifications referring to unknown model/renderer revisions or expired evidence.

## 12. Seed content migration

- Convert upstream `brain/skills/*.md` into knowledge cards, preserving provenance and marking claims as source priors/hypotheses.
- Do not migrate `brain/tools/*.py` or `brain/watchers/*.py` into auto-applied pack content.
- Convert current root settings examples into schema-valid objectives, tasks, workflows, matrices, parameters, and prompts.
- Derive initial fixtures from upstream tests/captured decisions; synthetic cases are labeled.
- No upstream episode result is promoted as supported policy without context-matched evidence.

## 13. Tests

- Full pack schema and content-hash validation.
- Stable/reference uniqueness and compatibility resolution.
- Matrix overlap, candidate limit, fallback, freshness, threshold-pair validation.
- DAG cycle/orphan/unreachable-node validation.
- Prompt frontmatter/budget/injection fixture checks.
- Fixture replay and append-only ratchet check.
- Semantic diff snapshots.
- Signature/hash tamper tests.

## 14. Release increments

- **B0:** core-survival skeleton and manifest.
- **B1:** landing/food/shelter/health matrices and first-week workflows.
- **B2:** power/logistics/mood/research and hazard fixtures.
- **B3:** defense/recovery, trade/people/world/endgame.
- **B4:** reviewed lesson snapshot and selector qualifications.

## 15. Acceptance

A community contributor can understand and edit a row without runtime code, prove the change with a fixture, inspect a semantic diff, validate/sign the pack, and have runtime either pin it safely or reject it with exact contract errors. The pack contains no executable code or secrets.
