# Tasks: Self-Improvement Loop (009)

**Inputs**: `spec.md`, `plan.md` | **Feature**: `specs/009-self-improvement-loop`

## Phase 1: Contracts (Foundational — blocks all stories)

- [x] T130 [P] Event-type schemas in `components/contracts/schemas/events/types/`: `selfcheck.diagnosed` (defect_class, span {first_seq,last_seq}, remediation, finding_count OR no-op flag), `audit.verdict` (check_id, domain: code|policy|ux, verdict: pass|fail, reasons[]), `improvement.promoted` (candidate_id, pack_hash, episode_boundary, metrics), `improvement.rejected` (candidate_id, gate: metrics|audit|defer, reasons[]), `episode.metrics` (episode_id, refusal_rate, verify_failure_rate, task_completion_rate, ticks_to_baseline, event_span) — matching the `task.transition` schema shape (FR-801/804/807/809)
- [x] T131 [P] Register all five in `components/contracts/registry/event-map.yaml` (native runtime types) + corpus cases in `components/contracts/examples/` (valid + ≥1 invalid each); `corpus_runner` 0 mismatched (FR-809)

## Phase 2: Thought Feed + Metrics (US3 + US5 — pure functions, parallel)

- [x] T132 [US3] `components/runtime/src/runtime/feed.py`: `render_event(env) -> str` deterministic per-type narrative templates (observation/plan.*/action.*/task.transition/selfcheck.*/audit.*/improvement.*/episode.metrics; fallback = structured echo for unknown types); `FeedWriter` appends `## tick N — <type>` entries to `state/feed.md` keyed by event_id; `feed_sink(inner)` wraps an event sink so every emitted event is narrated; write failure recorded, never fatal (FR-805, SC-803)
- [x] T133 [US5] `components/runtime/src/runtime/metrics.py`: `episode_metrics(events) -> dict` pure fold — refusal_rate (action.refused/action.issued), verify_failure_rate (task transitions to failed|expired / tasks terminal), task_completion_rate (succeeded/terminal), ticks_to_baseline (first→last action span), event_span; `emit_metrics(events, sink)` builds the `episode.metrics` envelope; deterministic — same events, same output (FR-807, SC-805)

## Phase 3: Audit Passes (US2)

- [x] T134 [US2] `components/runtime/src/runtime/audit.py`: `audit_code(state_dir) -> verdict` (runtime pytest + corpus + component validators via direct import/subprocess — fail-closed on nonzero); `audit_policy(pack_path) -> verdict` (schema validation, inventory cross-check, invariant scan — dispatcher bypass patterns, model-executed call names, fail-closed preserved); `audit_ux(state_dir) -> verdict` (feed coverage: every decision event has a feed entry; refusal messages non-empty); each emits `audit.verdict` via sink (FR-804, SC-802)

## Phase 4: Improvement Cycle (US1 — the loop)

- [x] T135 [US1] `components/rimbrain/packs/improve-v0.yaml`: cycle config — defect patterns (repeated `action.refused` same template ≥N, task `failed`/`expired` ≥N same kind, `dispatch.params_invalid` recurrences), metrics weights, audit gate list, cadence; all pack-validated (FR-801 config)
- [x] T136 [US1] `components/runtime/src/runtime/improve.py`: `diagnose(events, patterns) -> findings` (pure; emits `selfcheck.diagnosed` or recorded no-op); `propose(findings) -> candidate pack path` (rules-only remediation — e.g. fix a bad param path in a template — materializes under `packs/candidates/`); `validate(candidate, metrics_fn) -> verdict` (candidate metrics ≥ incumbent on replayed evidence); `decide(...)` → `improvement.promoted`/`improvement.rejected` (defer when evidence thin); `run_improve(dispatcher, store, cfg, iterations)` — ledger-durable cycle, bounded, clean stop (FR-801/802/803/808, SC-801/802)
- [x] T137 [US1] `loop.py`/`__main__.py`: `--mode improve` wiring + `--feed` flag composable with any mode (feed sink wraps the event sink); promote applies ONLY at loop start (episode boundary), never mid-run (FR-803/805)

## Phase 5: Customization (US4)

- [x] T138 [US4] `components/rimbrain/CUSTOMIZE.md`: the editable brain surface — pack anatomy (templates/decision_map/emergency/start/improve sections), binding files, every tunable threshold, edit→reload→verify recipe, candidate promotion workflow, plain-language error examples (FR-806, SC-804)

## Phase 6: Tests + Polish

- [x] T139 [P] `tests/test_feed.py` (every decision type renders, fallback echo, coverage 100%, failure non-fatal), `tests/test_metrics.py` (determinism, two histories differ), `tests/test_audit.py` (unsafe pack refused, failing suite blocks), `tests/test_improve.py` (planted-defect trace: diagnose→candidate→validate→decide; thin evidence defers; promote only at boundary) (SC-801..805)
- [x] T140 Polish: INDEX row 009, runtime README self-improvement + feed sections, AGENTS.md phase note, `validate_components` green
- [x] T090a `vitals.py` + `_run_start`: `colony.vitals`/`colony.sickness` canonical events every `vitals.every` polls (mood, downed, dead, illness onsets diffed per pawn) (FR-811)
- [x] T090b `improve.py`: `where` predicates + `window_ticks` in `diagnose`; dict remediations `{ops}` (`set_cfg`/`append`/`drop_template`/`drop_rule`) in `propose` (FR-812/813)
- [x] T090c `improve-v0.yaml`: poor_mood / repeat_sickness (per pawn-year) / multiple_downed / colonist_death failure classes with pack-declared mutations; tests in `test_improve.py` (SC-806)
