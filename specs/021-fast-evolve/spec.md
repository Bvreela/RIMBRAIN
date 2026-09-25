# Feature Specification: Fast-Evolve Play Mode

**Feature Branch**: `021-fast-evolve`

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description: "A play option that allows for daily mutate/evolve based on day failure triggers. If between an autosave we have a fail or trigger near fail states we allow an AI evolve change to the pack to address the problem and allow save scum reload to try the day again. We only allow 2 save reloads per day; if the evolve is not successful after the third try we move forward to the next day. This fast-evolve needs to be a game load option."

**Design decisions (locked with operator 2026-09-24)**:

- The play option lives on the launcher and command line — a `fastevolve` run mode selectable at game load, alongside the existing fair-run default. (The runtime cannot add options inside RimWorld's own load dialog.)
- Day failure detection uses **both** levels: the existing goal-level failure/near-failure triggers and colony-level declared predicates over observed state (e.g. colonist downed/dead, food runway collapsed, hostiles present).
- The retry anchor is a **real RimWorld autosave** detected from the game's save list, matched by a configurable name pattern — not a checkpoint the agent takes itself.
- When retries are exhausted, the **last evolved pack carries forward** into the next day (no revert to the day-start pack).

## Clarifications

### Session 2026-09-24

- Q: Should an evolve pass also run at every day boundary even on failure-free days? → A: No — evolve passes are failure-triggered only; a clean day produces no reflection call.
- Q: When a day exhausts its reloads, does the third failure still evolve the pack? → A: Yes — the reflection pass still runs (bounded by the per-day pass budget); only the reload is skipped, and the evolved pack carries forward.
- Q: When several autosaves exist for the current day, which is the retry anchor? → A: The autosave nearest the day's start — a retry replays the whole day; a mid-day autosave is used only when no day-start anchor exists.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retry a failing day with an evolved brain (Priority: P1)

The operator starts a colony run with the fast-evolve play option. During a day, the colony hits a failure or near-failure trigger (a goal goes terminal-failed, or a declared colony predicate trips — a colonist dies, food runs out). The run pauses, the reflection pass diagnoses what went wrong and produces an evolved pack, the evolved pack activates, the game reloads the autosave taken at the start of the day, and the day is replayed under the new policy. If the day fails again the cycle repeats once more; a third failure accepts the outcome and play advances to the next day with the last evolved pack in charge.

**Why this priority**: This is the entire feature — daily evolve-and-retry is the play option's core loop. Everything else (triggers, anchoring, evidence) exists to serve it.

**Independent Test**: Drive a run where a declared failure predicate trips mid-day; verify the game reloads the day-start autosave under a promoted candidate pack, the day replays, and a third failure advances without a third reload.

**Acceptance Scenarios**:

1. **Given** a fast-evolve run with a known autosave anchor for the current day, **When** a day-failure trigger fires, **Then** the game pauses, a reflection pass runs, any gated candidate is promoted, the day-start autosave is loaded, and play resumes with attempt count 2 of 3.
2. **Given** a day that has already used both reloads, **When** another failure trigger fires, **Then** no reload occurs, the day is marked exhausted, and play continues into the next day under the most recently promoted pack.
3. **Given** a day in which no trigger fires, **When** the in-game day rolls over, **Then** the retry budget resets and the next detected autosave becomes the new anchor.
4. **Given** a reflection pass that produces no candidate (degraded or empty proposal), **When** the trigger fired with budget remaining, **Then** the autosave still reloads and the day retries under the unchanged pack.

---

### User Story 2 - Fast-evolve is a declared play option (Priority: P1)

The operator chooses fast-evolve at game load — as a run-mode flag on the command line today and as a labeled play-option control on the launcher setup screen when the guided UI ships. The option is visibly distinct from a fair run: fair runs and scored episodes can never enable it, and it is never the default.

**Why this priority**: The user explicitly required this to be a game load option — an explicit, informed choice, not a hidden harness. It shares P1 with the core loop because a mode nobody can select delivers nothing.

**Independent Test**: Attempt to select the option alongside incompatible settings (a fair/scored run); verify the combination is refused with a named reason, while a standalone fast-evolve selection starts a run that exercises the retry loop.

**Acceptance Scenarios**:

1. **Given** the run command line, **When** the operator selects the fast-evolve mode, **Then** the run starts with day-anchored retry behavior enabled and every other mode's protections (no debug methods) intact.
2. **Given** a scored-episode context, **When** fast-evolve is requested, **Then** the launch refuses with a named error — while inside the mode, fair protections stay on (debug-class methods remain refused; only save/load is additionally permitted).
3. **Given** the launcher setup screen, **When** it renders play options, **Then** fast-evolve appears as a selectable non-default option.

---

### User Story 3 - Day failure triggers are pack policy (Priority: P2)

The pack author declares what counts as a day failure: colony-level predicates over observed state (colonist count dropped, a colonist downed or dead, food runway below a threshold, hostiles on the map) and whether the existing goal-level failure/near-failure signals (goal failed/expired, requeue bursts, refusal bursts, stalls, escalations, defect patterns) also trigger a retry. Thresholds, the autosave name pattern, the reload budget, and the reflection-pass call budget per day are all pack data.

**Why this priority**: "All gameplay policy lives in packs" is a project invariant — hardcoding the failure definition would make the mode untunable without a code change. The mode is playable with defaults, but the policy surface is what makes it a brain feature rather than a harness hack.

**Independent Test**: Edit only pack data to add a failure predicate (e.g. food_days below a value) and confirm a run treats that condition as a day failure with no code change.

**Acceptance Scenarios**:

1. **Given** a pack declaring a colony-level failure predicate, **When** the predicate's conditions are met mid-day, **Then** a day-failure trigger fires exactly as a goal-level failure would.
2. **Given** a pack disabling goal-level triggers, **When** a goal fails mid-day but no colony predicate trips, **Then** no retry occurs.
3. **Given** a changed reload budget in pack data, **When** a day fails repeatedly, **Then** the new budget is honored without any code change.

---

### User Story 4 - Retry transparency (Priority: P3)

Every day rollover, trigger, reflection outcome, promotion, reload, and exhaustion is a narrated canonical event; the live status view shows the current day, the active anchor, and attempts remaining so the operator can watch the retry loop work.

**Why this priority**: Diagnosis is a constitution principle and the events come nearly free once the loop exists, but the mode is playable without view polish.

**Independent Test**: After a triggered retry, read the event stream and status view and confirm they show the day, the anchor used, the attempt number, and the reflection outcome.

**Acceptance Scenarios**:

1. **Given** a day that retried once, **When** the operator reads the run's narrated feed, **Then** each step — trigger reason, proposal outcome, promoted candidate, save reloaded, attempts remaining — appears in plain language.
2. **Given** a mid-day run, **When** the status view renders, **Then** it identifies the current day, the active anchor save, and reloads remaining.

---

### Edge Cases

- **No autosave anchor exists** (autosaves disabled, interval longer than a day, or none detected yet): the reflection pass still runs so future days benefit, but no reload occurs and the attempt is not spent; the gap is recorded as an event.
- **Anchor is stale** — the newest detected autosave predates the current day beyond a configured age: treated as no anchor for retry purposes.
- **Reload dispatch fails or the save is missing/corrupt**: the attempt is spent (prevents infinite retry), the failure is recorded, and play continues.
- **The anchor autosave already contains a failing state**: retries exhaust naturally after two reloads and the day is accepted.
- **Reflection pass takes real time**: the game is paused for the evolve-and-reload sequence so in-game time does not advance while the model deliberates.
- **Process crash mid-retry**: the day session record is durable state; a restarted run resumes with the recorded attempt count rather than resetting the budget.
- **Mutation budget**: reflection calls during fast-evolve are bounded per day, separately from any per-run reflection budget.
- **Determinism**: the mode is exercisable against the simulated backend with an injected reflection response, producing identical event streams for identical inputs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-2101**: A `fastevolve` run mode MUST be selectable as a play option at game load: a mode flag on the run command and a non-default play-option control on the launcher setup screen. Scored episodes MUST refuse the mode (named error); the mode itself keeps fair protections on (debug-class methods stay refused — only save/load is additionally permitted); it is never a default.
- **FR-2102**: The mode MUST track the in-game day from observed state and maintain a durable per-day session record (current day, active anchor, reloads used, exhausted flag) that survives process restarts and post-reload state reinitialization.
- **FR-2103**: The mode MUST discover retry anchors by enumerating the game's save list at a bounded cadence and matching save names against a pack-configured autosave pattern; the anchor for a day is the detected autosave nearest that day's start — a later mid-day autosave does not displace it.
- **FR-2104**: Day-failure triggers MUST evaluate per poll from two declared sources: pack colony-level predicates over observed state, and (optionally, pack-controlled) the existing goal-level failure/near-failure trigger set. All trigger policy MUST be pack data.
- **FR-2112**: Evolve passes in this mode MUST be failure-triggered only — a day with no failure trigger produces no reflection call (general cadence reflection remains the existing live-mutate machinery's job, not this mode's).
- **FR-2105**: On a trigger with reload budget remaining, the mode MUST: pause the game; run a bounded reflection pass over the failure evidence; promote any gated candidate pack immediately (mid-run promotion with parent backup and lineage recorded); reload the day-start anchor save; reinitialize run state (task namespaces tombstoned, planning state wiped, goals re-derived from observed colony); and resume play.
- **FR-2106**: A day MUST allow at most the configured number of reloads (default 2 → three total attempts). A further trigger on the final attempt MUST record the day as exhausted and continue without reloading — but the reflection pass still runs (bounded by the per-day pass budget), so the failure still improves the pack; the most recently promoted pack remains active.
- **FR-2107**: Save/load operations MUST be permitted only within this mode and only through the single-writer dispatch path; all other run modes MUST keep refusing them, and debug-class methods MUST remain refused under fast-evolve.
- **FR-2108**: Mid-run candidate promotion MUST preserve pack-integrity guarantees: the promoted pack is reloaded through the normal load path (re-binding its hash so drift detection stays intact), a parent backup is recorded, and the lineage log gains an entry marked as a mid-run promotion.
- **FR-2109**: The mode MUST emit canonical events for day rollover, trigger, reflection outcome, promotion, reload, exhaustion, and missing-anchor conditions, narrated to the feed; the status view MUST expose current day, active anchor, and reloads remaining.
- **FR-2110**: The retry policy surface — reload budget, autosave pattern, save-scan cadence, maximum anchor age, pause-during-evolve behavior, trigger selection and predicates, and per-day reflection budget — MUST be pack data, not code constants.
- **FR-2111**: The mode MUST be exercisable end-to-end on the deterministic simulated backend (including simulated save/load and autosave listing) with an injected reflection response, producing identical event streams for identical inputs.

### Key Entities

- **Day session**: the per-day retry record — in-game day number, active anchor save name, reloads used, exhausted flag; durable across reloads and restarts.
- **Retry anchor**: a detected autosave (name + detection day) identifying the save the current day rewinds to.
- **Evolve attempt**: one trigger → reflection → (optional) promotion → reload cycle within a day, recorded with its outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-2101**: Under any failure pattern, a single in-game day produces at most the configured number of reloads (default 2); a third trigger always advances without reloading.
- **SC-2102**: Every reload restores the recorded day-start anchor save — the game state after reload corresponds to that save in 100% of attempts.
- **SC-2103**: A triggered retry with a valid candidate results in the promoted pack being the policy in force for the replayed day, with a recorded parent backup enabling manual rollback.
- **SC-2104**: Zero debug-class operations occur during a fast-evolve run — the mode changes no fairness invariant other than permitting save/load.
- **SC-2105**: Every retry sequence is fully reconstructible from the event stream: trigger reason, reflection outcome, promoted candidate, anchor name, and attempt number are all recorded.
- **SC-2106**: Selecting the option on an incompatible (fair/scored) run fails at launch with a named error 100% of the time — never mid-run.

## Assumptions

- The game's save list enumerates autosaves by name, and autosave file naming follows a configurable pattern (default matches common "autosave" naming); players whose autosave cadence exceeds one day get evolve-without-reload behavior on anchorless days.
- Mid-run pack promotion is acceptable in this mode because fast-evolve runs are never scored episodes; the promotion mechanics, parent backup, and lineage format are shared with the existing boundary-promotion path.
- The mode implies the live-reflection machinery (reflection pass state, trigger scan, candidate gate) — it is an extension of that pipeline, not a parallel one.
- RimWorld autosave frequency is a game setting outside runtime control; the feature detects autosaves rather than creating them.
- A reload followed by state reinitialization reuses the same full-wipe semantics as the existing brain-swap path — goals re-derive from the colony as observed after the reload.
- A reload resets run/planning state but not the day's failure history: the reflection pass on a retry sees cumulative evidence from all attempts within the current day.
