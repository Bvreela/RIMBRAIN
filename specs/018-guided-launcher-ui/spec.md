# Feature Specification: Guided Launcher UI

**Feature Branch**: `feature/018-guided-launcher-ui`

**Created**: 2026-09-24

**Status**: Draft

**Input**: "Present a startup menu where the user can select from all startup params with checkboxes, defaulting to fair run. The UI needs pack selection and a BIGbrain/fastbrain status check so the user can verify API connections to both AIs are running and see which model is connected. The pack editor must be menu-driven by phase, prescriptive in its main form, allow freeform text where permitted, manage data structure via the UI, and make it easy for a child to change pack logic."

**Design decisions (locked with operator 2026-09-24)**:

- One window, stacked screens — the overlay becomes the run supervisor: it owns the loop child process (spawn on GO, stop, restart, exit detection), not a passive tail.
- Command surface: bare `rimbrain` and `rimbrain run` (no args) open the menu; `rimbrain run -y` runs today's fair-default pass immediately; `rimbrain run <any flags>` stays headless; `loop`/`overlay` child entries unchanged.
- Guided editor saves-as-new pack (`packs/<id>-custom/pack.yaml` by default, name editable); source packs are never rewritten; `derived_from:` lineage recorded in the copy.
- Brain checks are live calls, not just listings: the select tier answers a real typed question; the plan tier answers a minimal chat completion against the bound model.
- Setup is a permanent screen, re-enterable mid-run: argv params read-only while a run is live; pack swap, brain probes, and the editor stay live; GO becomes "Restart run".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch screen drives the run (Priority: P1)

The operator opens the app and sees a setup screen instead of a run starting blind. Every startup parameter appears as a labeled control — run mode, fair/dev, live confirmation, live-brain, live-mutate, feed, ledger, no-store, no-hold, iterations, bridge address — defaulting to the current fair-run preset. A pack list shows each pack's class badge. A brains panel shows whether each AI tier is actually answering. One button starts the run; the same window then shows the live monitor.

**Why this priority**: The launcher is the whole point of the feature — everything else (pack editing, brain checks) hangs off this screen or is reachable from it. A child should be able to start a fair run by pressing one button.

**Independent Test**: Open the app with no arguments; verify every flag the loop accepts has a control, defaults match the fair preset, invalid combinations are unreachable or blocked with an explanation, and GO starts a run that behaves identically to today's default command line.

**Acceptance Scenarios**:

1. **Given** the app opened with no arguments, **When** the setup screen renders, **Then** every startup parameter is present as a control with the fair-run defaults applied (fair on, live-brain on, live-mutate on, feed on, start mode, default pack).
2. **Given** an invalid flag combination (e.g. cycle mode with fair on, or live-mutate with an ineligible mode), **When** the operator selects it, **Then** the combination is blocked or visibly flagged with the reason — the same fail-closed rules the command line enforces, never a surprise at GO.
3. **Given** any flag on the command line, **When** the app is invoked with it, **Then** no menu appears and the run proceeds headless exactly as today.
4. **Given** the menu is open, **When** GO is pressed, **Then** a run starts with a command line equivalent to the visible controls, and the window swaps to the monitor view.
5. **Given** a running loop, **When** it exits for any reason, **Then** the monitor reports the exit within one refresh cycle instead of silently tailing stale state.

---

### User Story 2 - Both brains verified live before and during a run (Priority: P2)

The brains panel shows one row per AI role — planner/review/improve (BIGbrain) and selector (fastbrain), plus the embed role. Each row resolves the role's binding to show which endpoint and which exact model is connected, runs a live test call against that bound model, and displays the result: answered (with latency), reachable-but-not-answering, or unreachable — plus the fallback chain that would engage.

**Why this priority**: "Is the AI actually working" is the user's stated need; a model listing that proves nothing about the chat/decide path is not good enough. A failed brain doesn't block the run — degraded paths exist — but the operator must see which brain the run will actually use.

**Independent Test**: With endpoints stubbed to known-good and known-bad states, verify each row shows the bound endpoint+model, the correct verdict, and the declared fallback chain — without blocking the UI while slow endpoints respond.

**Acceptance Scenarios**:

