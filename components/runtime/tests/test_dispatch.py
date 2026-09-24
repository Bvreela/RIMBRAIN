"""Dispatcher + templates tests (feature 004; FR-301..305, SC-301/302/304).

Offline: SimGame as the bridge target. Fail-closed matrix: unknown action,
invalid params, unmapped decision, pack drift — every refusal must cause zero
bridge calls (SC-302). Evidence: event stream == write stream (SC-301).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import templates  # noqa: E402
from runtime.dispatch import Dispatcher, substitute_params  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402


class _RecordingBridge:
    """SimGame wrapper that counts every rpc call (write-stream audit)."""

    def __init__(self, game: SimGame):
        self._game = game
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        return self._game.rpc(method, params)

    def status(self) -> dict:
        return self.rpc("game.status", {})


@pytest.fixture()
def dispatcher(tmp_path, monkeypatch):
    """Dispatcher wired to a recording SimGame + event sink; real repo pack."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    records: list[dict] = []
    d = Dispatcher(_RecordingBridge(SimGame()), sink=records.append)
    d.load_pack("core-survival-v0")
    d._records = records  # type: ignore[attr-defined]
    return d


# ---------------------------------------------------------------- templates --

def test_pack_loads_and_hash_stable(dispatcher):
    assert dispatcher.pack["pack"]["pack_id"] == "pack.core-survival-v0"
    again = templates.load_pack("core-survival-v0")
    assert again["hash"] == dispatcher.pack["hash"]


def test_pack_rejects_unknown_method(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(tmp_path))
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump({
        "schema_version": 0, "pack_id": "pack.bad", "revision": "v0",
        "templates": [{"id": "t", "method": "no.such.method",
                       "params_schema": {"type": "object"}}],
        "jobs": [], "decision_map": [], "emergency": []}), encoding="utf-8")
    with pytest.raises(templates.PackError) as e:
        templates.load_pack("bad")
    assert e.value.envelope["error"]["code"] == "pack.inventory_mismatch"


def _mkpack(dir_path: Path, name: str = "pack.yaml") -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / name
    p.write_text(yaml.safe_dump({
        "schema_version": 0, "pack_id": "pack.t", "revision": "v0",
        "templates": [{"id": "t", "method": "game.status",
                       "params_schema": {"type": "object"}}],
        "jobs": [], "decision_map": [], "emergency": []}),
        encoding="utf-8")
    return p


def test_folder_pack_loads(tmp_path, monkeypatch):
    """packs/<id>/pack.yaml is the canonical pack form."""
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(tmp_path))
    _mkpack(tmp_path / "my-pack")
    loaded = templates.load_pack("my-pack")
    assert loaded["pack"]["pack_id"] == "pack.t"
    assert loaded["path"].endswith("pack.yaml")


def test_flat_pack_fallback(tmp_path, monkeypatch):
    """Flat <id>.yaml still loads (candidates/ materializes flat)."""
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(tmp_path))
    _mkpack(tmp_path, "flat.yaml")
    assert templates.load_pack("flat")["pack"]["pack_id"] == "pack.t"


def test_list_packs_discovers_both_forms(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(tmp_path))
    _mkpack(tmp_path / "a")                       # folder pack "a"
    _mkpack(tmp_path / "grp" / "b")               # nested folder "grp/b"
    _mkpack(tmp_path, "flat.yaml")                # flat pack "flat"
    _mkpack(tmp_path / "a", "notes-as-yaml.yaml")  # aux inside folder pack
    assert templates.list_packs() == ["a", "flat", "grp/b"]


def test_pack_id_traversal_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(tmp_path))
    for bad in ("../x", "a/../../x", str(tmp_path / "abs.yaml"), ""):
        with pytest.raises(templates.PackError) as e:
            templates.load_pack(bad)
        assert e.value.envelope["error"]["code"] == "pack.invalid_id"


def test_pack_drift_refuses(dispatcher, tmp_path):
    """Mid-run pack edit -> dispatch.pack_drift, zero writes (SC-304)."""
    pack_path = templates.pack_path("core-survival-v0")
    original = pack_path.read_text(encoding="utf-8")
    try:
        # duplicate key: last wins in YAML -> different canonical doc -> drift
        pack_path.write_text(original + "\nrevision: v0-drift\n",
                             encoding="utf-8")
        res = dispatcher.dispatch("rescue", {"pawn": "Gomez", "job": "Rescue",
                                             "target": "c2"})
        assert not res["ok"]
        assert res["error"]["code"] == "dispatch.pack_drift"
        assert dispatcher.bridge.calls == []  # zero writes
    finally:
        pack_path.write_text(original, encoding="utf-8")


# ---------------------------------------------------------------- dispatch --

def test_dispatch_ok_and_evidence(dispatcher):
    res = dispatcher.dispatch("rescue", {"pawn": "Gomez", "job": "Rescue",
                                         "target": "c2"})
    assert res["ok"]
    assert dispatcher.bridge.calls == [("ui.job", {"pawn": "Gomez",
                                                   "job": "Rescue",
                                                   "target": "c2"})]
    types = [e["event_type"] for e in dispatcher._records]
    assert types == ["action.issued", "action.completed"]
    payload = dispatcher._records[0]["payload"]
    assert payload["pack_revision"] == dispatcher.pack["hash"]
    assert payload["template_id"] == "rescue"
    assert payload["params"] == {"pawn": "Gomez", "job": "Rescue",
                                 "target": "c2"}


def test_unknown_action_refused(dispatcher):
    res = dispatcher.dispatch("nuke", {})
    assert not res["ok"]
    assert res["error"]["code"] == "dispatch.unknown_action"
    assert dispatcher.bridge.calls == []
    assert dispatcher._records[-1]["event_type"] == "action.refused"


def test_params_invalid_refused(dispatcher):
    res = dispatcher.dispatch("rescue", {"pawn": "Gomez"})  # missing job/target
    assert not res["ok"]
    assert res["error"]["code"] == "dispatch.params_invalid"
    assert dispatcher.bridge.calls == []


def test_unmapped_decision_refused(dispatcher):
    res = dispatcher.dispatch_from_decision({"choice": "dance"},
                                            SimGame().current)
    assert not res["ok"]
    assert res["error"]["code"] == "dispatch.decision_unmapped"
    assert dispatcher.bridge.calls == []


def test_decision_maps_and_substitutes(dispatcher):
    state = SimGame().current
    state["first_colonist"] = "Gomez"
    state["colonists"]["downed_id"] = "c2"
    res = dispatcher.dispatch_from_decision(
        {"choice": "rescue", "score": 0.9, "noul": 0.1}, state)
    assert res["ok"]
    method, params = dispatcher.bridge.calls[0]
    assert method == "ui.job"
    assert params == {"pawn": "Gomez", "job": "Rescue", "target": "c2"}


def test_substitute_params_dotted():
    state = {"a": {"b": [1, 2]}}
    assert substitute_params({"x": "{state.a.b.1}", "y": "literal"},
                             state, {}) == {"x": 2, "y": "literal"}
    assert substitute_params({"x": "{state.missing}"}, state, {}) == \
        {"x": "{state.missing}"}


def test_reflex_fires_without_model(dispatcher):
    state = SimGame().current
    state["colonists"]["downed"] = 1
    state["colonists"]["downed_id"] = "c2"
    fired = dispatcher.reflex(state)
    assert fired and fired[0]["ok"]
    assert dispatcher.bridge.calls[0][0] == "ui.job"
    assert any(e["event_type"] == "action.emergency"
               for e in dispatcher._records)
