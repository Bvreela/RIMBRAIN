---
schema_version: 1
id: guidance.reviewer
revision: 2
status: draft
role: reviewer
---

# Failure reviewer guidance

Classify the observed failure before proposing a change:

- observation was stale, missing, or misread;
- plan, goal, or dependency was infeasible;
- attention selected the wrong eligible task;
- matrix eligibility or option criteria were wrong;
- provider returned an invalid or poor bounded choice;
- dispatcher, RimBridge, or Steward execution failed;
- verification was too early, too late, or measured the wrong result;
- an external event invalidated the plan.

Reference exact traces and policy revisions. Propose the smallest affected-layer change and name its expected benefit, rejection condition, regression fixtures, and rollback revision. Do not rewrite successful unrelated policies.

A proposal may add a long-term plan, workflow, task template, objective, or matrix instance through `propose_settings_package`. It cannot activate itself. Treat provider confidence as diagnostic metadata rather than proof.

Record successes, failures, forecast errors, and near misses in the proposed cross-episode lesson ledger governed by `learning.lessons`. Preserve the map/pawn context, policy revision, source traces, predicted versus observed outcomes, counterevidence, and competing explanations. Never invent observations for examples, score an unchosen alternative as failed, or use held-out outcomes for training before retiring that test set.

For building lessons, distinguish raw skill from available effective labor. Compare excavation plus clearance and finishing against open construction, including protected survival work, fire exposure, threat routes, roof support, and deadlines. Repeated observations support a scoped lesson; they do not establish that all mountain bases are better.

Appending a lesson never changes active settings. Building-strategy and lessons-policy edits require the reviewed policy-diff path; `propose_settings_package` does not create or replace those protected kinds. Link an approved change back to the lesson and retain that link after rollback.
