# RimBrainAgent

RimBrainAgent is the specification-first superproject for a modular, local-first RimWorld agent derived from `zorrobyte/rimagent`.

No production implementation has been added yet. This repository currently contains:

- a pinned, read-only upstream baseline at `upstream/rimagent`;
- the planned component/submodule directory layout under `components/`;
- detailed architecture, interface, migration, testing, and work-package specifications under `specs/`;
- reserved deployment, profile, and cross-component test roots.

## Start here

1. [Specification index](specs/INDEX.md)
2. [Unified requirements](specs/00-foundation/UNIFIED-REQUIREMENTS.md)
3. [Upstream baseline audit](specs/00-foundation/UPSTREAM-BASELINE-AUDIT.md)
4. [System architecture](specs/10-architecture/SYSTEM-ARCHITECTURE.md)
5. [Repository topology](specs/10-architecture/REPOSITORY-TOPOLOGY.md)
6. [Implementation work packages](specs/40-work-packages/IMPLEMENTATION-PLAN.md)
7. [Requirements traceability](specs/40-work-packages/TRACEABILITY.md)

## Planned component repositories

| Path | Future repository | Responsibility |
|---|---|---|
| `components/contracts` | `rimbrainagent-contracts` | Schemas, IDs, compatibility, generated bindings |
| `components/runtime` | `rimbrainagent-runtime` | Python orchestrator and legacy-compatible CLI |
| `components/rimbrain` | `rimbrain-core` | Human-readable policy, prompts, workflows, fixtures |
| `components/steward` | `rimbrainagent-steward` | Deterministic RimWorld add-on and standing orders |
| `components/lab` | `rimbrainagent-lab` | Replay, export, benchmark, evaluation, promotion tooling |
| `components/dashboard` | `rimbrainagent-dashboard` | Read-model UI and audited operator controls |
| `integrations/rimbridge` | upstream `rimbridge` | Generic player-parity game bridge, pinned dependency |

These directories are intentionally specification-only placeholders until their remotes are created. Do not place implementation in them before the corresponding Phase 0 repository-bootstrap work package is approved.

## Upstream baseline

`upstream/rimagent` is a Git submodule pinned to the reviewed upstream revision. Its own `mod` nested submodule pins RimBridge. It is evidence and migration input, not the destination for new work.

Initialize after cloning:

```text
git submodule update --init --recursive
```

## Spec-driven workflow

1. Select a work package.
2. Confirm every referenced requirement and contract is `READY`.
3. Add or revise an ADR for architectural changes.
4. Write contract/fixture tests before implementation.
5. Implement only within the owning component.
6. Run component, contract, replay, and acceptance gates.
7. Update traceability and evidence links before declaring completion.

See [AGENTS.md](AGENTS.md) for repository rules.
