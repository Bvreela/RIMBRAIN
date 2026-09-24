# Research: Live-Run Pack Mutation

All decisions resolved from codebase evidence + operator answers; no open NEEDS CLARIFICATION.

## Decision 1 — Promotion timing: next-run boundary, not mid-run

**Chosen**: candidates promote only at next run start, before `load_pack` (`mutate.boundary`).

**Evidence**: `dispatch.py:202` — `templates.pack_drift` re-hashes the active pack file on every dispatch; an in-place mid-run write freezes the run (`dispatch.pack_drift`). The brain-reset channel (`brain.py`, `--live-brain`) could swap to a new pack id mid-run, but it tombstones every `start.`/`govern.`/`combat.` task — a heavy reinit per mutation, and operator chose boundary semantics regardless.

**Alternatives rejected**: mid-run brain-reset swap (resets all goal state; drift-free but disruptive); in-place atomic write + immediate reload (one torn write away from a dead run).

## Decision 2 — Mutation op vocabulary: unified full-pack engine

**Chosen**: `packmut.py` with ops `{set, append, remove, upsert}` addressed by dotted paths where a path segment matching a list element's `id` field descends into it (`govern.goals.maintain-storage.retry_polls`). `upsert` requires `id` in the payload — covers add/edit of templates, govern goals, universal/emergency rules, decision_map entries, steps.

**Evidence**: `improve._apply_ops` (`set_cfg`/`append`/`drop_template`/`drop_rule`) walks dicts only — cannot reach `govern.goals[i]`; `planloop._apply_mutations` covers `add_template`/`edit_decision_map`/`add_emergency` only. One engine subsumes both; `improve.py` refactors onto it (existing tests pin behavior).

**Alternatives rejected**: cfg-only ops (operator chose full pack); reusing both engines side-by-side (two vocabularies for the model to confuse).

## Decision 3 — Trigger detection: event-window fold, pack-configured

**Chosen**: each poll, `mutate.check_triggers` inspects (a) the run's event stream via a ring buffer wrapped on the sink, and (b) `improve.diagnose` over the window. Terminal transitions count toward `goals_per_pass` (default 10); `failed`/`expired` fire `on_failure`; `requeued`, escalate dispatches, `action.refused` bursts, and defect-pattern hits fire `near_failure`. `cooldown_polls` + `max_passes_per_run` bound the loop. All thresholds are `mutate:` pack data (Principle IX).

**Evidence**: `startmode._run_start` already threads a sink through dispatcher + ledger; a wrap captures every envelope with zero plumbing changes. `improve.diagnose` is a pure fold — free to reuse.

**Alternatives rejected**: polling `tasks.jsonl` from disk (the sink ring is already in-process); new dedicated near-failure events (existing transition reasons already carry it).

## Decision 4 — Model role: `rimbrain.improve`, rules-only terminal fallback

**Chosen**: new binding `rimbrain.improve` → OpenRouter nemotron primary, `gemini flash-lite` degraded, `rules-only` sentinel terminal. On `rules-only` the pass runs `improve.diagnose` over the window and applies the first matching pack-declared remediation ops — mutation still happens with no model (Principle I).

**Evidence**: `bindings.resolve_role` already walks degraded hops to a sentinel; `planning._fallback` is the established terminal-sentinel pattern.

## Decision 5 — The gate: contract → applicability → full pack validation

**Chosen**: model output must parse `mutation.schema.json`, `base_revision` must equal the active hash, ops must be non-vacuous, and the mutated document must pass `templates.validate_pack` + `policy.validate_policy` + sealed-inventory method check + fair-class check. Failures → `mutation.rejected` with violations.

**Evidence**: `review.deterministic_check` + `planloop._materialize_candidate` established this exact shape; `load_pack` composes the same checks.

## Decision 6 — Auto-revert: lineage + episode-metrics regression

**Chosen**: promotion records `{candidate_hash, parent_hash, parent_path, baseline_score}`; parent file backed up under `packs/candidates/parent-<pack>-<hash8>.yaml`. At the next boundary, `improve.score` over events emitted *after* the `mutation.promoted` event vs `baseline_score`; strictly worse → restore parent file + `mutation.reverted`.

**Evidence**: `score()` (refusal/verify-failure/completion weights) is the existing badness metric; `state/mutations.jsonl` append-only rows give the durable lineage.

**Alternatives rejected**: in-run regression revert (would need mid-run pack writes — violates Decision 1); no-revert manual rollback (operator chose auto).

## Decision 7 — Pack layout: folder-first resolution

**Chosen**: all mutation file I/O resolves targets through `templates.pack_path(pack_id)` — canonical `<id>/pack.yaml` folder form, flat `<id>.yaml` fallback (kept for `candidates/`). Candidates stay flat files under `packs/candidates/`; the boundary install writes the resolved target path, so `start-mode-v0` lands at `start-mode-v0/pack.yaml`. Parent backups are flat `candidates/parent-<id>-<hash8>.yaml`.

**Evidence**: the pack library migrated to folder packs (`start-mode-v0/pack.yaml` etc.) with `pack_path`/`list_packs` resolving both forms; `improve.py` already promotes to `candidates/<id>/pack.yaml` folder form — flat is the candidate convention, folder the promoted convention.

## Decision 8 — Wiring points

- `loop.main`: `--live-mutate` flag; when set, `mutate.boundary(pack_id, …)` runs **before** `dispatcher.load_pack` in the `start`/`live` branches; `mutate.PassState` handed to `run_start`.
- `startmode._run_start`: after `mode.step()` each poll — `pass_state.note_events(new envelopes)` then `mutate.maybe_trigger(...)`. Never blocks on model failure; a pass failure records an event and the run continues.
- `rimbrain.py`: default `run` args gain `--live-mutate`.
- `views.py`: `planning.json` `mutation` block from `PassState` (last trigger, passes run, pending candidate, last verdict).
