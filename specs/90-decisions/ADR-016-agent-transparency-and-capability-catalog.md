# ADR-016: Agent transparency views and strategy-agnostic capability catalog

**Status:** ACCEPTED
**Date:** 2026-09-23
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** UR-VIEW-001..004; UR-BRN-015..017; UR-DAT-004/007; UR-EXP-008; specs/013-agent-transparency-views; specs/014-capability-catalog

## Context

Two gaps followed the policy externalization (ADR-015):

1. **Opacity.** The pack-driven interpreter executes phases and rules, but nothing exposes *what it intends* (goal ordering, exit evaluation, blockers) or *what it just did* (which rule fired, which template, with which params). A user watching a live run sees a game, not an agent.
2. **Unbounded capability surface.** The runtime's capability primitives (`@fn:` resolvers, selectors, templates) grew organically with no inventory. Nobody could answer "what can the agent do?" or "what mechanics are unimplemented?" — and the bridge exposes 115 RPCs with no provenance tracking back to packs.

## Decision drivers

- Views must be **synchronized and real-time**: planning state and tactical decisions from the same poll, not two drifting logs.
- Views are **derived artifacts**: canonical JSONL/JSON stays authoritative; markdown is a disposable render (UR-DAT-007).
- **No private chain-of-thought**: decision surfaces (rule id, predicate, resolved params, outcome) are sufficient; model internals stay out (UR-EXP-008).
- View failure must never break control: **fail-open on render, fail-closed on dispatch**.
- The catalog must distinguish **implemented** primitives from honest **gaps** — coverage claims must be auditable against the live bridge surface, not aspirational.
- Catalog entries carry **what is possible**, never **when/why** — policy fields are schema-rejected (UR-BRN-017).

## Options considered

### Option A — Log scraping / feed.md as the view

The event feed already narrates dispatches. Rejected: the feed is a linear story, not a synchronized two-view projection; goal state, exit evaluation, and per-poll tactical tables need structured inputs, not prose.

### Option B — Push views into the dashboard component only

Rejected: the dashboard is an optional consumer; live runs on headless sessions still need the views. Flat files under `state/` are the lowest common denominator — the dashboard can later render the same canonical records.

### Option C — Canonical decision log + atomic view renders (chosen)

`policy.py` `Ctx` gains a `decisions` sink; every `run_steps`/`run_rules` dispatch appends `{tick, poll, source, template, params, ok}` to `state/decisions.jsonl`. `runtime/views.py` renders `planning.md`/`planning.json` (ordered goals, states, blockers, exit eval) and `actions.md` (bounded recent-decision table) atomically per poll. Setup/spawn/cleanup phases flush through the same cursor so the matrix covers the whole run, not just the engage loop.

For the catalog: a versioned `capability-catalog.yaml` (schema-checked, corpus-tested) where each entry maps a bridge method or capability to inputs/outputs/safety/status (`implemented`|`gap`)/provenance. `tools/capability_audit.py` diffs the baseline RPC inventory against the catalog and exits nonzero on unmapped surface.

## Decision

**Option C.** Views live in `runtime/views.py`, written by each mode interpreter via a shared decisions cursor. The catalog lives in `components/rimbrain/capability-catalog.yaml` — pack-side data, not code — validated by `capability-catalog.schema.json`, audited by `tools/capability_audit.py`, and extended as live testing and authoritative sources (RimWorld Wiki) surface new mechanics.

## Consequences

### Positive

- Any poll's behavior is explainable: `decisions.jsonl` rows carry `source` ids traceable to pack YAML elements (SC-1103).
- Capability coverage is a number, not a vibe: 115/115 baseline methods mapped, 87 documented gaps, audit exit code is the gate (UR-BRN-016).
- New mechanics land as catalog entries + optional `@fn:`/template implementations — no strategy code changes (UR-BRN-015).

### Negative

- Two more artifacts to keep in sync: the catalog drifts if bridge methods change without regeneration — mitigated by the audit tool running in validation.
- The decision sink grows unboundedly within a run; bounded by the actions.md window (canonical log keeps everything, view truncates).

## Compatibility and migration

- `decisions.jsonl` is append-only canonical evidence; `planning.md`/`actions.md`/`planning.json` are disposable renders.
- No pack format change; `source` ids flow from existing phase/rule names.
- Cleanup chain steps are now `optional: true` in the pack so a failed undraft cannot abort checkpoint restore — a pack-level fix, not engine policy.

## Revisit/kill criteria

- If views need sub-poll granularity, move to a streaming writer; the canonical log already supports it.
- If catalog entries need richer mechanics metadata (wiki provenance URLs, review status), extend the schema minor-version — never by embedding policy.
