# Tasks: Fork Bootstrap and Contract Foundation

**Input**: Design documents from `specs/001-fork-bootstrap-contracts/`

**Prerequisites**: plan.md, spec.md (5 user stories), research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the feature specification mandates them (contract corpus, event round-trip,
fixture replay, baseline integrity) — this feature's deliverables are largely test infrastructure.

**Organization**: Tasks grouped by user story; P1 stories (US1, US3) precede P2 (US2, US4) and P3 (US5).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Superproject scaffold the feature builds on.

- [x] T001 Verify superproject layout per plan.md: `components/{contracts,runtime,rimbrain,steward,lab,dashboard}`, `integrations/rimbridge`, `tests/{contract,fixtures,acceptance}`, `tools/`, `baselines/` exist; create missing dirs with README placeholders — verified 2026-09-22, all present
- [x] T002 [P] Create `tools/env-check.ps1` verifying toolchain prerequisites (git, uv, dotnet SDK, python) with clear pass/fail output per E2E-TEST-ENVIRONMENT TE-003/004 — delivered 2026-09-22 (toolchain/game/bridges/repo sections, 15/16 live)
- [x] T003 [P] Create `baselines/.gitignore` keeping generated bundle artifacts out of git while allowing `MANIFEST.yaml` and `gaps.yaml` to be committed — done 2026-09-22

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work begins until this phase completes.

- [x] T004 Draft ADR-001 "Bridge layer selection" in `specs/90-decisions/` comparing zorrobyte RimBridge (HTTP JSON-RPC :8765 + Steward), pardeike RimBridgeServer (GABP :5174, 125-tool surface verified live 2026-09-22), and a dual-adapter gateway — recommend one; this gates baseline capture target (T019) and future runtime bridge adapters. Constitution: architectural changes require ADR before code. — delivered as ADR-013 (zorrobyte HTTP primary, gateway-shaped adapter boundary, GABP diagnostics sidecar); companion ADR-014 (model serving stack)
- [x] T005 Scaffold `components/contracts/` skeleton per CONTRACTS.md §4: `schemas/{common,events,runtime}`, `examples/{valid,invalid}`, `registry/`, `compatibility/{VERSIONING.md,MIGRATIONS.md}`, `tests/`, `pyproject.toml` (Python 3.12+, deps: `jsonschema`, `pyyaml`), `LICENSE` (MIT)
- [x] T006 [P] Implement canonical-JSON hashing util `components/contracts/src/contracts/canonical.py` (RFC 8785/JCS key ordering, stable string/number encoding) — used by corpus hashes and fixtures
- [x] T007 Implement superproject corpus runner `tests/contract/corpus_runner.py` (entry points `validate-corpus` and `tests/contract/run-corpus` per quickstart.md §5): validates every `components/contracts/examples/valid/*.json` against its schema in `components/contracts/schemas/` (must pass) and every `examples/invalid/*.json` (must fail with `{ok:false,error:{code,...}}`)
- [x] T008 Implement upstream-baseline integrity scanner `tools/baseline_validate.py`: locates git via PATH with fallback to `C:\Program Files\Git\cmd\git.exe`, auto-recovers uninitialized submodules (`git submodule update --init --recursive` when a `-` pin prefix appears), then compares pins against manifest and runs `git status --porcelain` inside `upstream/rimagent`; exits nonzero with structured error on drift (FR-002, SC-006)

**Checkpoint**: Foundation ready — ADR decided, contracts scaffold live, hashing + corpus + integrity primitives working.

---

## Phase 3: User Story 1 - Fork Checkout and Validation (Priority: P1) 🎯 MVP

**Goal**: A maintainer gets a working fork checkout — pinned upstream intact, all component validation shells green, upstream suites passing unmodified.

**Independent Test**: Clean recursive clone + `tools/env-check.ps1` + per-component `validate` + upstream pytest/dotnet suites all pass with zero changes to `upstream/rimagent`.