1. **Given** a healthy bound endpoint+model, **When** the brains check runs, **Then** the row shows connected, the model name, and the measured latency of a real role-shaped call (typed question for the select tier, minimal completion for the plan tier).
2. **Given** an endpoint that answers listings but whose bound model fails a live call, **When** the check runs, **Then** the row distinguishes "endpoint up, model not answering" from "unreachable", and names the fallback that would engage.
3. **Given** an unreachable endpoint, **When** the check runs, **Then** the row shows unreachable plus the fallback chain; the run is never blocked by a failed brain.
4. **Given** a slow or rate-limited endpoint, **When** checks are in flight, **Then** the screen stays responsive, shows a checking state, and resolves within a bounded timeout.
5. **Given** a bindings change, **When** the operator re-checks, **Then** the displayed endpoint+model reflects the new binding.

---

### User Story 3 - Pack selection with class visibility (Priority: P2)

The setup screen lists every discoverable pack with its declared class (fair/dev) and lineage. Dev-class packs are visibly marked and cannot be selected while fair is on. Selecting a pack works both at launch and mid-run: mid-run selection goes through the existing live-swap channel with its full state reinitialization.

**Why this priority**: Pack choice is a first-class launch decision the user explicitly asked for; class badges prevent the confusing failure of picking a dev pack for a fair run.

**Independent Test**: With a packs dir containing fair and dev packs, verify the list, badges, fair-mode gating, and that a mid-run swap posts the same reset request today's picker posts.

**Acceptance Scenarios**:

1. **Given** packs on disk, **When** the setup screen renders, **Then** every pack is listed with id, class badge, and derivation lineage where recorded.
2. **Given** fair mode on and a dev-class pack, **When** the operator tries to select it, **Then** selection is refused with the reason shown.
3. **Given** a running loop, **When** the operator picks a different pack and confirms, **Then** the live swap request is posted exactly as today's Use button does, and the run reloads under the new pack.
4. **Given** a pack newly created by the editor, **When** the list refreshes, **Then** it appears and is selectable.

---

### User Story 4 - Guided pack editor, menu-driven by phase (Priority: P3)

Opening a pack in the editor presents an outline organized by pack structure — meta, configuration blocks, reflexes, phases, rules, standing goals, decide/mutate configuration — aligned with the unified phase vocabulary. Selecting a node shows a form, not raw text: fields become typed controls, predicates become structured builders (combinator + field + operator + value), steps pick their template from a dropdown with its description, and step parameters are generated from the template's declared schema so only legal keys exist. Freeform text remains where the pack language is inherently freeform (resolver expressions, descriptions, configuration values), assisted by an insert-list of known function/config/variable names.

**Why this priority**: The raw-YAML editor is the current "Edit Brain" and is the barrier to a child changing pack logic; this is the user's core ask after the launcher. P3 only because launch + brains must exist first to make edited packs runnable/testable in one window.

**Independent Test**: Open a real pack, change a phase's step parameter and a numeric config through forms only, save, and verify the new pack loads and validates under the identical checks the loader applies.

**Acceptance Scenarios**:

1. **Given** any pack, **When** it opens in the editor, **Then** every top-level section appears in the outline and every node shows a form appropriate to its type.
2. **Given** a step form, **When** the operator picks a template, **Then** parameter rows are generated from that template's declared parameter schema — no hand-typed parameter keys.
3. **Given** a predicate field (effect/when/repeat), **When** editing, **Then** the operator works in a structured builder limited to the pack dialect's combinators and operators.
4. **Given** edits made, **When** saving, **Then** the document passes the same validation the loader applies (schema, policy vocabulary, sealed method inventory) or the save is blocked with the violations listed.
5. **Given** a successful save, **Then** the result is a new sibling pack (never a rewritten source) that the launcher can select and run.
6. **Given** any field the pack language leaves freeform, **When** editing it, **Then** plain text entry remains available with insert-assist for known names.

---

### User Story 5 - One window owns the run lifecycle (Priority: P3)

The window supervises the loop process: GO spawns it, the monitor shows its output-driven views plus process status, and Stop/Restart controls exist. Setup remains reachable during a run; run-fixed parameters display read-only with an "applies to next run" note, while pack selection, brain checks, and the editor remain live. Restarting applies edited parameters after confirmation.

**Why this priority**: Converts three separate concerns (launch, monitor, edit) into one place and makes iteration loops (edit pack → restart → watch) single-window. P3 because a launchable monitor already exists; this is lifecycle polish.

