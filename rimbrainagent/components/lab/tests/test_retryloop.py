"""Checkpoint-retry loop tests (feature 003, T053; FR-201..210, SC-201..205).

All offline via SimBridge + ManualClock -- no game, bridge server, or network.
Covers:

- early_exit at iteration N < max_retries (SC-202);
- exhausted at the retry cap and at mutation-space exhaustion (SC-204);
- exactly one mutation per retry + invalid-mutation rejection with the prior
  revision kept (FR-204);
- checkpoint tick/day equality after reload, and abort on mismatch
  (SC-201, FR-210);
- scored-episode hard rejection -- flag and status-reported (FR-208);
- per-window and total budget aborts (FR-207);
- emitted retry.* envelopes validate against the envelope schema and the
  strict consumer (payload schemas + native event-map registration);
- fixture export round-trips through lab.fixtures (FR-209, SC-203);
- deterministic repeated runs produce byte-identical event streams.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]

from lab import fixtures  # noqa: E402
from lab.bridge import ManualClock, SimBridge  # noqa: E402
from lab.gate import GateError, evaluate  # noqa: E402
from lab.mutations import MutationSpace, apply_mutation  # noqa: E402
from lab.retryfixture import export_fixture  # noqa: E402
from lab.retryloop import RetryConfigError, load_config, run_loop  # noqa: E402

from contracts import canonical_bytes, eventmap  # noqa: E402

EXAMPLE_CONFIG = REPO_ROOT / "configs" / "retryloop.example.yaml"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _config(**over) -> dict:
    cfg = {
        "schema_version": 0,
        "config_id": "rl.test-001",
        "window_ticks": 2500,
        "max_retries": 4,
        "speed": 3,
        "checkpoint_family": "retry",
        "gate_ref": "gate.test",
        "mutation_space_ref": "muts.test",
        "budgets": {"per_window_s": 120, "total_s": 3600},
        "gate": {
            "combinator": "all",
            "predicates": [
                {"id": "stock", "field": "colony.stock", "op": "gte", "value": 100}
            ],
        },
        "mutation_space": [
            {"id": f"m{i}", "apply": {"path": "plan.x", "op": "set", "value": i}}
            for i in range(4)
        ],
        "candidate": {"plan": {"x": 0, "name": "base"}},
    }
    cfg.update(over)
    return cfg


def _sim(state: dict | None = None, **kw) -> SimBridge:
    base = {"state": "playing", "tick": 60000, "day": 1, "colony": {"stock": 40}}
    base.update(state or {})
    return SimBridge(state=base, **kw)


def _events_of(result: dict, event_type: str) -> list[dict]:
    return [e for e in result["events"] if e["event_type"] == event_type]


def _gate_passes_on(window: int):
    """on_advance hook: gate field satisfies the predicate from window N on."""

    def hook(state: dict, ticks: int, call_index: int) -> None:
        if call_index >= window:
            state["colony"]["stock"] = 150

    return hook


# ---------------------------------------------------------------------------
# gate unit tests (T049)
# ---------------------------------------------------------------------------


def test_gate_all_ops_and_combinators():
    state = {"a": 5, "b": "hello world", "c": [1, 2, 3], "d": {"k": 1}}
    for op, field, value, met in [
        ("eq", "a", 5, True),
        ("ne", "a", 6, True),
        ("gt", "a", 4, True),
        ("gte", "a", 5, True),
        ("lt", "a", 6, True),
        ("lte", "a", 5, True),
        ("lt", "a", 5, False),
        ("contains", "b", "world", True),
        ("contains", "c", 2, True),
        ("contains", "d", "k", True),
        ("contains", "a", 5, False),
    ]:
        verdict = evaluate(
            {"predicates": [{"id": "p", "field": field, "op": op, "value": value}]},
            state,
        )
        assert verdict["passed"] is met, (op, field, value)
        assert verdict["early_exit"] is met
        assert verdict["predicates"][0]["met"] is met


def test_gate_any_combinator_and_missing_field():
    state = {"a": 5}
    verdict = evaluate(
        {
            "combinator": "any",
            "predicates": [
                {"id": "missing", "field": "nope", "op": "eq", "value": 1},
                {"id": "hit", "field": "a", "op": "gte", "value": 5},
            ],
        },
        state,
    )
    assert verdict["passed"] is True
    assert verdict["predicates"][0]["observed"] is None
    assert verdict["predicates"][0]["met"] is False
    # 'all' over the same predicates fails on the missing field
    verdict = evaluate(
        {
            "combinator": "all",
            "predicates": [
                {"id": "missing", "field": "nope", "op": "eq", "value": 1},
                {"id": "hit", "field": "a", "op": "gte", "value": 5},
            ],
        },
        state,
    )
    assert verdict["passed"] is False


def test_gate_rejects_malformed_definition():
    with pytest.raises(GateError):
        evaluate({"combinator": "all", "predicates": []}, {})
    with pytest.raises(GateError):
        evaluate({"predicates": [{"id": "p", "field": "a", "op": "eq"}]}, {"a": 1})
    with pytest.raises(GateError):
        evaluate({"combinator": "xor", "predicates": [{"id": "p", "field": "a", "op": "eq", "value": 1}]}, {"a": 1})


# ---------------------------------------------------------------------------
# mutation unit tests (T050)
# ---------------------------------------------------------------------------


def test_mutation_set_bump_swap():
    cand = {"plan": {"x": 1, "items": ["a", "b", "c"]}}
    new, err = apply_mutation(cand, {"id": "m", "apply": {"path": "plan.y", "op": "set", "value": 9}})
    assert err is None and new["plan"]["y"] == 9 and "y" not in cand["plan"]
    new, err = apply_mutation(cand, {"id": "m", "apply": {"path": "plan.x", "op": "bump", "value": 4}})
    assert err is None and new["plan"]["x"] == 5 and cand["plan"]["x"] == 1
    new, err = apply_mutation(cand, {"id": "m", "apply": {"path": "plan.items", "op": "swap", "value": [0, 2]}})
    assert err is None and new["plan"]["items"] == ["c", "b", "a"]


def test_mutation_invalid_applies_rejected_unchanged():
    cand = {"plan": {"x": 1, "name": "base", "items": ["a"]}}
    bad_applies = [
        {"path": "plan.name", "op": "bump", "value": 1},       # non-numeric leaf
        {"path": "plan.missing", "op": "bump", "value": 1},    # missing leaf
        {"path": "plan.name", "op": "swap", "value": [0, 1]},  # non-list target
        {"path": "plan.items", "op": "swap", "value": [0, 9]}, # out of range
        {"path": "plan.x", "op": "frobnicate", "value": 1},    # unknown op
        {"path": "", "op": "set", "value": 1},                 # empty path
    ]
    for apply in bad_applies:
        new, err = apply_mutation(cand, {"id": "bad", "apply": apply})
        assert err is not None and err["code"] == "mutation.invalid", apply
        assert new == cand  # prior revision kept
    # missing apply / id entirely
    new, err = apply_mutation(cand, {"id": "bad"})
    assert err is not None
    new, err = apply_mutation(cand, {"apply": {"path": "plan.x", "op": "set", "value": 1}})
    assert err is not None


def test_mutation_space_pops_one_per_retry_then_exhausted():
    space = MutationSpace([{"id": "a", "apply": {}}, {"id": "b", "apply": {}}])
    assert space.remaining == 2
    assert space.next() == (0, {"id": "a", "apply": {}})
    assert space.next() == (1, {"id": "b", "apply": {}})
    assert space.next() is None and space.exhausted


# ---------------------------------------------------------------------------
# engine: early exit / exhaustion / mutations (FR-203, FR-204, SC-202, SC-204)
# ---------------------------------------------------------------------------


def test_early_exit_on_first_window():
    clk = ManualClock()
    sim = _sim(clock=clk, on_advance=_gate_passes_on(1))
    result = run_loop(_config(), sim, clock=clk)
    assert result["ok"] is True
    assert result["outcome"] == "early_exit"
    assert result["reason"] == "gate_passed"
    assert len(result["iterations"]) == 1
    assert sim.advance_calls == 1
    # no reloads, no mutations when the first window passes
    assert _events_of(result, "retry.mutation.applied") == []
    assert len(sim.saves) == 1


def test_early_exit_at_iteration_n_below_cap():
    clk = ManualClock()
    sim = _sim(clock=clk, on_advance=_gate_passes_on(3))
    result = run_loop(_config(max_retries=4), sim, clock=clk)
    assert result["outcome"] == "early_exit"
    assert len(result["iterations"]) == 3
    # one mutation popped per retry (retries = iterations - 1)
    mutations = _events_of(result, "retry.mutation.applied")
    assert len(mutations) == 2
    assert [m["payload"]["mutation_id"] for m in mutations] == ["m0", "m1"]
    loop = _events_of(result, "retry.loop.completed")[0]
    assert loop["payload"]["outcome"] == "early_exit"
    assert loop["payload"]["iterations"] == 3
    assert loop["payload"]["mutations_applied"] == 2


def test_exhausted_at_retry_cap():
    clk = ManualClock()
    sim = _sim(clock=clk)  # gate never passes (stock stays 40 < 100)
    result = run_loop(_config(max_retries=2), sim, clock=clk)
    assert result["ok"] is True
    assert result["outcome"] == "exhausted"
    assert result["reason"] == "max_retries"
    assert len(result["iterations"]) == 3  # 1 initial + 2 retries
    assert sim.advance_calls == 3
    assert len(_events_of(result, "retry.mutation.applied")) == 2
    assert all(i["verdict"] == "failed" for i in result["iterations"])


def test_exhausted_by_mutation_space_before_cap():
    cfg = _config(
        max_retries=4,
        mutation_space=[{"id": "only", "apply": {"path": "plan.x", "op": "set", "value": 1}}],
    )
    clk = ManualClock()
    sim = _sim(clock=clk)
    result = run_loop(cfg, sim, clock=clk)
    assert result["outcome"] == "exhausted"
    assert result["reason"] == "mutation_space_exhausted"
    assert len(result["iterations"]) == 2  # initial + the one available retry


def test_exactly_one_mutation_per_retry_and_invalid_rejected():
    cfg = _config(
        max_retries=3,
        mutation_space=[
            {"id": "good", "apply": {"path": "plan.x", "op": "bump", "value": 5}},
            {"id": "bad", "apply": {"path": "plan.name", "op": "bump", "value": 1}},
            {"id": "good2", "apply": {"path": "plan.x", "op": "bump", "value": 7}},
        ],
    )
    clk = ManualClock()
    sim = _sim(clock=clk)
    result = run_loop(cfg, sim, clock=clk)
    assert result["outcome"] == "exhausted"  # space exhausted after 3 retries
    mutations = _events_of(result, "retry.mutation.applied")
    assert len(mutations) == 3
    payloads = [m["payload"] for m in mutations]
    assert [p["applied"] for p in payloads] == [True, False, True]
    assert payloads[1]["mutation_id"] == "bad"
    assert payloads[1]["error"]["code"] == "mutation.invalid"
    # invalid mutation kept the prior revision: good(+5) then good2(+7) -> 12
    assert result["candidate"]["plan"]["x"] == 12
    assert result["candidate"]["plan"]["name"] == "base"


# ---------------------------------------------------------------------------
# checkpoint isolation + reload verification (FR-206, FR-210, SC-201)
# ---------------------------------------------------------------------------


def test_checkpoint_namespaced_and_reload_returns_tick_day():
    clk = ManualClock()
    sim = _sim(clock=clk)
    sim.save("user-save-1")  # pre-existing user save must be untouched
    result = run_loop(_config(max_retries=2), sim, clock=clk)
    assert result["checkpoint"]["save_name"] == "retry--run.test-001--cp0"
    # every checkpoint save is inside the family namespace
    assert all(n.startswith("retry--") for n in sim.saves if n != "user-save-1")
    assert "user-save-1" in sim.saves
    # each window started from the checkpoint tick/day (verified on reload)
    for event in _events_of(result, "retry.window.started"):
        assert event["payload"]["start_tick"] == 60000
        assert event["payload"]["start_day"] == 1
    # sim restored the checkpoint exactly: window ticks re-advance from 60000
    for event in _events_of(result, "retry.iteration.completed"):
        assert event["payload"]["tick_start"] == 60000
        assert event["payload"]["tick_end"] == 62500


def test_reload_state_mismatch_aborts():
    def corrupt(state: dict, name: str) -> None:
        state["tick"] += 1

    clk = ManualClock()
    sim = _sim(clock=clk, on_load=corrupt)
    result = run_loop(_config(max_retries=2), sim, clock=clk)
    assert result["ok"] is False
    assert result["outcome"] == "aborted"
    assert result["reason"] == "reload_state_mismatch"
    assert result["error"]["code"] == "retry.reload.state_mismatch"
    loop = _events_of(result, "retry.loop.completed")[0]
    assert loop["payload"]["outcome"] == "aborted"
    assert loop["payload"]["reason"] == "reload_state_mismatch"


def test_checkpoint_load_failure_aborts():
    sim = _sim()

    def fail_load(name: str) -> dict:
        return {"ok": False, "error": {"code": "sim.load.fail", "message": "nope", "retryable": False}}

    sim.load = fail_load  # type: ignore[method-assign]
    result = run_loop(_config(max_retries=2), sim, clock=ManualClock())
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.checkpoint.load_failed"
    assert result["reason"] == "bridge_error"


# ---------------------------------------------------------------------------
# guards + budgets (FR-207, FR-208, SC-204, SC-205)
# ---------------------------------------------------------------------------


def test_scored_episode_flag_hard_rejects():
    sim = _sim()
    result = run_loop(_config(), sim, scored_episode_active=True, clock=ManualClock())
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.scored_episode_active"
    assert result["events"] == [] and result["iterations"] == []
    assert sim.saves == {}  # no checkpoint written -- fail closed


def test_scored_episode_reported_by_status_hard_rejects():
    sim = _sim(state={"scored_episode_active": True})
    result = run_loop(_config(), sim, clock=ManualClock())
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.scored_episode_active"
    assert sim.saves == {}


def test_not_playing_state_rejects():
    sim = _sim(state={"state": "menu"})
    result = run_loop(_config(), sim, clock=ManualClock())
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.game.not_playing"


def test_per_window_budget_abort():
    clk = ManualClock()
    sim = _sim(clock=clk, wall_per_window_s=30.0)
    cfg = _config(budgets={"per_window_s": 10, "total_s": 3600})
    result = run_loop(cfg, sim, clock=clk)
    assert result["ok"] is False
    assert result["outcome"] == "aborted"
    assert result["error"]["code"] == "retry.budget.per_window"
    assert result["reason"] == "budget_per_window"
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["verdict"] == "aborted"


def test_total_budget_abort():
    clk = ManualClock()
    sim = _sim(clock=clk, wall_per_window_s=30.0)
    cfg = _config(budgets={"per_window_s": 100, "total_s": 25})
    result = run_loop(cfg, sim, clock=clk)
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.budget.total"
    assert result["reason"] == "budget_total"


def test_missing_embedded_gate_rejected():
    cfg = _config()
    del cfg["gate"]
    result = run_loop(cfg, _sim(), clock=ManualClock())
    assert result["ok"] is False
    assert result["error"]["code"] == "retry.config.gate_unresolved"


# ---------------------------------------------------------------------------
# canonical events (FR-205)
# ---------------------------------------------------------------------------


def test_emitted_events_validate_against_contracts():
    clk = ManualClock()
    sim = _sim(clock=clk, on_advance=_gate_passes_on(2))
    result = run_loop(_config(max_retries=4), sim, clock=clk)
    types = [e["event_type"] for e in result["events"]]
    assert types == [
        "retry.checkpoint.saved",
        "retry.window.started",
        "retry.gate.evaluated",
        "retry.iteration.completed",
        "retry.mutation.applied",
        "retry.window.started",
        "retry.gate.evaluated",
        "retry.iteration.completed",
        "retry.loop.completed",
    ]
    for envelope in result["events"]:
        assert envelope["event_id"].startswith("evt.retry-")
        assert envelope["episode_id"] is None  # never fabricated
        assert eventmap.validate_envelope(envelope) == []
        verdict = eventmap.consume_strict(envelope)
        assert verdict["ok"] is True, verdict
    # sequence is strictly increasing, contiguous
    assert [e["sequence"] for e in result["events"]] == list(
        range(1, len(result["events"]) + 1)
    )
    # correlation chains each event to its predecessor
    assert result["events"][0]["correlation"] == {"parent_event": None}
    assert result["events"][1]["correlation"]["parent_event"] == "evt.retry-000001"


def test_deterministic_repeated_runs_identical():
    blobs = []
    for _ in range(2):
        clk = ManualClock()
        sim = _sim(clock=clk, on_advance=_gate_passes_on(3))
        result = run_loop(_config(max_retries=4), sim, clock=clk)
        blobs.append(canonical_bytes(result["events"]))
    assert blobs[0] == blobs[1]


# ---------------------------------------------------------------------------
# fixture export (T052; FR-209, SC-203)
# ---------------------------------------------------------------------------


def test_fixture_export_replays_through_us5_harness(tmp_path):
    clk = ManualClock()
    sim = _sim(clock=clk, on_advance=_gate_passes_on(2))
    result = run_loop(_config(max_retries=4), sim, clock=clk)
    dest = export_fixture(result, tmp_path / "fix.retry-test-001")
    report, blob = fixtures.run_fixture(dest)
    assert report["status"] == "ok", report["defects"]
    assert report["fixture_id"] == "fix.retry-test-001"
    assert report["mode"] == "field-subset"
    assert report["records"]["input"] == len(result["events"])
    assert report["comparison"]["counts"]["equivalent"] == len(result["events"])
    # deterministic export: same run exports byte-identical members
    dest2 = export_fixture(result, tmp_path / "fix.retry-test-002")
    for name in ("input.jsonl", "expected.jsonl", "run.json"):
        assert (dest / name).read_bytes() == (dest2 / name).read_bytes()
    # attribution: run.json answers which mutation produced which verdict
    run_doc = json.loads((dest / "run.json").read_text(encoding="utf-8"))
    assert run_doc["outcome"] == "early_exit"
    assert run_doc["iterations"][1]["mutation_id"] == "m0"


def test_exported_fixture_detects_tamper(tmp_path):
    clk = ManualClock()
    sim = _sim(clock=clk)
    result = run_loop(_config(max_retries=1), sim, clock=clk)
    dest = export_fixture(result, tmp_path / "fix.retry-tamper")
    lines = (dest / "expected.jsonl").read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    last["payload"]["outcome"] = "early_exit"  # was 'exhausted'
    import hashlib

    new_bytes = ("\n".join(lines[:-1] + [json.dumps(last, sort_keys=True)]) + "\n").encode()
    (dest / "expected.jsonl").write_bytes(new_bytes)
    manifest_path = dest / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["expected.jsonl"] = hashlib.sha256(new_bytes).hexdigest()
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "diverged"


# ---------------------------------------------------------------------------
# config contract (T046) + CLI
# ---------------------------------------------------------------------------


def test_example_config_validates_against_schema():
    config = load_config(EXAMPLE_CONFIG)
    assert config["config_id"] == "rl.example-colony-001"
    assert "window_hours" in config and "window_ticks" not in config


def test_config_rejects_window_xor_violation(tmp_path):
    bad = _config(window_hours=2)  # both window fields set
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(RetryConfigError):
        load_config(path)


def test_config_rejects_missing_required(tmp_path):
    bad = _config()
    del bad["max_retries"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(RetryConfigError):
        load_config(path)


def test_cli_sim_mode(tmp_path, capsys):
    env_src = REPO_ROOT / "components" / "lab" / "src"
    assert str(env_src) in sys.path
    from lab.retryloop import main

    export_dir = tmp_path / "fix.retry-example"
    rc = main(
        [
            "--config", str(EXAMPLE_CONFIG),
            "--mode", "sim",
            "--export", str(export_dir),
        ]
    )
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["outcome"] == "early_exit"  # sim effect stocks up on window 2
    report, _ = fixtures.run_fixture(export_dir)
    assert report["status"] == "ok"


def test_restores_pre_run_speed_and_pause():
    """T056: loop leaves the game at the pre-run speed/pause, not loop speed."""
    bridge = _sim({"speed": 1, "paused": True}, wall_per_window_s=1.0)
    clock = ManualClock(0.0)
    cfg = _config(
        speed=3, max_retries=2, window_ticks=100,
        budgets={"per_window_s": 10, "total_s": 100},
        gate={"combinator": "all",
              "predicates": [{"id": "ok", "field": "colony.stock",
                              "op": "gte", "value": 40}]})
    res = run_loop(cfg, bridge, clock=clock)
    assert res["ok"] and res["outcome"] == "early_exit"
    cur = bridge.status()["result"]
    assert cur["speed"] == 1 and cur["paused"] is True
