# Phase 0 Research: Guided Launcher UI

All NEEDS CLARIFICATION items were resolved in operator discussion 2026-09-24
(recorded in spec.md "Design decisions"). This file documents the technical
choices that follow from them.

## R1. Who owns the loop process — overlay as supervisor

**Decision**: The overlay spawns and owns the loop child. `rimbrain run` (no
args) spawns the overlay in setup mode and returns; GO →
`subprocess.Popen(RIMBRAIN_LOOP_CMD + assembled_argv)`.

**Rationale**: Gives Stop/Restart/exit-detection and menu re-entry for free —
the window already polls on a timer, so `proc.poll()` rides the same cadence.
The alternative (parent owns loop, menu→GO via a new `state/launch.request`
file handshake) adds a second channel plus a kill channel for no benefit.

**Alternatives considered**: File-handshake supervisor (rejected: extra
channels, harder restart semantics); web UI on :8771 (rejected: new
process-spawn machinery, browser dependency, second UI stack).

## R2. Loop spawn mechanics — `RIMBRAIN_LOOP_CMD`

**Decision**: `rimbrain.py` exports `RIMBRAIN_LOOP_CMD` — a JSON-encoded argv
prefix — when spawning the overlay. Frozen: `["rimbrain.exe", "loop"]`.
Dev: `["python", "-m", "runtime", "loop"]` (PYTHONPATH already extended).
Overlay does `json.loads` + appends flag args. Unset (standalone overlay) →
GO disabled with an explanatory label.

**Rationale**: One env var, no new CLI surface, identical frozen/dev behavior.
A JSON argv array avoids Windows command-line quoting pitfalls.

## R3. Live brain verification — `api.probe_live(role)`

**Decision**: New facade entry. Resolve `role` offline via
`bindings.resolve_role()` → `resolved.{endpoint_id, model, api}` → one
role-shaped call:

- `api == "systemone"` → `probe._decide_probe(url, key, model)` — already
  posts a real typed question; reuse as-is.
- `api == "openai-compat"` → `POST {base}/chat/completions` with
  `{model, messages:[{role:"user","content":"ping"}], max_tokens:1}`.
  `client.openai_compat_chat` does not expose `max_tokens`; probe.py builds
  the payload via `client._post_json` (both are runtime internals — legal
  inside the component, unlike `extra_body` which strict endpoints strip).
- `resolved.kind == "fallback"` → verdict `fallback_only`, no call.

**Verdict vocabulary**: `answered` (live call ok + latency), `model_failed`
(listing reachable, live call failed — distinguish HTTP status vs transport),
`unreachable`, `missing_secret`, `fallback_only`. Result also carries
`endpoint`, `model`, `latency_ms`, `fallbacks` (the role's `degraded_paths`
verbatim) for display.

**Rationale**: FR-007 requires proving the bound model answers, not just
that the endpoint lists. `max_tokens:1` keeps cost ~$0; `systemone` gets a
real decide call for free. Timeouts reuse probe.py's (5s TCP / 10s HTTP).

**Alternatives considered**: Listing-only probe (rejected — proves nothing
about the call path); extend `openai_compat_chat` with `max_tokens`
(acceptable alternative; probe-local payload chosen to keep client surface
stable).

## R4. Editor save path — `api.validate_pack_doc(doc)`

**Decision**: New facade entry running `templates.validate_pack(doc)` +
`policy.validate_policy(doc)` (when `policy_version` present) +
sealed-inventory method check — the identical sequence `load_pack` applies —
returning `{ok, issues[]}` or an error envelope.

**Rationale**: FR-018 demands loader-identical validation, and the dashboard
boundary forbids importing `templates`/`policy` directly. One facade entry
keeps the checks in one place — the same place the loader uses them.

**Alternatives considered**: Save-then-brain-reset and read `brain_status`
(rejected: async, mutates the live run to discover an invalid file);
dashboard-side reimplementation (rejected: duplicated validation drift).

## R5. Guided editor document model

**Decision**: `packedit.py` loads the pack via `yaml.safe_load`, presents an
outline keyed to v0 paths with unified-phase-vocabulary labels
(`start.phases`→"Phases", `emergency`→"Reflexes", `universal.rules`→"Rules",
`govern.goals`→"Standing goals"), edits the in-memory doc through form→doc
writes, validates via `validate_pack_doc`, then `yaml.safe_dump` to
`packs/<name>/pack.yaml` with `pack_id`/`derived_from` set.

**Rationale**: Forms over a real doc object means every edit is
schema-shaped by construction; the v0→v1 label map is a small table that
swaps when feature 017's loader migration lands.

**Alternatives considered**: `ruamel.yaml` comment-preserving round-trip
(rejected: new dependency; save-as-new means the commented source survives
regardless — comments inside the *copy* are best-effort, accepted in spec
assumptions); text-patching the source file (rejected: brittle).

## R6. Parameter grid — declarative `PARAM_SPEC`

**Decision**: `paramspec.py` holds a table: `{flag, label, kind
(check|radio|spin|text|choice), default, group, hint, enable_when,
block_when}`. Widget generation, argv assembly, and constraint evaluation
all derive from it — one edit point when feature 017 reduces the flag
surface (FR-022 there).

**Constraint mirror** (from `loop.main` fail-closed checks):
`mode∈{live,start,combat,cycle} ⇒ --live`; `mode==cycle ⇒ fair off`;
`--live-mutate ⇒ mode∈{start,live}`; dev-class pack ⇒ fair off.
Violations render as blocked GO + reason, matching CLI error codes.

**Rationale**: FR-002/FR-004 — a table is testable without Tk and stays in
sync with the argparse surface by convention (single obvious place to edit).

## R7. Threading model

**Decision**: Tk mainloop never does network I/O. Brain checks run in a
`threading.Thread` per check batch; results post back via `queue.Queue` +
`after()` polling (same pattern as the existing refresh loop). Probes are
idempotent and read-only; re-check just enqueues again.

**Rationale**: FR-009 — OpenRouter round-trips take seconds; blocking the
mainloop would freeze the window.

## R8. Mid-run edit of the active pack

**Decision**: Editor offers "Save as new pack" (always) and, only when the
target is the *active* pack, "Overwrite + reset" behind a confirm — write
file then immediately post `brain_reset.request {}` so `load_pack`
re-reads; the drift window between write and reload is one poll.

**Rationale**: `dispatch.pack_drift` freezes the run between file change
and reload; pairing write+reset collapses it to ≈0, the supported hot-swap
per spec FR-024. Editing non-active packs never triggers drift.