**Independent Test**: Start a run from the menu, stop it, change a parameter, restart, and verify the new run uses the edited command line — all within one window, with exit status reported throughout.

**Acceptance Scenarios**:

1. **Given** a running loop, **When** the operator opens Setup, **Then** run-fixed parameters are read-only and labeled, while pack/brains/editor controls stay live.
2. **Given** a running loop, **When** Stop is pressed, **Then** the loop child terminates and the monitor reports the stopped state.
3. **Given** edited parameters and a stopped or running loop, **When** Restart is confirmed, **Then** a new loop starts with the edited command line.
4. **Given** the window closing while a loop runs, **When** it closes, **Then** the loop child is terminated — no orphaned run.
5. **Given** a save over the currently-running pack, **When** the operator chooses overwrite, **Then** the editor warns it hot-swaps the live brain and pairs the write with a reload request so the run does not sit in a drift-frozen state.

---

### Edge Cases

- Probes hang or exceed their timeout → row resolves to unreachable/transient with the fallback note; the screen never blocks on a probe.
- Bound model is absent from the endpoint's advertised list → row flags "model not advertised" even when the endpoint answers.
- A save-as-new name collides with an existing pack → operator is asked to choose another name or confirm overwrite; blank names are refused.
- The loop child dies between GO and the first state write → monitor shows "exited" with the exit code, not a frozen "starting" state.
- Operator edits the *active* pack's file outside the editor mid-run → existing pack-drift freeze applies unchanged; the editor's own overwrite+reset path is the supported hot-swap.
- Dev pack selected then fair re-checked → selection is revoked or flagged before GO can fire.
- Frozen executable behaves identically to the dev invocation — menu, supervisor, editor, and probes resolve the same writable/bundled roots.

## Requirements *(mandatory)*

### Functional Requirements

**Launch & parameters**