### Tests for User Story 1

- [x] T009 [P] [US1] Acceptance test `tests/acceptance/test_fork_checkout.py`: asserts submodule pins (85cb050, 3c1e4c7), clean porcelain, and that upstream test commands are documented in output (SC-001/SC-002)
- [x] T010 [P] [US1] Tamper test `tests/acceptance/test_baseline_integrity.py`: modifies a scratch file under `upstream/rimagent/`, asserts `tools/baseline_validate.py` flags it within 60 s (SC-006 timing bound), then restores

### Implementation for User Story 1

- [x] T011 [P] [US1] Add one shared runner `tools/validate_components.py` that discovers each component under `components/` and invokes its declared self-check (per-component entry stays a thin shim or doc-declared command); prints component name/version + toolchain presence + `ok:<component>`; passes without game/model/network/secrets (FR-003). Avoids six copy-pasted scripts.
- [x] T012 [P] [US1] Add per-component CI shell `components/*/ci.yml` (GitHub Actions stub) that runs the component's `validate`; inert until remotes exist (FR-014)
- [x] T013 [US1] Add `tests/acceptance/run_quickstart.ps1` executing quickstart.md sections 1–3 (checkout, validation shells, upstream parity) with pass/fail summary (SC-002)

**Checkpoint**: US1 fully functional — fork baseline proven, MVP validatable.

---

## Phase 4: User Story 3 - Shared Contract Primitives (Priority: P1)

**Goal**: One shared definition of ID, revision, freshness, and error consumed identically by every component.

**Independent Test**: `validate-corpus` accepts 100% of valid and rejects 100% of invalid primitive examples across a runtime consumer import.

### Tests for User Story 3

- [x] T014 [P] [US3] Write corpus `components/contracts/examples/{valid,invalid}/id.schema.json*`, `revision-set.*`, `freshness.*`, `error.*` per contracts/contract-primitives.md (ID grammar `^[a-z][a-z0-9]*\.[A-Za-z0-9][A-Za-z0-9_-]{2,63}$`, `schema_version` required int, freshness required on freshness-bearing refs, error `{ok:false,error:{code,message,details?,retryable}}`) — invalid set includes malformed ID, negative version, missing freshness, error without `code`, unknown extra key
- [x] T015 [P] [US3] Consumer contract test `components/contracts/tests/test_primitive_consumer.py`: a minimal consumer loads the corpus through canonical JSON hashing and asserts identical acceptance/rejection to the runner (SC-003)
- [x] T016 [P] [US3] Property tests `tests/contract/test_primitives_property.py` per CONTRACTS.md §9: seeded-random ID grammar fuzzing, string/array/size bounds, and canonicalization stability (same input → identical hash across runs); deterministic seed recorded in test

### Implementation for User Story 3

- [x] T017 [P] [US3] Create `schemas/common/id.schema.json`, `revision-set.schema.json`, `freshness.schema.json`, `error.schema.json` (JSON Schema 2020-12, `additionalProperties: false`) per contracts/contract-primitives.md (FR-005)
- [x] T018 [US3] Add `components/contracts/compatibility/VERSIONING.md` + `MIGRATIONS.md` documenting schema_version bump rules (major = meaning change/removal, minor = new optional field, consumers reject unknown newer) and a breaking-change detection note (FR-006, CONTRACTS.md §5.3)

**Checkpoint**: Primitives shareable — corpus + property tests green, consumer parity proven.

---

## Phase 5: User Story 2 - Baseline Characterization Capture (Priority: P2)

**Goal**: Immutable baseline bundle of the pinned upstream — RPC inventory, synthesized event corpus, automation surface, manifest — diffable by all later migration work.

**Independent Test**: Run capture twice on the same pinned baseline → identical manifest/inventory records; bundle answers "what did upstream expose/emit" offline.

### Tests for User Story 2

