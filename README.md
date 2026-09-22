# BVRimAgent

Project artifacts for a provider-neutral AI framework that plans, decomposes goals
into tasks, cycles attention, chooses from bounded decision matrices, and learns
through reviewed evidence.

This standalone repository contains the RimWorld project artifacts originally
developed in wolf. Runtime integration will build on
[RimAgent](https://github.com/zorrobyte/rimagent).

## Start here

- [Framework specification](rimworld-jev-plan.html) — architecture, human review,
  decision matrices, learning, evaluation, and rollout.
- [Interactive UI mockup](ui-mockup/index.html) — prototype dashboard with a
  schematic map, shelter choices, tasks, lesson review, and simulated controls.
  [Run instructions and game/agent architecture](ui-mockup/README.md).
- [Settings examples](settings/README.md) — human-editable settings, long-term
  plans, action workflows, building strategy, and lessons policy.
- [RimWorld guide transcript](rimworld-complete-guide-transcript.txt) — original
  reference material supplied for this project.

The domain order is **food → shelter → mood → research → combat**, with emergencies
able to interrupt. Planner and Decision Selector endpoints are independently
configurable. Building strategy accounts for effective available pawn capacity,
and persistent lessons preserve applicability, evidence, and counterexamples.

**Status:** specification, example settings, and an interactive browser mockup.
The RimAgent integration, spatial planner, runtime settings loader, lesson ledger,
and gameplay evaluation have not been implemented. Mockup data is illustrative.
