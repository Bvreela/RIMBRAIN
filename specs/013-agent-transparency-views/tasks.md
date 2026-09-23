# Tasks: Agent Transparency Views (feature 013)

- [x] T163 `policy.py`: `Ctx.decisions` sink + `source` kwarg on `run_steps`/`run_rules`; dispatch rows `{tick, poll, source, template, params, ok}` (FR-1101)
- [x] T164 `views.py`: `record_decisions`, `write_planning`, `write_actions`, `write_views` (fail-open); `StartMode.last_eval` exposure (FR-1102, FR-1104, FR-1105)
- [x] T165 Wire views into `_run_start`, `run_combat`, `run_cycle`, `run_loop` per poll (FR-1103)
- [x] T166 Tests: sim run emits both views, pack reorder changes goal order, decision rows carry pack-traceable sources, render failure doesn't abort; live run confirms real stamps (SC-1101..1105); docs (README, INDEX, TRACEABILITY)
