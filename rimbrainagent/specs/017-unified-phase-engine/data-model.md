# Data Model: Unified Phase Engine

**Date**: 2026-09-24 | **Feature**: 017

## Entities

### Phase

Ordered lifecycle unit declared in `pack.phases[]`.

| Field | Type | Notes |
|---|---|---|
| `id` | string, unique | `init` reserved for the prescriptive bootstrap |
| `prescriptive` | bool | `true` → deterministic `steps`; `false` → `goals` + `action_list` |
| `when` | predicate | entry gate (default: previous phase complete) |
| `complete` | predicate | phase exit contract (init carries today's `exit` + fix chains) |
| `steps` | list | prescriptive ordered steps with `effect`/`need`/`requires`/`resources` |
| `goals` | list | goal specs identical to standing-goal shape |
| `action_list` | object | `{scope, max_items≤20, priority: expr, fallback: expr}` |
| `on_enter`/`on_exit` | ops | optional hooks |

**Transitions**: `pending → active → complete`; a `complete` phase never re-enters except via pack-declared `repeat`/`rearm` (same as today's effect-lapse re-arm semantics on goals).

### StandingGoal

Today's `govern.goals`, unchanged semantics: `id`, `when`, `effect`, `steps`, `resources`, `retry_polls`. Evaluated every poll in declared order, independent of active phase; re-arms on effect lapse.

### ActionList (per-poll, ephemeral)

| Field | Type |
|---|---|
| `candidates` | ≤20 `{id, scope: colony|pawn, label, dispatch: {template, params}, priority: float, source: goal_id|rule_id}` |
| `question` | systemone payload — `q.colony` + `q.pawn.<id>` entries |
| `inputs` | stats snapshot embedded in the question (colony stats, pawn rows, efficiency metrics, plan id) |

### Plan (in force until superseded)

| Field | Type |
|---|---|
| `id` / `issued_at` | planner round identity |
| `goal_order` | list of goal ids — priority feed for ActionList scoring |
| `active_goals` | goals switched on/off |
| `promotions` | `goal_options` ids → materialized goals/phases |
| `horizon` | short-term window description |

**Transitions**: `proposed → accepted|rejected(gate) → superseded`. Rejection or planner failure leaves the prior plan active.

### DecisionRecord (append-only, `state/decisions.jsonl`)

`{poll, tick, phase, offered: [...ids], pick, applied, fallback: bool, shadow: bool, inputs_hash, latency_ms}` — the auditability backbone.

### CandidatePack / Lineage

Unchanged from feature 016: gated mutation artifact; `parent_hash` recorded; boundary-only promotion; regression auto-revert.

### RunState (per-run, owned by `runstate.py`)

Consolidates `mode.vars`, `uni_state`, `PassState`, `vstate`. One persistence owner → `state/runstate.json` (replaces `startmode.json`); ledger stays canonical for tasks.

### Observation (per-poll, canonical)

`{tick, colony{...}, pawns[...], map{...}, stocks{...}, vitals{...}, threats{...}}` — one producer (`observe.py`), all stages consume sections. Merges `observe_start`, `planloop.enrich`, `vitals.sample`.

## Validation rules

- `phases` non-empty; exactly one `prescriptive` phase MAY exist and, if present, MUST be first or gated by `when`.
- `action_list.max_items` ≤ 20 (hard bound — engine rejects higher).
- `init.complete` (or equivalent completion predicate) required on the prescriptive phase.
- Every `candidates[].dispatch` resolves to a pack template with schema-valid params before the list is offered.
- Legacy v0 packs load through the migration map in `contracts/pack-schema-v1.md`; unknown `schema_version > 1` rejected.
