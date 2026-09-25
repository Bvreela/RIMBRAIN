# BVRimAgent

A provider-neutral AI framework that plans, decomposes goals into tasks, cycles
attention, chooses from bounded decision matrices, and learns through reviewed
evidence — driving RimWorld through the
[RimBridge](https://github.com/zorrobyte/rimbridge) mod.

## Layout

- `components/` — runtime, contracts, rimbrain (packs/policy), dashboard, lab,
  steward.
- `specs/` — foundation, architecture, submodules, contracts, work packages,
  verification, ADRs, and per-feature specs (001–021). See `specs/INDEX.md`.
- `upstream/` — vendored upstream `rimagent` (git submodule).
- `baselines/` — sealed baseline fixtures.

Earlier design artifacts (the `settings/` examples, `ui-mockup/` browser
prototype, `rimworld-jev-plan.html` framework spec, and guide transcript) were
removed from the working tree and remain recoverable in git history; archived
reference material lands under `docs/`.
