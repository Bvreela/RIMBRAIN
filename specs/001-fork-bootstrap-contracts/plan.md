# Implementation Plan: Fork Bootstrap and Contract Foundation

**Branch**: `001-fork-bootstrap-contracts` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-fork-bootstrap-contracts/spec.md`

## Summary

Bootstrap RimBrainAgent as an evolving fork of upstream RimAgent (`85cb050`, nested RimBridge
`3c1e4c7`): stand up the component layout and per-component validation shells over the pinned upstream
code, capture an immutable baseline bundle, and land the shared contract layer — JSON Schema
primitives (ID, revision, freshness, error), the canonical event envelope with a complete mapping of
the upstream `bus.py` 17-kind stream, and an offline fixture harness. No gameplay behavior changes;
upstream code remains the working baseline throughout.

## Technical Context

**Language/Version**: Python 3.12+ (`uv`) for contracts tooling, harness, and runtime consumer;
C#/.NET (RimWorld 1.6 target) for upstream mods — read-only this feature

**Primary Dependencies**: JSON Schema 2020-12 as contract source of truth; `jsonschema` (Python) for
validation; canonical JSON (JCS, RFC 8785) for hashing; PyYAML for manifests — extends the existing
upstream `agent/` dependency set (pydantic, pyyaml, pytest)

**Storage**: Flat files only — JSONL canonical records, YAML manifests, hashed fixture packages; no
database (per `specs/30-contracts/DATA-OWNERSHIP.md`)

**Testing**: `uv run pytest -q` (Python, corpus + property tests); `dotnet test` (upstream
`mod/Tests`, `mod-steward/Tests` — must pass unmodified)

**Target Platform**: Windows 11 dev environment; loopback-only; CI shells committed but inactive
until component remotes exist

**Project Type**: multi-component development platform / agent fork infrastructure

**Performance Goals**: baseline integrity scan < 60 s (SC-006); fixture replay deterministic and
offline; corpus validation of hundreds of examples in seconds

**Constraints**: no live game, model endpoint, or non-source-control network required; upstream tree
is read-only; `.gitmodules` may not use local filesystem URLs; secrets never enter schemas, fixtures,
or manifests

**Scale/Scope**: 7 component locations, 115 upstream RPC methods to inventory (97 RimBridge + 18
Steward), 18 upstream bus kinds to map, ~30 initial schemas from the CONTRACTS required list
(common → events → runtime core subset per increment C0–C1)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| I. Deterministic before probabilistic | PASS | Feature is pure infrastructure; no model in any path |
| II. One writer, bounded model authority | PASS | No game writes in scope; upstream baseline untouched |
| III. Spec-first (NON-NEGOTIABLE) | PASS | This plan derives from spec 001; all artifacts carry requirement IDs traceable to FR-001..015 and WP-000..002 |
| IV. Explicit compatibility | PASS | Schema `schema_version` on every contract; submodule pins exact; consumers reject unknown newer revisions (FR-006) |
| V. Immutable evidence, revisable policy | PASS | Canonical records append-only JSONL; baseline bundle immutable; fixtures content-hashed |
| VI. Granular qualification, staged promotion | PASS | Fixture harness IS the replay-before-live machinery (P11) |
| VII. Build for diagnosis | PASS | Canonical envelope carries causality/revision/provenance; baseline bundle makes migration diffs reviewable |
| VIII. Migration escape hatch | PASS | Upstream legacy mode preserved intact; baseline bundle captures it as the reference |

No violations. No complexity-tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-fork-bootstrap-contracts/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output: primitive + envelope + fixture + baseline contracts
└── checklists/
    └── requirements.md  # From /speckit-specify
```

### Source Code (repository root)

```text
upstream/rimagent/                 # PINNED READ-ONLY baseline (submodule @ 85cb050, nested mod @ 3c1e4c7)

components/
├── contracts/                     # rimbrainagent-contracts (in-repo until remote exists)
│   ├── schemas/{common,events,runtime}/   # JSON Schema 2020-12, increment C0–C1 scope
│   ├── examples/{valid,invalid}/          # shared corpus
│   ├── compatibility/{VERSIONING.md,MIGRATIONS.md}
│   └── tests/                             # corpus + property + canonicalization tests
├── runtime/                       # rimbrainagent-runtime: fork root for agent/ migration
│   └── (validation shell + upstream-parity harness; no framework code yet)
├── rimbrain/  steward/  lab/  dashboard/  # validation shells only this feature
integrations/rimbridge/            # direct-bridge integration placeholder (upstream nested copy is source)

tests/
├── contract/                      # superproject corpus runner (consumes components/contracts corpus)
├── fixtures/                      # fixture packages (seeded from synthesized upstream corpus)
└── acceptance/                    # SC-001..007 verification scripts

.specify/                          # spec-kit infra (constitution, templates, scripts)
baselines/upstream-85cb050/        # generated baseline bundle output (gitignored artifacts except manifest)
```

**Structure Decision**: In-repo component directories with committed validation shells, promoted to
pinned Git submodules only when portable remotes exist (AGENTS.md forbids local `.gitmodules` URLs).
`upstream/rimagent` stays a read-only submodule — migration copies/adapts files into `components/`
per `specs/40-work-packages/UPSTREAM-MIGRATION.md`; nothing is edited inside `upstream/`.

## Complexity Tracking

No constitution violations — table omitted.
