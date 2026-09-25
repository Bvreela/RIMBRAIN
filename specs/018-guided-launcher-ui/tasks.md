# Tasks: Guided Launcher UI

**Input**: Design documents from `/specs/018-guided-launcher-ui/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included per project convention (constitution verification ladder; new logic lands in pure modules with pytest coverage — Tk glue stays thin).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[USn]**: user story from spec.md

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Add optional `"derived_from": {"type": "string"}` to root `properties` of `components/contracts/schemas/runtime/pack.schema.json` (contract `pack-edit-save.md` — additive-only, existing packs still validate)
- [X] T002 [P] Rework `rimbrain.py` arg routing per `contracts/launch-cli.md`: bare/`run` with no args → spawn overlay in setup mode and return; `run -y`/`--yes` (sole arg only, else usage error exit 2) → today's fair-defaults argv; `run <any flags>` → unchanged headless path; export `RIMBRAIN_LOOP_CMD` JSON argv prefix on the overlay child's env (frozen `[exe, "loop"]`, dev `[python, "-m", "runtime", "loop"]`)
- [X] T003 Create `components/dashboard/src/dashboard/paramspec.py` — `PARAM_SPEC` table `{flag,label,kind:check|radio|spin|text|choice,default,group,hint,enable_when,block_when}` covering every `runtime loop` flag (pack, mode{sim,live,start,improve,combat,cycle}, iterations, bridge, live, no-store, ledger, feed, fair/dev, live-brain, live-mutate, no-hold) + `defaults()`/`argv(cfg)`/`violations(cfg)` per `data-model.md`; fair default ON; constraint mirror = loop.main's fail-closed checks verbatim (cycle⇒dev, live-ish modes⇒live, live-mutate⇒mode∈{start,live})

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 [P] Implement role-shaped live probing in `components/runtime/src/runtime/probe.py` per `contracts/probe-live.md`: `probe_live(role, timeout_s=10)` — offline `resolve_role` → call shaped by the role's required capability (`registry.ROLE_REQUIREMENTS`): `typed_decisions`⇒reuse `_decide_probe` (omit `model` for local endpoints if they 422 on it), `chat`⇒POST `{base}/chat/completions` `{model, messages:[{role:"user","content":"ping"}], max_tokens:1}` via `client._post_json`, `embeddings`⇒`openai_compat_embed`-shaped `{model, input:["ping"]}`; `resolved.kind=="fallback"`⇒`fallback_only`; verdicts `answered|model_failed|unreachable|missing_secret|fallback_only|unbound` + `endpoint/model/api/latency_ms/fallbacks(degraded_paths verbatim)/degraded/checked_utc`; 429/5xx ⇒ `retryable:true`
- [X] T005 [P] Expose `probe_live`, `validate_pack_doc`, and `policy_vocabulary` in `components/runtime/src/runtime/api.py` (+`__all__`) per `contracts/probe-live.md` — `validate_pack_doc(doc)` runs the identical `load_pack` sequence (`validate_pack` → `policy.validate_policy` when `policy_version` → sealed-inventory check) as a pure function returning `{ok, issues[]}`; `policy_vocabulary()` returns `{ops, combinators, functions, resolvers}` sourced from `policy.py` (authoritative — dashboard never duplicates the table)
- [X] T006 [P] Create `components/runtime/tests/test_probe_live.py` — verdict matrix with stubbed transports: answered (decide, chat, embeddings shapes), model_failed (endpoint up, call fails), unreachable (TCP fail), missing_secret, fallback_only sentinel, unbound role; verify `max_tokens:1` + minimal decide/embeddings payloads + `fallbacks` passthrough
- [X] T007 Refactor `components/dashboard/src/dashboard/overlay.py` to a stacked-screen shell: `Setup`/`Monitor` frames swapped in one Tk window; existing goals/learning/actions/brain-status widgets move under Monitor unchanged; window close handler terminates any owned child (placeholder Run Handle until T008)
- [X] T008 Implement Run Handle in `components/dashboard/src/dashboard/overlay.py`: `RIMBRAIN_LOOP_CMD` (`json.loads` env, malformed/missing ⇒ GO disabled + label) + assembled flags → `subprocess.Popen`; `proc.poll()` on the existing refresh cadence; status line `running pid N` / `exited code N`; `terminate()` on window close (kill on timeout)

**Checkpoint**: `rimbrain run` opens a two-screen window; GO can spawn a loop child; runtime facade additions tested green.

---

## Phase 3: User Story 1 - Launch screen drives the run (Priority: P1) — MVP

**Goal**: Every startup param a labeled control, fair defaults, fail-closed mirroring, GO spawns the loop and swaps to Monitor.

**Independent Test**: `rimbrain run` → grid shows fair preset; invalid combos blocked with reasons; GO starts a run equivalent to today's default argv; loop exit reported within one refresh.

### Implementation for User Story 1

- [X] T009 [P] [US1] Create `components/dashboard/tests/test_paramspec.py` — `argv()` equals the known default preset; `violations()` flags each mirrored rule (cycle+fair, live-mutate+improve, live-ish without live); defaults match spec FR-003
- [X] T010 [US1] Build the Setup screen in `components/dashboard/src/dashboard/overlay.py` — widget generation from `PARAM_SPEC` (check/radio/spin/text rows grouped Run/Flags), `enable_when` greying, `block_when` violations rendered inline + GO disabled with reason; presets row (Fair run/Sim test/Dev lab) applying table defaults
- [X] T011 [US1] Wire GO in `overlay.py`: assembled argv preview label (verbatim, Principle VII) → Run Handle spawn → swap to Monitor; argv controls become read-only while running ("applies to next run" label)
- [X] T012 [US1] Monitor additions in `overlay.py`: loop status line from Run Handle (`exited code N` within one refresh cycle) + "Setup" button returning to the Setup screen

**Checkpoint**: default GO is byte-equivalent to `rimbrain run -y` argv; US1 acceptance scenarios 1–5 pass.

---

## Phase 4: User Story 2 - Both brains verified live (Priority: P2)

**Goal**: Per-role rows show resolved endpoint+model, live-call verdict + latency, and fallback chain — never blocking the UI or GO.

**Independent Test**: Stub facade results → verdict rendering per row; live Laya/OpenRouter → green answered + latency; kill Laya → unreachable + fallback note.

### Implementation for User Story 2

- [X] T013 [P] [US2] Create `components/dashboard/tests/test_brains.py` — verdict→row mapping (answered/model_failed/unreachable/missing_secret/fallback_only/unbound), fallback-chain display, stubbed `api.probe_live`/`list_bindings`; no Tk, no network
- [X] T014 [US2] Create `components/dashboard/src/dashboard/brains.py` — `ROLES` table (label→role: BIGbrain plan/review/improve, fastbrain select, embed), `check_all(api,on_result)` spawning one `threading.Thread` per role posting `Brain Status` dicts to a `queue.Queue`; pure verdict classifier per `contracts/probe-live.md`; facade import wrapped try/except like `server.py`'s `_RUNTIME_OK` — unimportable runtime ⇒ rows show `runtime unavailable`, never a crash (standalone overlay case)
- [X] T015 [US2] Mount the brains panel in the Setup screen (`overlay.py`) — row per role: status dot → role → `endpoint · model` → verdict/latency → dimmed fallback chain; `queue.Queue` drained on the refresh cadence; auto-check on screen open + manual "Re-check"; GO never blocked

**Checkpoint**: healthy endpoints show `✓ live Nms`; failures show the right verdict + which fallback engages.

---

## Phase 5: User Story 3 - Pack selection with class visibility (Priority: P2)

**Goal**: Pack list with class badges + lineage, fair-mode gating, launch-time and mid-run selection.

**Independent Test**: packs dir with fair+dev packs → list, badges, gating; mid-run pick posts the same reset request as today's Use.

### Implementation for User Story 3

- [X] T016 [US3] Add pack descriptors to the Setup screen (`overlay.py` + `packedit.py` helper): extend `scan_packs` output with `class`/`pack_id`/`derived_from` parsed from each discovered pack file (folder `pack.yaml` or flat `<id>.yaml`; fail-open defaults `fair`); radio list w/ `[fair]`/`[dev]` badges + `(from <derived_from>)` lineage
- [X] T017 [US3] Enforce fair gating: `class==dev` ⇒ unselectable while fair checked, reason shown; selection drives the Launch Configuration `pack` field
- [X] T018 [US3] Mid-run swap: selected pack + Use posts `{"pack": id}` to `brain_reset.request` (existing `write_reset_request`), `brain_status.json` follow already present

**Checkpoint**: dev pack refused under fair; mid-run swap reloads the live brain.

---

## Phase 6: User Story 4 - Guided pack editor, menu-driven by phase (Priority: P3)

**Goal**: Outline tree → typed forms; predicates structured; params schema-generated; freeform where allowed; save = loader-identical validation → new sibling pack.

**Independent Test**: edit a phase step + numeric cfg via forms only → save → new pack passes `load_pack`; deliberate breakage blocked with issues.

### Implementation for User Story 4

- [X] T019 [P] [US4] Create `components/dashboard/tests/test_packedit.py` — doc→outline map (`pack-edit-save.md` table), form→doc writes, slug enforcement `[a-z0-9-]+`, save-as-new writes `packs/<name>/pack.yaml` with `pack_id: pack.<name>` + `derived_from` + unchanged `class`/`revision`, source file byte-identical, `candidates/` refused, `validate_pack_doc` stub wiring
- [X] T020 [US4] Create `components/dashboard/src/dashboard/packedit.py` — Guided Edit Session (load `yaml.safe_load`, dirty tracking, outline model per v0→v1 label map; `decide`/`reflexes` v1-only sections shown only when present), node-type→form dispatch (scalar→typed control; predicate→combinator/field/op/value builder; steps→template dropdown + `params_schema`-generated rows + reorder; cfg→typed grid), op dropdown + insert-assist lists fed from `api.policy_vocabulary()` — facade unavailable ⇒ freeform text entry only, never a copied vocabulary table
- [X] T021 [US4] Build the editor Toplevel in `overlay.py`: left outline tree + right form pane + template `description:` as helper text; Save → `api.validate_pack_doc` → blocked-with-issues or write-new + rescan/select; name dialog prefilled `<id>-custom`; collision → rename-or-overwrite-user-pack prompt; Raw YAML tab (existing `_edit_brain` text box retained per FR-020)
- [X] T022 [US4] Active-pack guard: overwrite path only when target is the running pack — confirm "hot-swaps the live brain" → write + `brain_reset.request {}` (drift window ≈ one poll); non-active packs unrestricted, never post reset

**Checkpoint**: round-trip a real pack through forms → new sibling loads clean; invalid edit blocked before write.

---

## Phase 7: User Story 5 - One window owns the run lifecycle (Priority: P3)

**Goal**: Stop/Restart controls, Setup re-entry mid-run, no orphaned children.

**Independent Test**: run → stop → edit param → restart uses new argv; window close mid-run leaves no orphan.

### Implementation for User Story 5

- [X] T023 [US5] Monitor controls in `overlay.py`: Stop button (`terminate` → kill on timeout) + Restart button (confirm dialog → terminate → Setup with argv editable → GO respawns)
- [X] T024 [US5] Mid-run Setup re-entry polish: brains + pack Use + Edit Pack stay live during run; exit/stop restores argv editability
- [X] T025 [US5] Close path verified: closing the window mid-run terminates the loop child (no orphan `runtime loop`/`rimbrain loop` process)

**Checkpoint**: full launch→monitor→edit→restart loop inside one window.

---

## Phase 8: Polish & Cross-Cutting

- [X] T026 [P] Update `AGENTS.md` (menu command surface, `RIMBRAIN_LOOP_CMD`, editor save-as-new convention) and `components/rimbrain/CUSTOMIZE.md` (guided editor + `derived_from` field)
- [X] T027 [P] Update `specs/40-work-packages/TRACEABILITY.md` — feature 018 FR rows linking test evidence
- [X] T028 Run all `quickstart.md` scenarios — menu defaults, constraint mirror, brain verdicts (live + stubbed), pack swap, editor round-trip, lifecycle, `-y` exit-2 case
- [X] T029 Full-suite regression: `uv run pytest components/dashboard/tests components/runtime/tests -q` — all green incl. T006/T009/T013/T019 additions; `python -m dashboard.overlay` standalone still launches (GO disabled label when `RIMBRAIN_LOOP_CMD` unset)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: no dependencies — T001/T002/T003 parallel-able
- **Phase 2 Foundational**: T004/T005 need nothing upstream (runtime-only); T007/T008 need T002 (env var contract)
- **US1 (P1)**: needs Phase 1+2 — the whole screen stack + spawn path; T009 (its test) specifically needs T003's API shape
- **US2 (P2)**: needs T004/T005/T007 (facade + screen frame); panel mounts into US1's Setup screen but the module is independently testable
- **US3 (P2)**: needs T007; integrates with US1's Setup screen
- **US4 (P3)**: needs T001/T005; editor is a Toplevel — independent of US1
- **US5 (P3)**: needs T008/T010–T012 (Run Handle + Setup screen)
- **Phase 8**: after all desired stories

### User Story Dependencies

- **US1**: foundational only — MVP
- **US2**: facade + screen frame; independent module
- **US3**: screen frame only; independent
- **US4**: schema + validate facade only; most isolated story
- **US5**: builds on US1's machinery (only true story dependency)

### Parallel Opportunities

- Phase 1: all three tasks [P]
- Phase 2: T004, T005, T006 [P]
- After foundational: US2's `brains.py`, US3's descriptor helper, US4's `packedit.py` + tests are all different files — three stories can progress in parallel
- Within US4: T019 test [P] vs T020 module (test defines contract first)

## Parallel Example

```bash
# Phase 1 — all independent files:
Task: "derived_from in pack.schema.json"
Task: "rimbrain.py arg routing + RIMBRAIN_LOOP_CMD"
Task: "paramspec.py PARAM_SPEC + argv + violations"

# Post-foundational — three modules, three files:
Task: "brains.py role table + threaded checks"
Task: "packedit.py outline/forms/save-as-new"
Task: "overlay.py pack descriptor list"
```

## Implementation Strategy

### MVP First (US1 only)

Setup → Foundational → US1 ⇒ `rimbrain run` opens the menu, GO spawns a supervised fair run. Ship-stop there is already useful.

### Incremental

1. MVP (US1) → 2. +US2 brains (safety visibility) → 3. +US3 pack list → 4. +US4 editor → 5. +US5 lifecycle polish. Each story is a runnable increment; US4/US5 can swap order (US4 has no US5 dependency).
