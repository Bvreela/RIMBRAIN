# Quickstart: validating feature 016

Prereq: `PYTHONPATH=components/runtime/src;components/contracts/src;components/dashboard/src` (or `python rimbrain.py`).

## 1. Unit suite

```powershell
python -m pytest components/runtime/tests/test_mutate.py -q
```

Covers: cadence counting (10 terminal goals → 1 pass), failure trigger, near-failure trigger, gate rejections (schema/stale/vacuous/invalid pack), boundary promote, regression revert, flag-off = zero mutation activity, rules-only degraded path.

## 2. Live run (fair, mutation on)

```powershell
python rimbrain.py run            # default args now include --live-mutate
# or explicitly:
python -m runtime loop --pack start-mode-v0 --mode start --live-flag --fair --live-brain --live-mutate --feed --iterations 2000
```

Watch `state/feed.md` for `mutation.triggered`/`proposed`/`candidate` narration; `state/planning.json` carries the `mutation` block (passes run, pending candidate, last verdict). `packs/candidates/cand-mut-*.yaml` collects proposals.

## 3. Boundary promotion

End the run; relaunch. Before `load_pack`, `mutate.boundary` installs the pending candidate over the resolved pack path (`packs/start-mode-v0/pack.yaml`; parent backed up to `candidates/parent-start-mode-v0-*.yaml`), emits `mutation.promoted`, and records lineage in `state/mutations.jsonl`.

## 4. Auto-revert

Force a regression (or seed a lineage row whose baseline beats the current episode score): next boundary restores the parent file and emits `mutation.reverted`. `git diff` on the pack file shows the round-trip.

## 5. Invariants to spot-check

- `state/events.jsonl` contains **zero** `dispatch.pack_drift` caused by mutation machinery (active pack file never written mid-run).
- `--mode sim` output unchanged; mutation code never runs without `--live-mutate`.
- A candidate proposing a `dev.*` method under `--fair` dies at the gate (`mutation.rejected`, gate `validation`).
