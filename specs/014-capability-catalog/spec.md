# Feature Specification: Capability Catalog — Complete, Audited Mechanic Coverage

**Feature Branch**: `014-capability-catalog`

**Created**: 2026-09-23

**Status**: Draft

**Input**: The capability-primitive engine must be continuously expanded to cover every action, mechanic, and interaction discovered during live testing and documented in RimWorld, using structured knowledge from authoritative sources (e.g. the RimWorld Wiki) so the agent has access to the full option range available to human players. All gameplay strategy stays outside the codebase in the brain package; the engine's role is strictly to expose a complete, strategy-agnostic capability catalog. Hardcoding gameplay direction in the engine is an antipattern.

## Purpose

The engine today exposes ~35 fns, ~5 selectors, and ~20 templates — a good spine, but nobody can answer "which game mechanics can't the agent express yet?" There is no inventory mapping the bridge surface (115 RPCs) and RimWorld's mechanic space (wiki-documented: work priorities, zones, growing, taming, trading, quests, research, medical, mood/needs, temperature, power, prisoners, factions, royalty/ideology systems…) to implemented primitives.

This feature adds:

1. **A versioned capability catalog** (`components/rimbrain/capability-catalog.yaml`) — every entry is a capability the engine exposes (`status: implemented`) or a mechanic known-but-not-yet-exposed (`status: gap`). Entries carry bridge methods, domain tags, and authoritative source references (wiki URLs, live-test findings). RimBrain owns the catalog (validated data), contracts owns its schema.
2. **An audit tool** (`tools/capability_audit.py`) — diffs the live `bridge.methods` surface (or the sealed baseline `rpc-inventory.json`) against the catalog: unmapped bridge methods and uncovered domains are reported, never silently absent.
3. **A consistency gate** — runtime tests assert every `implemented` catalog entry resolves to a real template/fn/selector registry member and every registry member appears in the catalog.

Coverage growth is pack-independent: new mechanics add catalog entries + registry primitives, never policy. Strategy remains exclusively in `packs/*.yaml` (ADR-015).

## User Stories *(mandatory)*

### User Story 1 - Audited Capability Inventory (Priority: P1)

A contributor runs `python tools/capability_audit.py` and gets: implemented capabilities, bridge methods with no catalog entry (undiscovered surface), and catalog entries marked `gap` (known mechanics not yet primitive). Against a live bridge (`--live`), drift between the shipped inventory and the real method list is reported.

**Acceptance Scenarios**:

1. **Given** the sealed 115-RPC baseline, **When** the audit runs, **Then** every method is either mapped to a catalog entry or reported as uncovered — nothing is silently skipped.
2. **Given** a live bridge exposing a method absent from the baseline, **When** `--live` runs, **Then** the new method is reported as drift requiring a catalog entry.
3. **Given** a catalog entry with `status: implemented` but no matching registry member, **When** the runtime suite runs, **Then** the consistency test fails.

### User Story 2 - Mechanic Coverage Growth Without Policy (Priority: P1)

Newly discovered mechanics (live testing or wiki research) enter the catalog as `gap` entries with a source citation; when implemented, they become generic primitives (fn/template/selector) and the entry flips to `implemented`. At no point does a capability encode *when* or *why* to act — that is pack data.

**Acceptance Scenarios**:

1. **Given** a wiki-documented mechanic with no primitive (e.g. caravan formation), **When** catalogued, **Then** the entry is `status: gap` with the wiki source — the audit reports it as a known gap, not an error.
2. **Given** a new primitive added to `policy.py` registries, **When** tests run, **Then** the suite fails until the catalog gains a matching `implemented` entry.
3. **Given** any catalog entry, **When** reviewed, **Then** it contains no when/threshold/priority fields — policy content in the catalog fails schema validation.

### User Story 3 - Wiki-Seeded Domain Map (Priority: P1)

The catalog seeds `domains` covering RimWorld's documented mechanic space (construction, work/jobs, combat, health/medical, needs/mood, food/cooking, growing, animals, trade, research, quests/incidents, prisoners, factions/social, temperature/environment, power, apparel/equipment, storage/zones, transport/caravans, royalty, ideology), each citing its wiki root, so coverage gaps are visible by domain, not just by method.

**Acceptance Scenarios**:

1. **Given** the domain list, **When** the audit reports, **Then** coverage percentages are broken down per domain.
2. **Given** a domain with zero `implemented` entries, **When** audited, **Then** it is listed as an uncovered domain.

## Requirements *(mandatory)*

- **FR-1201**: `components/rimbrain/capability-catalog.yaml` — versioned, schema-validated entries `{id, kind: template|fn|selector|domain, bridge_methods[], domains[], status: implemented|gap, sources[], notes}`. No policy fields (when/threshold/priority) permitted.
- **FR-1202**: `components/contracts/schemas/rimbrain/capability-catalog.schema.json` validates the catalog; corpus gains valid + invalid examples.
- **FR-1203**: `tools/capability_audit.py` — default reads `baselines/upstream-85cb050/rpc-inventory.json`; `--live` queries `bridge.methods`; reports unmapped methods, gap entries, per-domain coverage; nonzero exit on unmapped baseline methods unless `--allow-gaps`.
- **FR-1204**: Runtime suite asserts bidirectional consistency: every `implemented` entry resolves to a registry member (template/fn/selector) and every public registry member is catalogued.
- **FR-1205**: Catalog and audit live outside the runtime policy path — packs may *reference* capability ids in comments, but behavior never depends on the catalog (data about capabilities, not policy).

## Success Criteria *(mandatory)*

- **SC-1201**: `capability_audit.py` on the sealed baseline exits nonzero listing every unmapped method; after catalog seeding, exits 0 with only declared `gap`s.
- **SC-1202**: Adding a registry fn without a catalog entry fails the suite; adding a `gap` entry passes.
- **SC-1203**: Live `--live` audit against the running bridge reports drift accurately.
- **SC-1204**: Corpus validates catalog examples; suite/corpus/validators green.
- **SC-1205**: Catalog contains zero policy fields — verified by schema `additionalProperties: false` + a test scanning for forbidden keys.
