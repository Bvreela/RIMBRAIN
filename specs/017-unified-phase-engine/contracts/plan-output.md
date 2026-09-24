# Contract: Planner short-term plan

**Feature**: 017 | **Producer**: `rimbrain.plan` endpoint | **Consumer**: plan gate → active plan → `select.py` priority scoring

## Triggers (pack `decide.plan`)

- `cadence_s` (default 150) — wall-clock since last accepted plan.
- `on_phase_boundary: true` — phase complete/entry.
- `on_events: [raid_letter, phase_blocked_N, ...]` — declared major events.

## Input digest

Compact projection of canonical observation + ledger stats: colony vitals, stocks, threats, phase status, standing-goal holds/fails, recent decision/fallback counts, current plan id. Bounded — same digest machinery feeds `evolve` reflection digests.

## Accepted output shape

```yaml
plan:
  goal_order: [goal_id, ...]        # priority feed into ActionList scoring
  activate:   [goal_id, ...]        # standing goals switched on
  deactivate: [goal_id, ...]        # standing goals switched off
  promote:                         # catalog consumption
    - option: <goal_options id>
      as: {goal|phase}
      params: {...}
  horizon: "<short text>"
```

## Gate (deterministic, decisive)

Reject (prior plan stays) if any:
- references a goal/option id not present in pack `standing_goals`/`goal_options`/`phases`;
- `promote.params` fail the option's declared param schema;
- violates fair-class (dev surfaces);
- fails `templates.validate_pack`-equivalent structural checks on materialized goals.

## Semantics

- `goal_order` re-scores ActionList priorities; unlisted goals keep pack order after listed ones.
- `promote` materializes catalog entries into the run's goal set (and, for `as: phase`, appends a phase) — runtime structures only; mutating the pack file itself still goes through `evolve`.
- A plan is **in force until superseded**; there is always exactly one active plan (possibly the pack default).
