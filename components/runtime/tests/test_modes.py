"""Flag-matrix tests for the FR-1422 CLI surface (feature 017): every
(mode x game x flag) combination is either defined or fails closed.
Positive paths run --game sim (offline); live paths are rejected before
any bridge client is constructed."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import loop  # noqa: E402


def _run_cli(argv, capsys):
    rc = loop.main(argv)
    out = capsys.readouterr()
    body = out.out.strip().splitlines()
    return rc, (json.loads(body[-1]) if body else {}), out.err


def test_run_sim_is_the_default(tmp_path, monkeypatch, capsys):
    """--mode run --game sim works offline with zero flags."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(
        ["--pack", "core-survival-v0", "--iterations", "2",
         "--no-store"], capsys)
    assert rc == 0 and body["ok"]


def test_live_requires_confirmation(tmp_path, monkeypatch, capsys):
    """--game live without --live fails closed before the bridge."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(
        ["--mode", "run", "--game", "live"], capsys)
    assert rc == 2
    assert body["error"]["code"] == "loop.live_requires_confirmation"


def test_deprecated_sim_alias_warns_and_runs(tmp_path, monkeypatch,
                                             capsys):
    """--mode sim still works, warns, and maps to run+sim."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, err = _run_cli(
        ["--mode", "sim", "--pack", "core-survival-v0",
         "--iterations", "2", "--no-store"], capsys)
    assert rc == 0 and body["ok"]
    assert "deprecated" in err


def test_deprecated_start_alias_needs_live(tmp_path, monkeypatch,
                                           capsys):
    """--mode start maps to run --game live -> still needs --live."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(["--mode", "start"], capsys)
    assert rc == 2
    assert body["error"]["code"] == "loop.live_requires_confirmation"


def test_stage_combat_requires_dev(tmp_path, monkeypatch, capsys):
    """--stage combat executes dev tooling -> refused under fair."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(
        ["--mode", "run", "--game", "sim", "--stage", "combat"],
        capsys)
    assert rc == 2
    assert body["error"]["code"] == "loop.stage_requires_dev"


def test_cycle_requires_dev(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(["--mode", "cycle", "--live"], capsys)
    assert rc == 2
    assert body["error"]["code"] == "loop.cycle_requires_dev"


def test_cycle_fair_check_before_live_gate(tmp_path, monkeypatch,
                                           capsys):
    """Gate order: cycle's dev requirement fires regardless of --live."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(["--mode", "cycle"], capsys)
    assert rc == 2
    assert body["error"]["code"] in ("loop.cycle_requires_dev",
                                     "loop.live_requires_confirmation")


def test_live_mutate_requires_live_run(tmp_path, monkeypatch, capsys):
    """--live-mutate on a sim run fails closed."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(
        ["--mode", "run", "--game", "sim", "--live-mutate"], capsys)
    assert rc == 2
    assert body["error"]["code"] == "loop.live_mutate_requires_live"


def test_combat_alias_maps_to_stage_and_dev(tmp_path, monkeypatch,
                                            capsys):
    """--mode combat -> run --game live --stage combat: live gate first
    (the alias sets --game live) then dev gate."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    rc, body, _ = _run_cli(["--mode", "combat"], capsys)
    assert rc == 2
    # either gate may refuse first — both are closed-world rejections
    assert body["error"]["code"] in ("loop.live_requires_confirmation",
                                     "loop.stage_requires_dev")