- [x] T019 [US2] Capture-tool test `tests/acceptance/test_baseline_capture.py`: asserts `rpc-inventory.json` contains 115 methods (97 RimBridge + 18 Steward) extracted from `[Rpc(` attributes in `upstream/rimagent/mod/Source` and `mod-steward/Source` (target per ADR-001, T004, outcome) and that two consecutive captures produce identical manifests (FR-009)

### Implementation for User Story 2

- [x] T020 [P] [US2] Implement static RPC extractor `tools/baseline_capture.py` (mode `rpc`): parses `[Rpc(name, doc)]` attributes → `rpc-inventory.json` rows `{name, group, doc, source_file, line}` — `source_file`/`line` enable upstream-origin traceability (FR-009, FR-013; R2)
- [x] T021 [P] [US2] Implement event-corpus synthesizer (mode `events`): generates one record per upstream `bus.py` kind (18 kinds, `{seq,t,kind,data}` shapes per bus.py docstring) marked `provenance: synthesized-from-docstring` → `event-corpus/bus-kinds.jsonl` (R2, FR-009)
- [x] T022 [P] [US2] Implement automation-surface extractor (mode `steward`): inventories Steward orders/scorer/stock RPCs + config surface from `mod-steward/Source` + upstream AGENTS.md → `automation-surface.yaml` (FR-009)
- [x] T023 [US2] Implement manifest writer (mode `manifest`): emits `baselines/upstream-85cb050/MANIFEST.yaml` with pins, tree hash, capture methods, tool manifest, and `gaps.yaml` recording the deferred live state.summary/event samples with `provenance: synthesized-from-docstring` for synthesized entries; then seals the bundle (FR-009, data-model.md BaselineBundle)

**Checkpoint**: Baseline captured and sealed — migration equivalence diffs now possible.

---

## Phase 6: User Story 4 - Canonical Event Envelope (Priority: P2)

**Goal**: One canonical record envelope subsuming the upstream JSONL stream; every upstream kind maps cleanly, unknown kinds preserved-not-executed.

**Independent Test**: Round-trip corpus — 17 synthesized upstream-kind records map forward and reproduce original `{seq,kind,data}` losslessly (SC-004).

### Tests for User Story 4

- [x] T024 [P] [US4] Round-trip test `components/contracts/tests/test_event_roundtrip.py`: maps each upstream kind through `components/contracts/registry/event-map.yaml` and asserts payload + ordering preservation; unknown-kind record → `legacy.unmapped`, stored but rejected by strict consumer (FR-008, SC-004)
- [x] T025 [P] [US4] Schema-drift test: record with `schema_version` greater than consumer's max → explicit `{ok:false,error}` rejection, never silent misread (FR-006, envelope contract §Validation)

### Implementation for User Story 4

- [x] T026 [P] [US4] Create `schemas/events/envelope.schema.json` with required fields per contracts/canonical-event-envelope.md: `schema_version, event_id (evt.*), episode_id, sequence, event_type, game_tick, wall_time_utc, source, correlation, revisions, payload, privacy` (FR-007)
- [x] T027 [P] [US4] Create `schemas/events/types/` payload schemas for the initial mapped families (`system.*`, `model.*`, `bridge.event.ingested`, `policy.*`, `episode.*`, `observation.packet.shown`, `operator.*`, `legacy.unmapped`) (FR-007/008)
- [x] T028 [US4] Author `components/contracts/registry/event-map.yaml` — versioned kind→type mapping per contracts/canonical-event-envelope.md table, in the event-type registry (CONTRACTS.md §2); emit `legacy.unmapped` rule for unknown kinds (FR-008, R5)

**Checkpoint**: Canonical event layer live — history-readable, schema-gated.

---

## Phase 7: User Story 5 - Replayable Fixture Harness (Priority: P3)

**Goal**: Offline, deterministic replay of recorded session segments as portable fixtures — the "replay before live authority" machinery.

