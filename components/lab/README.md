# rimbrainagent-lab

Future `rimbrainagent-lab` submodule for export, replay, evaluation, calibration, and benchmarks. Build specification: [Lab](../../specs/20-submodules/LAB.md).

Current contents: the replayable fixture harness (`src/lab/fixtures.py`, US5 / FR-010–FR-012 / SC-005) implementing `specs/001-fork-bootstrap-contracts/contracts/fixture-package.md`, and the checkpoint-reload retry loop (feature 003, `specs/003-checkpoint-retry`; debug/eval mode only - forbidden during scored episodes, FR-208).

```powershell
# replay a fixture package (deterministic JSON report)
python -m lab.fixtures tests/fixtures/fix.seed-001 --report report.json

# checkpoint-retry loop, offline deterministic sim (needs lab/src on PYTHONPATH)
$env:PYTHONPATH = "components/lab/src;components/contracts/src"
python -m lab.retryloop --config configs/retryloop.example.yaml --mode sim --export out/fix.retry-example

# live mode (manual gate; needs the game + zorrobyte bridge on :8765)
python -m lab.retryloop --config configs/retryloop.example.yaml --mode live

# run the harness + retry-loop tests
uv run --with pytest,pyyaml,jsonschema pytest components/lab/tests -q
```

Retry-loop modules: `bridge.py` (GameCtl: `LiveBridge` HTTP + `SimBridge` in-memory deterministic fake), `gate.py` (`{field, op, value}` state predicates, `all|any`, early exit), `mutations.py` (ordered `set|bump|swap` space, one pop per retry, invalid applies keep the prior revision), `retryloop.py` (engine + CLI: namespaced `retry--<run_id>--cp<N>` checkpoints verified via `game.list_saves`, canonical `retry.*` envelope events, hard `max_retries`/wall-clock bounds, reload tick/day verification), `retryfixture.py` (US5 fixture-package export: manifest + `input.jsonl` + `expected.jsonl` + `run.json`, sha256-pinned).

Fixture corpus lives in `tests/fixtures/` at the repo root (`fix.seed-001`, `fix.max-001`, `fix.corrupt-001`, `fix.baseline-001`). The harness consumes the sibling `components/contracts` package when importable (envelope schema validation and upstream `kind` -> envelope wrapping); envelope-shaped inputs also work with PyYAML alone.