- **FR-001**: The app MUST present a setup screen before a run starts when invoked with no run arguments; invocation with any run argument MUST bypass the screen unchanged, and a skip flag MUST start the fair-default pass immediately.
- **FR-002**: Every parameter the run loop accepts MUST have a labeled control; the screen MUST be generated from a declarative parameter specification so a reduced flag surface (feature 017's consolidation) re-renders without rework. The run-mode control in particular MUST enumerate every run type the runtime exposes — including play-option modes specified after this feature (e.g. feature 021 fast-evolve) — so new run types appear without UI rework.
- **FR-003**: Defaults MUST equal today's fair-run preset: fair on, start mode, default pack, live confirmation, live-brain, live-mutate, and feed enabled.
- **FR-004**: Invalid flag combinations MUST be blocked or visibly flagged at selection time, mirroring the loop's fail-closed validation (cycle needs dev; live-ish modes need the live confirmation; live-mutate needs an eligible mode; dev-class packs need fair off).
- **FR-005**: GO MUST start a run whose effective parameters exactly match the visible controls.

**Brain verification**

- **FR-006**: The brains panel MUST show one row per bound role — at minimum plan, select, review, improve, embed — each resolving to its endpoint id and bound model name.
- **FR-007**: Each row MUST run a live, role-shaped verification — a call shaped by the role's required capability (typed decision for select, minimal completion for chat roles, embeddings ping for the embed role) executed against the bound model — not merely an endpoint listing.
- **FR-008**: Verdicts MUST distinguish answered (with latency), reachable-but-model-failing, unreachable, and missing-secret; each row MUST display the declared fallback chain for that role.
- **FR-009**: Checks MUST run off the display thread with a checking state, bounded timeout, and a manual re-check action; a failed check MUST NOT block GO.
- **FR-010**: Probe logic MUST live behind the public runtime API facade; the UI MUST NOT import runtime internals.

**Pack selection**

- **FR-011**: The pack list MUST discover folder packs and flat packs, display each pack's class, and show recorded derivation lineage.
- **FR-012**: Dev-class packs MUST be unselectable while fair is on, with the reason visible.
- **FR-013**: Mid-run pack selection MUST use the existing brain-reset request channel (full state reinitialization), identical to today's Use action.

**Guided pack editor**

- **FR-014**: The editor MUST present an outline organized by pack structure — meta, configuration blocks, reflexes, phases, rules, standing goals, decide/mutate — using the unified phase vocabulary for labels while reading the on-disk pack layout.
- **FR-015**: Every node type MUST map to a form: scalar fields to typed controls, predicates to a structured builder (combinator, field, operator from the pack dialect, value), steps to template dropdown + schema-generated parameter rows, lists to add/remove/reorder editors.
- **FR-016**: Fields that are inherently freeform (resolver expressions, descriptions, configuration values) MUST keep plain text entry, with insert-assist listing known function, config, and variable names.
- **FR-017**: Template descriptions and field comments MUST be surfaced as helper text so an inexperienced operator can understand each control.
- **FR-018**: Save MUST validate the document with the identical checks the pack loader applies — schema, policy vocabulary, sealed method inventory — and block with violations listed on failure.
- **FR-019**: Guided saves MUST write a new sibling pack (`packs/<name>/pack.yaml`, default name `<source>-custom`, editable, slug-enforced), record `derived_from` lineage, update the pack id inside the file, and never rewrite the source pack; user packs MUST NOT be written into the mutation-candidates directory.
- **FR-020**: A raw-text editing mode MUST remain available for direct pack editing.

**Run lifecycle**

- **FR-021**: The window MUST own the loop process it spawns: report running/exited status each refresh, provide Stop, and terminate the child when the window closes.
- **FR-022**: Setup MUST remain reachable mid-run with run-fixed parameters read-only and labeled "applies to next run"; pack, brains, and editor controls stay live.
- **FR-023**: Restart MUST confirm, terminate any running child, and start a new run with the current parameter set.
- **FR-024**: Saving over the active pack MUST warn that it hot-swaps the live brain and MUST pair the write with a reload request; saving as new or editing non-active packs MUST be unrestricted.

### Key Entities

- **Launch Configuration**: The parameter set assembled on the setup screen — mode, flags, pack, iterations, bridge — serialized into the run's command line; immutable once a run is live.
- **Pack Descriptor**: A discoverable pack's identity — id, on-disk form (folder/flat), declared class, derivation lineage.
- **Brain Status**: Per-role verification record — role, resolved endpoint id, bound model, verdict, latency, fallback chain, checked-at time.
- **Guided Edit Session**: A loaded pack document plus pending form edits; commits by validation → save-as-new (or warned overwrite of the active pack).
- **Run Handle**: The supervised loop child — process identity, argv, exit status; one per window.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh operator reaches a running fair pass in ≤3 interactions from window open (open → optional pack pick → GO).
- **SC-002**: 100% of parameters the run loop accepts are represented as controls, and 100% of invalid combinations the loop rejects are blocked or flagged before GO.
- **SC-003**: Brain checks resolve within their bounded timeout for every endpoint state (healthy, listing-only, unreachable, missing secret); the screen never blocks longer than the timeout.
- **SC-004**: A guided edit touching a phase step and a numeric configuration saves as a new pack that passes the loader's validation 100% of the time; a deliberately invalid edit is blocked before write 100% of the time.
- **SC-005**: Source pack files are byte-identical before and after any guided save; new packs appear in the launcher list without an app restart.
- **SC-006**: Loop death is surfaced in the monitor within one refresh cycle; window close leaves zero orphaned loop processes.

## Assumptions

- **Sequencing gate (operator decision, 2026-09-24):** this feature implements *last* among the queued features — after 017 unified phase engine, 019 combat capability, 020 building capability, and 021 fast-evolve are implemented and their suites pass. The declarative parameter spec (FR-002) is then generated from the final mode/flag/run-type surface once, rather than snapshotted early and reworked per feature.
- The existing overlay window technology is retained; this feature extends it rather than introducing a second UI stack.
- The runtime's public API facade is the only permitted path for endpoint probing and binding resolution from UI code.
- The brain-reset request file channel already handles pack swap/reset/unload and is reused unchanged.
- Packs on disk are schema v1 (feature 017 landed the native shape + auto-migration); the editor's outline uses the unified phase vocabulary directly against v1 roots.
- Comment preservation inside guided-save copies is best-effort (copy-then-patch where feasible); source packs are never modified so no documentation is destroyed.
- Probe verdicts are advisory: degraded-path fallbacks mean a failed brain never blocks a run.
- The mutation-candidates directory remains exclusively owned by the reflect/mutate pipeline.