**Independent Test**: Replay the same fixture 5× → identical comparison reports; corrupt fixture fails closed with a named defect (SC-005, FR-011).

### Tests for User Story 5

- [x] T029 [P] [US5] Fixture corpus `tests/fixtures/`: `fix.seed-001` (minimal valid, input+expected), `fix.max-001` (with `blobs/` side payload), `fix.corrupt-001` (truncated JSONL tail + bad hash) per contracts/fixture-package.md (FR-010/011)
- [x] T030 [P] [US5] Harness tests `components/lab/tests/test_fixture_harness.py`: determinism (5 runs identical), fail-closed on corrupt/truncated with named structural defect, quarantine salvage for torn tail (FR-011, FR-012, SC-005)

### Implementation for User Story 5

- [x] T031 [US5] Implement fixture harness in `components/lab/src/lab/fixtures.py` — replay/replay-harness ownership is lab's per `specs/20-submodules/LAB.md` and REPOSITORY-TOPOLOGY (contracts owns only the fixture *schema*): load `manifest.yaml`, verify sha256 file hashes, parse `input.jsonl` → CanonicalRecords, reject missing provenance, move torn records to `quarantine/`, compare against `expected.jsonl` with `exact|field-subset` modes, emit deterministic report (FR-010/011/012, contracts/fixture-package.md §Harness semantics)
- [x] T032 [US5] Seed the first synthesized fixtures from the baseline event corpus (`event-corpus/bus-kinds.jsonl`) with provenance `synthesized-from-baseline` (FR-010, spec US5)

**Checkpoint**: Replay loop functional offline — deterministic, fail-closed, corpus-seeded.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Docs, acceptance closure, repo hygiene.

- [x] T033 [P] Update `AGENTS.md` + `specs/INDEX.md` to reference this feature's artifacts and the new `tools/bridgecheck` + `tools/baseline_capture.py` dev tools
- [x] T034 [P] Wire CI shells: `tests/acceptance/run_quickstart.ps1` + corpus + baseline-validate into the superproject CI stub (inert until remotes) (FR-014)
- [x] T035 Run quickstart.md sections 1–7 end-to-end; record results against SC-001..007 in `checklists/requirements.md`; record FR-013 traceability status (baseline inventory `source_file`/`line` rows) (traceability row for this feature)
- [x] T036 [P] Sweep for secrets: grep fixtures/examples/manifests for `config.local.yaml` values, tokens, absolute paths; ensure `bridge_check.py` token handling is documented as local-session-only (FR-secrets rule, constitution)
- [x] T037 [P] Windows mod build/deploy scripts: `tools/build-mods.ps1` + `tools/deploy-mods.ps1` delivered 2026-09-22 — junctions into `V:\SteamLibrary\...\Mods`, ModsConfig enable applied while game closed (TE-010/012); game restart still pending user launch

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately
- **Foundational (Phase 2)**: depends on Setup; **BLOCKS all user stories** (ADR-001 gates T019; scaffold/hashing/corpus/integrity used by every story)
- **User Stories (Phase 3+)**: depend on Foundational
  - US1 (P1) and US3 (P1) proceed in parallel
  - US2 (P2) depends on ADR-001 (T004) for capture target
  - US4 (P2) depends on US3 (primitives: revision-set/freshness)
  - US5 (P3) depends on US2 (baseline corpus seeds fixtures) and US4 (records are canonical)
- **Polish (Phase 8)**: after all stories

### User Story Dependencies

- **US1**: none beyond Foundational — independently testable (fork checkout green)
- **US3**: none beyond Foundational — corpus + property tests green standalone
- **US2**: ADR-001 decision — capture target (zorrobyte `[Rpc]` vs GABP surface)
- **US4**: US3 primitives — envelope embeds revision-set/freshness
- **US5**: US2 + US4 — fixture provenance and canonical records

### Within Each User Story

Tests/corpus first (red), then implementation (green) — contract-first per constitution III.

