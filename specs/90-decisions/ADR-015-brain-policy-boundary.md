# ADR-015: Brain policy boundary — gameplay strategy lives in packs, runtime provides capability primitives

**Status:** ACCEPTED
**Date:** 2026-09-23
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** Constitution Principle IX; UR-BRN-011..014; specs/012-brain-policy-engine; specs/20-submodules/RIMBRAIN.md, specs/20-submodules/RUNTIME.md

## Context

Features 010–011 shipped working gameplay (start bootstrap, combat test mode, universal pawn rules) by encoding the *strategy* in `startmode.py` / `combatmode.py` / `universal.py`: phase lists and orderings, per-phase dispatch heuristics, exit-condition fields, flee thresholds, idle-job keyword lists, arming logic. That works, but it inverts the project's intent — the brain package is meant to be the human-readable, community-customizable home of gameplay intelligence, while the code is an executor. Every strategy change previously required a code change, a release, and a review of Python rather than YAML.

## Decision drivers

- Community customization: users must be able to reorder, replace, extend, or disable start phases, combat scripts, and universal rules by editing pack files only.
- Long-horizon evolution: policy should improve via data (packs, decision matrices) and model-generated candidates, not code patches.
- One-writer safety: pack-driven execution must still route every game write through the single dispatcher; packs are untrusted data and must never auto-execute arbitrary code.
- Reviewability: pack content is diffable YAML; behavior change = pack diff + hash change, visible in evidence.
- Fail-closed: malformed or unknown policy must refuse, never guess.

## Options considered

### Option A — Keep strategy in code, packs as config knobs

Status quo. Simple, but every strategy change is a code change; packs can only tune what the author parameterized.

### Option B — Full DSL interpreter in the runtime

A Turing-complete pack language. Maximum expressive power, but a new language to spec, sandbox, version, and debug — and Turing-complete packs undermine auditability.

### Option C — Capability-primitive engine + declarative pack sections

The runtime exposes a small, versioned primitive vocabulary — resolvers (`@cfg:`/`@obs:`/`@var:`/`@fn:`), a predicate set, selectors, and a step/rule runner — all executed against the existing dispatcher. Packs declare `start.phases[]` (steps + effect predicates), `start.exit.conditions{}`, `universal.rules[]` (for_each/when/try/cooldown), and a `combat` script (setup/spawn/engage/until/cleanup). No arbitrary code executes; unknown refs fail closed.

## Decision

**Option C.** `runtime/policy.py` is the sole interpreter; `startmode`/`combatmode`/`universal` become thin pack-driven interpreters over it. `policy_version` in `pack.schema.json` versions the primitive vocabulary so packs declare compatibility. All dispatched writes carry the existing pack hash/evidence; `validate_policy` runs at pack load and rejects unknown functions, selectors, ops, or template ids.

## Consequences

### Positive

- Any shipped behavior can be redefined, reordered, extended, or disabled from YAML — verified by tests that mutate the pack and observe changed behavior (SC-1001..1003).
- A second pack (or a model-proposed candidate pack) is a pure data artifact — the self-improvement loop can propose and quarantine policy without touching code.
- The runtime's gameplay surface shrinks to: dispatcher, resolvers, predicates, selectors, step/rule runner, and the capability `@fn:` implementations.

### Negative

- Capability `@fn:` implementations (site ranking, fertility sampling, arm matching, loose-item counting) are still code — but they are generic capabilities, not decisions; packs choose which to call and how to combine them.
- The primitive vocabulary must grow (a versioned change) when a pack needs a capability that doesn't exist — that's deliberate friction, not a bug.

## Compatibility and migration

- `start-mode-v0.yaml` is the canonical declaration of current behavior; the 010/011 code paths were deleted, not wrapped.
- `StartMode`/`observe_start`/`run_start` and `run_combat`/`run_cycle` keep their signatures for test compatibility; internals are pack-driven.
- `policy_version: 1` is the first vocabulary; additions bump the minor, removals/restrictions bump the major.

## Revisit/kill criteria

- If packs routinely need escape hatches beyond declarative rules, reconsider a constrained expression layer — never arbitrary code.
- If capability `@fn:` count balloons, consider moving composition into a typed decision-matrix format instead of more named functions.
