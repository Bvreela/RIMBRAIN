# Initial architecture decision records

**Status:** ACCEPTED as design baseline; implementation-specific choices remain open where stated.

## ADR-001 Superproject with pinned component submodules

**Decision:** Use a thin integration superproject and independently versioned Contracts, Runtime, RimBrain, Steward, Lab, Dashboard, and RimBridge repositories. Keep provider/domain packages inside Runtime initially.

**Why:** These seven boundaries have different release/trust/consumer profiles. More fragmentation would slow delivery; less would couple policy, mods, analytics, and UI.

**Consequence:** Portable component remotes are required before placeholder directories become submodules.

## ADR-002 Upstream as read-only baseline submodule

**Decision:** Pin `zorrobyte/rimagent` under `upstream/rimagent`; never implement the fork there.

**Why:** Preserves a reproducible comparison and avoids mixing specifications with accidental upstream edits.

## ADR-003 Legacy and framework controllers coexist

**Decision:** Preserve legacy mode behind an explicit controller boundary while framework mode is independently constructed.

**Why:** Enables matched evaluation and recovery without weakening framework safety through compatibility shortcuts.

## ADR-004 Single process/event loop and one dispatcher

**Decision:** Initial Runtime uses one Python process/async event loop and a single write consumer.

**Why:** Simplest structure that enforces serialization/recovery. Distributed agents are unnecessary.

**Revisit when:** Measured throughput/availability needs cannot be solved within process, with a separate ADR.

## ADR-005 Rules baseline; selector qualifies per row

**Decision:** Rules always ship. Laya is preferred local candidate and Jev optional, but model authority is row/model/renderer qualified.

**Why:** Resolves prior spec conflict and makes selector value falsifiable.

## ADR-006 Provider-neutral strategic model

**Decision:** Planner/reviewer contracts do not depend on GLM/Qwen/vendor. GLM may be a deployment profile.

**Why:** Prevents game/policy coupling to model churn.

## ADR-007 RimBrain is immutable data, not executable code

**Decision:** Packs contain validated YAML/Markdown/JSON fixtures and cannot auto-apply Python.

**Why:** Human/community editability without remote-code trust. Executable extensions follow normal code review/releases.

## ADR-008 Flat-file canonical truth

**Decision:** Schema-versioned JSONL and atomic JSON/YAML snapshots are authoritative; databases/indexes are derived.

**Why:** Local ownership, inspectability, recovery, sharing, and diffability.

## ADR-009 Export is a public interface

**Decision:** Build canonical causal events and structured export as architecture, not post-hoc log scraping.

**Why:** Required for replay, honest learning, external training, and auditing.

## ADR-010 Keep RimBridge generic

**Decision:** Prefer upstream RimBridge and its add-on hooks. Agent strategy stays in Steward/Runtime/RimBrain.

**Why:** Preserves reusable player-parity infrastructure and reduces fork maintenance.

## ADR-011 Extract Steward after contract capture

**Decision:** Steward becomes an independent submodule, but only after golden tests cover current RPC/event behavior.

**Why:** Repository modularity must not cause an unmeasured rewrite/regression.

## ADR-012 Dashboard and Lab use public contracts

**Decision:** Both become independent consumers and cannot import Runtime internals or call live bridge mutations.

**Why:** Enforces modularity and trust boundaries.

## Open decisions requiring separate ADRs before implementation

1. Schema toolchain and generated-binding strategy.
2. Runtime packaging/name and compatibility command strategy.
3. Steward package ID/name migration versus preserving upstream identity.
4. Dashboard implementation framework.
5. Secret backend(s) and remote dashboard authentication profile.
6. Exact local Laya deployment protocol/model revision. **Resolved 2026-09-22 by ADR-014**: native `laya serve` on :8780, `laya_english_q8_0`, OpenRouter `~typesafe/jev-latest` fallback.
7. Planner deployment profiles and cost ceilings.
8. Repository hosting organization, maintainer keys, and signing governance.
9. Exact quantitative kill thresholds and evaluation machine-hour budget.
10. High-impact actions requiring human approval.
