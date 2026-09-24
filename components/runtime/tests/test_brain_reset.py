"""Live brain-reset channel — FR-1107/1108 (feature 013).

`--live-brain` runs consume `state/brain_reset.request`: reload the pack
file (full validation), wipe planning state, re-derive goals. Without the
flag the request is refused; a broken pack stays fail-closed.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import brain, templates  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.startmode import run_start  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402
from test_startmode import StartSim  # noqa: E402


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    packs_tmp = tmp_path / "packs"
    shutil.copytree(templates.packs_dir(), packs_tmp)
    monkeypatch.setenv(templates.PACKS_ENV, str(packs_tmp))
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(state))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(state / "tasks.jsonl", sink=events.append)
    return d, game, ledger, state, events, packs_tmp


def _edit_pack(packs_tmp: Path, mutate) -> None:
    f = packs_tmp / "start-mode-v0" / "pack.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    mutate(doc)
    f.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _status(state: Path) -> dict:
    return json.loads((state / brain.STATUS).read_text(encoding="utf-8"))


def _decision_rows(state: Path) -> list[dict]:
    f = state / "decisions.jsonl"
    if not f.is_file():
        return []
    return [json.loads(l) for l in
            f.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_reset_reloads_pack_and_replans(rig):
    """SC-1107: request -> new pack hash live, status+event+matrix row."""
    d, game, ledger, state, events, packs_tmp = rig
    old_hash = d.pack["hash"]
    _edit_pack(packs_tmp,
               lambda doc: doc.__setitem__("revision", "v0-live"))
    (state / brain.REQUEST).write_text("{}\n", encoding="utf-8")
    res = run_start(d, game, ledger, d.pack["pack"],
                    iterations=3, live_brain=True)
    assert res["ok"]
    assert d.pack["hash"] != old_hash
    assert d.pack["pack"]["revision"] == "v0-live"
    status = _status(state)
    assert status["ok"] and status["pack_revision"] == d.pack["hash"]
    assert any(e["event_type"] == "brain.reset" and e["payload"]["ok"]
               for e in events)
    assert any(r["source"] == "ui:brain-reset" and r["ok"]
               for r in _decision_rows(state))


def test_reset_refused_without_live_brain(rig):
    """Scored/immutable runs never honor the channel (UR-BRN)."""
    d, game, ledger, state, events, packs_tmp = rig
    old_hash = d.pack["hash"]
    (state / brain.REQUEST).write_text("{}\n", encoding="utf-8")
    run_start(d, game, ledger, d.pack["pack"], iterations=2)
    assert d.pack["hash"] == old_hash
    status = _status(state)
    assert status["ok"] is False and "disabled" in status["error"]
    assert not (state / brain.REQUEST).exists()  # consumed, not replayed
    assert not any(e["event_type"] == "brain.reset" for e in events)


def test_reset_invalid_pack_fails_closed(rig):
    """SC-1108: broken YAML edit -> refused reset, run stays fail-closed."""
    d, game, ledger, state, events, packs_tmp = rig
    old_hash = d.pack["hash"]
    _edit_pack(packs_tmp,
               lambda doc: doc.__setitem__("templates", "not-a-list"))
    (state / brain.REQUEST).write_text("{}\n", encoding="utf-8")
    res = run_start(d, game, ledger, d.pack["pack"],
                    iterations=2, live_brain=True)
    assert res["ok"]  # reset failure must not crash the run
    assert d.pack["hash"] == old_hash
    status = _status(state)
    assert status["ok"] is False and "PackError" in status["error"]
    ev = next(e for e in events if e["event_type"] == "brain.reset")
    assert ev["payload"]["ok"] is False
    # stale hash vs edited file -> every dispatch refused as drift
    out = d.dispatch("set-anchor", {"name": "x", "cell": [5, 5]})
    assert out["ok"] is False
    assert out["error"]["code"] == "dispatch.pack_drift"
