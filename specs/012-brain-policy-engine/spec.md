# Feature Specification: Brain Policy Engine — All Gameplay Policy in Packs

**Feature Branch**: `012-brain-policy-engine`

**Created**: 2026-09-23

**Status**: Draft

**Input**: Prime directive (Constitution Principle IX; UR-BRN-011..014) — all gameplay strategy, tactics, priorities, and decision logic (Start Mode, combat behavior, work scheduling, resource flow, long-horizon planning) must live entirely in the external, human-configurable brain package. Code provides flexible capability-based primitives that execute any strategy the brain files define. Hardcoding how the colony starts, fights, or prioritizes is an antipattern; a pack must be able to redefine, reorder, extend, or disable any executed behavior without code changes.

## Purpose

Today `startmode.py`, `combatmode.py`, and `universal.py` embed the policy they execute: the phase list and order, per-phase dispatch heuristics (placement arithmetic, stuff choice, skill-ranked arming, meal-count formula), exit conditions, combat round orchestration, idle-job keywords, and chase/strip thresholds are all Python. A user cannot reorder phases, change exit criteria, swap combat doctrine, or alter idle policy without editing source.

This feature extracts a small **policy engine** (`runtime/policy.py`) exposing three capability primitive families, and moves every gameplay decision into pack data:

1. **Resolvers** — `@cfg:path`, `@obs:path`, `@var:name`, and `@fn:name(args)` capability functions (geometry, counts, id lists, skill-ranked picks, fertility scan, stuff availability, hostile-faction lookup). Pure observation/math — no policy.
2. **Predicates** — `{field, op, value}` with `all/any/not` combinators over resolved values. Used for phase effects, step `when` guards, rule `when` gates, and exit conditions.
3. **Steps & rules** — `steps: [{template, params, when?, for_each?, cooldown_polls?}]` execute ordered writes through the single dispatcher; `rules: [{id, for_each, when, try[], cooldown}]` are per-poll invariant enforcement (idle correction, chase, strip) with `try` ordered alternatives.

Modes become interpreters: start mode iterates the pack's `start.phases[]`; combat runs the pack's `combat` script (setup → per-round spawn → engage rule-loop → cleanup); universal rules iterate the pack's `universal.rules[]`. Deleting a phase from the pack removes it from the game; reordering the list reorders execution; editing any condition changes behavior — no code touched.

## User Stories *(mandatory)*

### User Story 1 - Pack-Authored Start Sequence (Priority: P1)

A pack declares `start.phases` as an ordered list of `{id, effect, steps}` objects. The runtime interprets them generically: propose → check effect against observed state → run declared steps → verify. A community member can write a totally different start (e.g. "dig into a mountain first, buy food from traders") by writing YAML alone.

**Acceptance Scenarios**:

1. **Given** a pack whose `start.phases` omits `recreation`, **When** start mode runs, **Then** no recreation build is dispatched and `start.completed` never requires it.
2. **Given** a pack with phases in a different order (meals before beds), **When** start mode runs, **Then** dispatch order follows the pack order.
3. **Given** a phase whose `effect` predicate already holds, **When** the interpreter reaches it, **Then** it is skipped with zero writes (established-colony resume still works).

### User Story 2 - Declarative Universal Rules (Priority: P1)

`universal.rules[]` in the pack define invariants: each rule declares a selector (`for_each`), a `when` predicate, ordered `try` actions, and a cooldown. The engine evaluates them identically in every mode. Idle correction, downed-hostile exclusion, flee-chase, and strip sweeps are pack entries, not functions.

**Acceptance Scenarios**:

1. **Given** a pack with no `idle-work` rule, **When** a colonist idles, **Then** the runtime takes no corrective action (the pack opted out).
2. **Given** a pack whose idle rule's first `try` targets mines instead of trees, **When** a colonist idles, **Then** the mining job is attempted first.
3. **Given** a rule's cooldown, **When** its action was just dispatched, **Then** the engine suppresses re-dispatch until the cooldown elapses.

### User Story 3 - Combat as Pack Script (Priority: P1)

`combat` config declares checkpoint handling, per-round spawn steps, an engage rule-loop (`until` predicate + tick/spawn budgets + rule list), and cleanup steps (strip, heal, undraft, restore). Verdict accounting is engine bookkeeping; every game-write decision is pack data.

**Acceptance Scenarios**:

1. **Given** a pack with `spawn_mode: incident` steps instead of pawn spawns, **When** combat runs, **Then** the declared spawn steps execute verbatim.
2. **Given** a pack whose engage `until` predicate counts only `living` hostiles (downed excluded), **When** all hostiles are downed, **Then** the round ends `cleared`.
3. **Given** a pack without a strip step, **When** combat ends, **Then** no strip designations are issued.

