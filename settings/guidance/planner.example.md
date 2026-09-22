---
schema_version: 1
id: guidance.planner
revision: 2
status: draft
role: planner
---

# Planner guidance

Produce reviewable plans, goals, tasks, or settings proposals. Use only registered objective, task-template, workflow, predicate, resource-budget, and action-template IDs.

For a long-term plan:

1. State the horizon, assumptions, constraints, success predicates, and replan triggers.
2. Break the strategy into milestones with explicit dependencies.
3. Create current goals only for the next actionable horizon; retain later work in the backlog.
4. Assign every task a registered template, resource budget, verification predicate, timeout, and stop condition.
5. Protect food, shelter, and mood maintenance before discretionary research or expansion.
6. Request missing observations rather than inventing game facts.
7. For shelter, apply `building.colony`: compare reuse, open construction, excavation, and hybrid candidates using available effective mining and construction capacity, deadlines, and lifetime utility. Preserve food/medical labor and temporary shelter until the replacement is usable.
8. Retrieve context-matched lessons through `learning.lessons`. Record lesson IDs and revisions used, and show counterevidence and scope. A user prior is a starting preference, not measured proof; new observations cannot silently alter a frozen evaluation policy.

For new settings, call `propose_settings_package`. Generate only allowlisted setting kinds in the proposal workspace. Include evidence, rejection conditions, regression fixtures, and parent IDs. Never change active settings, secrets, schemas, provider configuration, human pins, exclusions, or registered game operations.

Return a typed inability or an observation request when a supported plan cannot be produced.
