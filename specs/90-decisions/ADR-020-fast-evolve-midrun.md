# ADR-020: Fast-evolve play mode — mid-run promotion + scoped save/load grant

**Status:** ACCEPTED
**Date:** 2026-09-24
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** UR-BRN-004/005/006 (immutability, proposal-only models, atomic activation with rollback lineage); UR-CTL-009 (fair runs refuse dev + save/load); specs/021-fast-evolve; ADR-017, ADR-018, ADR-019

## Context

Feature 021 adds a `fastevolve` play mode: each in-game day anchors to the
day-start autosave; on a day-failure trigger the run pauses, reflects, and
save-scum reloads the day under an evolved pack (max 2 reloads/day). Two
existing rules collide:

1. ADR-018: "the active pack file is write-never during a run" — candidates
   promote only at the next run's boundary. A day retry needs the evolved
   pack *now*, not next run.
2. UR-CTL-009 / ADR-017: fair runs refuse `game.save`/`game.load` dispatches.
   The retry loop is built on save/load.

## Decision drivers

- `--dev` unlocks the whole debug surface (`dev.*` spawn tooling, god mode)
  — far broader than two save/load methods; a narrower grant is needed.
- Bypassing the dispatcher with raw `game.rpc` calls would break the
  single-writer invariant (Principle II) and lose `action.*` evidence.
- Mid-run promotion must not weaken `dispatch.pack_drift`: after install,
  `load_pack` rebinds the recorded hash so drift detection stays sound.
- Fast-evolve runs are never scored episodes — the "policy immutable during
  scored episodes" invariant (Principle V) is not engaged; each reload is
  itself a boundary (full state wipe, fresh-eyes reinit) that legitimizes a
  policy swap.

## Options considered

### Option A — Boundary promotion only; retry under the same pack

Rejected: defeats the feature — the point is retrying the day under the
evolved brain.

### Option B — `--dev` mode for fast-evolve

Rejected: opens the entire debug surface; hides the distinction between
"save/load allowed" and "dev tooling allowed"; scored-adjacent leakage.

### Option C — Scoped `allow_save_load` grant + mid-run promote (chosen)

`Dispatcher(allow_save_load=True)` bypasses only the `game.save`/`game.load`
half of `dispatch.fair_mode`; `dev.*` refusal, pack-class load check, and
params validation unchanged. `evolve.promote_candidate(mid_run=True)`
factors the install half of `boundary()` — same gate, same lineage, marked
`mid_run: true` — and `load_pack` rebinds the hash post-install. The
episode-score auto-revert still applies at the next run boundary.

## Decision

**Option C.** Save/load is a scoped dispatcher grant set only by
`--mode fastevolve`; no pack content can enable it. Mid-run promotion
reuses the feature-016/017 gate + lineage machinery, diverging from ADR-018
only in *when* install happens (per retry boundary, not per run boundary).
Every reload is recorded (`fastevolve.reloaded`, attempt rows in
`state/fastevolve.json`, lineage rows in `state/mutations.jsonl`).

## Consequences

### Positive

- Fair-class guarantees survive: mutations still can't introduce `dev.*`,
  packs still fail-closed at load, drift detection intact after rebind.
- One candidate format + one lineage log + one gate across boundary and
  mid-run paths.
- Each retry is honest evidence: the lineage shows which pack ran which
  attempt.

### Negative / risks

- The pack file is writable mid-run in this mode — operators editing packs
  concurrently must expect promotion to overwrite (same caveat as ADR-018's
  boundary install).
- A bad-but-valid mutation can win a retry by luck (RimWorld RNG) — the
  exhaustion path bounds this to 3 attempts/day and the next boundary's
  score-revert still applies.
- Save-scum semantics mean the mode is inherently unscored; any future
  scored-episode flag must refuse combination at launch.

## Verification

`test_fastevolve.py`: grant refuses `dev.*` while permitting save/load;
mid-run promotion rebinds hash (no `pack_drift`); lineage rows carry
`mid_run: true`; exhaustion honors the budget; sim path is deterministic.