### User Story 4 - Capability Primitives Are Policy-Free (Priority: P1)

The resolver function library contains only generic mechanics: geometry (`cell`, `rect`, `near`), collections (`ids`, `first`, `count`, `filter`), arithmetic (`add`, `sub`, `mul`, `fdiv`), selectors (`colonists`, `hostiles`, `idle`, `unarmed`, `fleeing`, `downed`), lookups (`map_find_id`, `anchor`, `stuff`, `fertile`, `best_skill`, `arm_match`, `hostile_faction`, `loose_items`). Every numeric threshold, ordering, and preference list is pack data.

**Acceptance Scenarios**:

1. **Given** the function registry, **When** audited, **Then** no function hardcodes a RimWorld def name, phase id, threshold, or ordering — all come from arguments.
2. **Given** a pack referencing an unknown `@fn:` or selector, **When** the pack loads, **Then** validation fails closed with a named unknown-capability error.

## Requirements

- **FR-1001** `runtime/policy.py`: resolver (`@cfg:`/`@obs:`/`@var:`/`@fn:` nested), predicate evaluator (`eq/ne/gt/gte/lt/lte/in/not_in/empty/not_empty/truthy/falsy/contains/contains_any/matches` + `all/any/not`), step runner (`when`/`for_each`/`cooldown_polls`/`optional`), rule runner (`for_each`/`when`/`try`/`cooldown`). All writes via the dispatcher; every resolver fail-closed (unknown ref → error, never guessed).
- **FR-1002** Pack schema gains `start.phases[]`, `start.exit.conditions{}`, `universal.rules[]`, `universal.selectors`/`idle_patterns`, and the `combat` script shape (`setup`/`spawn`/`engage`/`cleanup`); `pack.schema.json` documents the primitive vocabulary version (`policy_version`).
- **FR-1003** `startmode.py`: `StartMode.step` iterates `cfg["phases"]` generically — propose task with declared `effect`, check via predicate evaluator, dispatch via `run_steps`, verify. `rank_site`, fertility sampling, stuff picking, and arm matching are `@fn:` capabilities invoked from pack params, not phase logic. `observe_start` keeps producing measured obs fields (capability metrics, pack-selected via `observe` config).
- **FR-1004** `combatmode.py`: executes `combat.setup` steps once, then per round `combat.spawn` steps → engage rule-loop (`until` predicate, `tick_budget`, `spawn_grace`, rule refs) → `combat.cleanup` steps. Round/verdict/casualty accounting is engine bookkeeping only.
- **FR-1005** `universal.py`: becomes `apply_rules(dispatcher, game, obs, pack_rules, ctx, state)` — thin wrapper over the rule runner; no rule content in code.
- **FR-1006** The shipped `start-mode-v0` pack expresses the complete current policy declaratively: 13 start phases, idle/arm/chase/strip rules, combat script, exit conditions — behavior-identical to the 011 implementation.
- **FR-1007** Pack validation fails closed on unknown `@fn:`, selector, op, template id, or a phase with no `effect`; the primitive vocabulary is versioned (`policy_version: 1`).

## Success Criteria

- **SC-1001** Deleting `recreation` phase + exit condition from a test pack changes behavior with zero code edits (test proves it).
- **SC-1002** Reordering pack phases changes dispatch order (test proves it).
- **SC-1003** A pack with no idle rule leaves an idle colonist uncorrected (test proves it).
- **SC-1004** Full suite + corpus + validators green; pack validates against the new schema.
- **SC-1005** Live: start mode still completes on the real colony driven entirely by pack phases; live loop still corrects an idle pawn from pack rules.

## Boundaries / Non-Goals

- The DSL is deliberately small — resolver + predicate + step/rule. No loops, no macros, no embedded code. Community packs remain untrusted data (UR-BRN-008): they cannot name arbitrary RPCs, only declared templates.
- `observe` field computation (rooms, zones, stocks, beds) stays code — measuring the world is a capability, not policy; which measurements feed conditions is pack data.
- Verdicts, evidence envelopes, ledger mechanics, checkpoint plumbing stay code — bookkeeping, not strategy.
- Planner/selector model routing is untouched; this feature governs the deterministic tier.

## Assumptions

- Every game write a pack can express routes through a declared template id; the template inventory is the pack's action vocabulary (already true).
- Rule evaluation per poll stays O(rules × candidates); selectors bound their candidate sets.
- Packs that need capabilities the engine lacks must request a new primitive via a spec change — never smuggle policy as params.