### Parallel Opportunities

- Phase 1: T002/T003 in parallel
- Phase 2: T005/T006/T007/T008 in parallel after T004
- US1+US3 phases in parallel (T009–T018), then US2+US4 (T019–T028), then US5 (T029–T032)
- All `[P]` tasks run concurrently

---

## Parallel Example: User Story 1

```text
Task: "Acceptance test test_fork_checkout.py in tests/acceptance/"
Task: "Tamper test test_baseline_integrity.py in tests/acceptance/"
Task: "Component validate entry points in components/*/validate.py"
Task: "CI shells in components/*/ci.yml"
```

## Parallel Example: User Story 3

```text
Task: "Primitive corpus in components/contracts/examples/"
Task: "Consumer contract test in components/contracts/tests/test_primitive_consumer.py"
Task: "Property tests in tests/contract/test_primitives_property.py"
Task: "Primitive schemas in components/contracts/schemas/common/"
```

---

## Implementation Strategy

### MVP First (US1 + Foundational)

1. Phase 1 Setup → Phase 2 Foundational (incl. ADR-001)
2. Phase 3 US1 — fork checkout + validation shells + acceptance tests
3. **STOP and VALIDATE**: quickstart sections 1–3 green; deploy nothing
4. Deliverable: provably working fork baseline (SC-001/002/006)

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → test → MVP (fork proven)
3. US3 → test (primitives green)
4. US2 → test (baseline sealed)
5. US4 → test (envelope round-trip)
6. US5 → test (replay loop)
7. Polish → full quickstart acceptance (SC-001..007)

### Parallel Team Strategy

- Team A: US1 (fork/validation) · Team B: US3 (primitives) — in parallel after Foundational
- Then Team A: US2 + US4 (baseline, envelope) · Team B: US5 (fixtures)
- Integrate and run full quickstart at each checkpoint

---

## Notes

- ADR-001 (T004) is the only cross-feature dependency — the bridge decision also feeds `specs/20-submodules/RIMBRIDGE.md` and runtime work packages, but 001 stays executable under either outcome.
- `bridge_check.py` (already delivered in `tools/bridgecheck/`) serves quickstart section 4/E2E TE-015 and is not re-implemented here.
- Commit after each task or logical group; stop at checkpoints to validate stories independently.


## Phase 9: Convergence

- [x] T038 Restrict baseline `tree_hash` to git-tracked files only (`git ls-files`) so MANIFEST hashes are stable across machines and unaffected by gitignored locals like `config.local.yaml` per FR-009 (partial)
- [x] T039 Capture live representative samples into `baselines/upstream-85cb050/` once a game is loaded (real `state.summary` + real event-window capture), closing the `gaps.yaml` deferred-live entries per FR-009 (partial)
- [x] T040 Point `components/lab` validation at its real pytest suite so `validate_components` exercises the 12 fixture-harness tests instead of the no-op shell per FR-003 (partial)
- [x] T041 Decide and record whether `error.schema.json` accepts `{ok:true,result}` shapes (current `oneOf` permits it); if failure-only, tighten schema and corpus per FR-006 (partial)
- [x] T042 Pin `revision-set` slot values to a single type (or document the string|int>=0 union as intentional) per FR-005 (partial)
- [x] T043 Correct `17 kinds` to `18 kinds` in spec/quickstart text (real bus.py enumerates 18; corpus already emits all 18) per SC-004 (missing)
- [x] T044 Extend `tests/acceptance/run_quickstart.ps1` to quickstart sections 4-7 (baseline, corpus, event-map, fixture replay) or document that �1-3 is the automated scope per T013 (partial)


## Phase 10: Convergence

- [x] T045 `tools/baseline_capture.py live` prints a structured `LIVE_CAPTURE_UNAVAILABLE` error but exits 0 -- return nonzero so callers can detect failure per FR-002 error-envelope contract (partial)
