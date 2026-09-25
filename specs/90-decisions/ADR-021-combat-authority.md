# ADR-021: Combat-writer authority — delegate model with surgical pawn overrides

**Status:** ACCEPTED
**Date:** 2026-09-24
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** FR-1907 (manual-touch interlock), specs/019-combat-capability (contract combat-capability/v0); ADR-015 (policy boundary), ADR-017 (pack classes), ADR-019 (unified phase engine)

## Context

Feature 019 adds fair-class colony defense. Two writers can drive combat:

1. The in-mod Steward `combat` standing order (`Order_Combat`) — a proven
   tick-level state machine: draft → rally spread → hold → overrun →
   hysteresis release → area restore → rescue, with manual-touch cooldowns.
2. Pack-declared rules and `decide.select.pawn_scope` per-pawn options —
   the fastbrain per-pawn fit (skills × gear × enemy composition) the
   feature exists for.

Both writing the same pawns fights the manual-touch interlock: every
pack-issued `ui.draft`/`ui.goto`/`ui.attack` is itself a manual touch that
pauses order control for that pawn ~2500 ticks. Unmediated mixing = thrash.

## Decision drivers

- `Order_Combat` is already correct on the hard parts (rally spread,
  overrun, release hysteresis, area restore, touch bookkeeping); a YAML
  re-implementation doubles the writer-conflict surface for no gain.
- Principle II: one writer — the dispatcher serializes all game writes;
  the order is an *in-mod* executor the pack steers through
  `steward.orders.*`, not a second writer on the bridge surface.
- Principle IX: tactics (engage radii, option vocabulary, priorities) are
  pack data; the order supplies tick-level babysitting only.
- Per-pawn overrides (retreat, relieve, focus-fire, block) are exactly
  what manual touches were designed to protect — the order skips touched
  pawns until the touch expires.
- Order state must be observable (`steward.status`/`steward.orders.explain`
  → `order_state()` fn) so options gate on the order's own lifecycle
  instead of duplicating it.

## Options considered

### Option A — Pack owns everything (`delegate_order: null`)

Rejected for v0: reimplements the order in YAML — draft/undraft, rally
spread, overrun, release hysteresis, area restore, touch bookkeeping —
with every issued command a manual touch that must be self-managed.
Contract keeps `delegate_order: null` as an allowed but unsupported path.

### Option B — Full delegate, no per-pawn options

Rejected: loses the feature's point — compile-time per-pawn fit where
`priority_head` fallback equals the best deterministic assignment.

### Option C — Delegate + surgical overrides (chosen)

The order remains the base executor; the pack steers it
(`steward.orders.set`/`rally`/`run`/`release`), reads `order_state` from
observation, and compiles pawn options as surgical overrides the order
honors via the touch window.

## Decision

**Option C.** Authority split: the steward `combat` order owns
draft/rally/hold/overrun/release tick control; the pack owns *decisions* —
when to enable/release, where to rally, and per-pawn exceptions. Options
are exceptions-first (retreat, relieve, shelter, focus/block), never a
parallel executor. Packs MUST NOT rely on the order honoring an override
it will later re-steer; order state is re-read each poll.

## Consequences

### Positive

- Zero duplicated state machine; release/area-restore/touch semantics stay
  in the proven in-mod code.
- Overrides compose cleanly: a touched pawn is skipped by the order for
  the touch window, so surgical commands stick.
- `order_state` projection keeps pack rules honest — they gate on what the
  order actually did, not what they asked for.
- Fair-class preserved: `steward.orders.*` + `ui.*` are sealed inventory
  methods; no `dev.*` anywhere.

### Negative / risks

- Bridge-surface gaps (`order_state` fields, per-pawn `touched`) degrade
  options fail-closed — null → gates false, unreadable touch → treated as
  touched. The colony still defends via the order; gaps become follow-up
  specs, never in-feature C# scope growth.
- Touch cooldown (~2500t) means an override commits the pawn for ~1 game
  hour; option gates must be conservative about firing.
- The pack could fight the order if it re-issues order-managed writes
  (draft/area) outside the exception set — pack authoring discipline +
  contract guidance mitigate; runtime cannot fully prevent it.

## Verification

`test_combat_capability.py`: classification fixtures, `order_state`
projection, delegate steering through the single writer, touch-exclusion
(fail-closed on gap), release hysteresis, fallback-equality.
