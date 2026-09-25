# Implementation Plan: Agent Transparency Views (feature 013)

## Approach

1. **Decision records (FR-1101)** — `Ctx.decisions` list; `run_steps`/`run_rules` append `{tick, poll, source, template, params, ok}` on dispatch. `source` is passed by callers (`phase:<id>` / `rule:<id>`) via a new optional `source` kwarg on both runners.
2. **Views module (FR-1102)** — `runtime/views.py`:
   - `record_decisions(path, rows)` — append canonical JSONL to `state/decisions.jsonl`.
   - `write_planning(state_dir, mode, pack, eval, ledger)` — build ordered goal list from `pack['start']['phases']` (state from ledger tasks, truth from eval/effect check), blockers from latest transition reasons, planner summary from latest `plan.proposed` event if any; write `planning.json` + render `planning.md`.
   - `write_actions(state_dir, rows, window)` — render trailing window as a markdown table to `actions.md`.
   - `write_views(...)` — one call writing both; wrapped in try/except (fail-open, FR-1103).
3. **Wiring (FR-1103)** — `_run_start`, `run_combat`, `run_cycle`, `run_loop` construct `Ctx` with `decisions=[]` + `source` label, then call `views.write_views` after each poll.

## Design notes

- Planning view goal state comes from the task ledger (`start.<phase>` task state) — no new bookkeeping.
- Exit eval is already computed each poll (`mode._exit_eval`); expose it through `mode.last_eval` for the view.
- Actions matrix shows only dispatches (decisions taken); skipped steps are absent by design (SC-1102.2).
- Planner summary: read last `plan.proposed` envelope from `state/events.jsonl` if present; render declared fields only (no CoT).

## Tasks

See `tasks.md` (T163–T166).
