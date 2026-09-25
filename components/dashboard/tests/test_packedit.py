"""Feature 018 T019 — guided pack editor model: outline map, doc writes,
slug enforcement, save-as-new artifact (contracts/pack-edit-save.md)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "dashboard" / "src"))

from dashboard import packedit  # noqa: E402

V0_DOC = {
    "schema_version": 0,
    "pack_id": "pack.demo", "revision": "r1", "class": "fair",
    "templates": [{"id": "t1", "method": "game.status",
                   "params_schema": {"type": "object",
                                     "properties": {}}}],
    "emergency": [{"id": "e1", "priority": 1,
                   "condition": {"combinator": "all",
                                 "predicates": []},
                   "action": {"template_id": "t1", "params": {}}}],
    "universal": {"rules": [{"id": "r1"}], "senses": {"x": 1}},
    "start": {"phases": [{"id": "site"}], "exit": {"op": "truthy"},
              "shelter": {"w": 5}},
    "govern": {"goals": [{"id": "g1"}], "stock": {}},
    "goal_options": [{"id": "o1"}],
    "jobs": ["food"], "decision_map": [],
    "mutate": {"goals_per_pass": 4},
}

V1_DOC = {
    "schema_version": 1,
    "meta": {"pack_id": "pack.v1", "revision": "r2"},
    "capabilities": {"templates": [{"id": "t1", "method": "m",
                                    "params_schema": {}}]},
    "reflexes": [{"id": "x", "when": {"op": "truthy"}}],
    "rules": [{"id": "r"}],
    "senses": {"site": {}},
    "phases": [{"id": "init", "steps": [], "complete": {}}],
    "standing_goals": [{"id": "g"}],
    "options": [{"id": "o"}],
    "decide": {"select": {}},
}


def _labels(outline):
    return {n["label"]: n for n in outline}


def test_v0_outline_map():
    labels = _labels(packedit.build_outline(V0_DOC))
    assert "Meta" in labels
    assert labels["Capabilities"]["path"] == "templates"
    assert labels["Reflexes"]["path"] == "emergency"
    assert labels["Rules"]["path"] == "universal.rules"
    assert labels["Phases (init)"]["path"] == "start.phases"
    assert labels["Standing goals"]["path"] == "govern.goals"
    assert labels["Options"]["path"] == "goal_options"
    senses = {c["label"] for c in labels["Senses"]["children"]}
    assert "universal › senses" in senses
    assert "start › shelter" in senses
    assert "govern › stock" in senses
    assert not any("rules" in s for s in senses)
    cfg = {c["label"] for c in labels["Config"]["children"]}
    assert "mutate" in cfg
    # dead v0 fields are hidden
    assert not any(n["path"] in ("jobs", "decision_map")
                   for n in packedit.build_outline(V0_DOC))


def test_v1_outline_uses_v1_paths():
    labels = _labels(packedit.build_outline(V1_DOC))
    assert labels["Capabilities"]["path"] == "capabilities.templates"
    assert labels["Reflexes"]["path"] == "reflexes"
    assert labels["Rules"]["path"] == "rules"
    assert labels["Phases"]["path"] == "phases"
    assert labels["Standing goals"]["path"] == "standing_goals"
    assert labels["Options"]["path"] == "options"
    cfg = {c["label"] for c in labels["Config"]["children"]}
    assert "decide" in cfg
    senses = {c["label"] for c in labels["Senses"]["children"]}
    assert "senses › site" in senses


def test_absent_sections_omitted():
    out = packedit.build_outline({"schema_version": 1})
    labels = _labels(out)
    assert "Phases" not in labels and "Standing goals" not in labels


def test_get_set_path():
    doc = {"a": {"b": {"c": 1}}}
    assert packedit.get_path(doc, "a.b.c") == 1
    packedit.set_path(doc, "a.b.c", 42)
    assert doc["a"]["b"]["c"] == 42
    packedit.set_path(doc, "a.x.y", "new")
    assert doc["a"]["x"]["y"] == "new"


def test_is_pred_and_is_steps():
    assert packedit.is_pred({"op": "eq", "field": "f"})
    assert packedit.is_pred({"all": []})
    assert not packedit.is_pred({"name": "x"})
    assert packedit.is_steps([{"template": "t", "params": {}}])
    assert not packedit.is_steps([{"id": "g", "effect": {}}])
    assert not packedit.is_steps([])


def test_slug_enforcement():
    assert packedit.slug_ok("my-pack-1")
    assert not packedit.slug_ok("")
    assert not packedit.slug_ok("My Pack")
    assert not packedit.slug_ok("-lead")
    assert not packedit.slug_ok("trail_underscore")
    assert not packedit.slug_ok("a/b")


def test_save_name_problem(tmp_path):
    packs = tmp_path / "packs"
    packs.mkdir()
    assert packedit.save_name_problem("new-pack", packs) is None
    assert packedit.save_name_problem("Bad Name", packs)
    assert "candidates" in packedit.save_name_problem("candidates",
                                                    packs)
    (packs / "taken").mkdir()
    (packs / "taken" / "pack.yaml").write_text("x: 1")
    assert packedit.save_name_problem("taken", packs) == "exists"


def test_save_as_new_writes_sibling(tmp_path):
    packs = tmp_path / "packs"
    src_dir = packs / "demo"
    src_dir.mkdir(parents=True)
    src = src_dir / "pack.yaml"
    src.write_text(yaml.safe_dump(V0_DOC), encoding="utf-8")
    before = src.read_bytes()

    path = packedit.save_as_new(dict(V0_DOC), "demo-custom", "demo",
                                packs)
    assert path == packs / "demo-custom" / "pack.yaml"
    out = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert out["pack_id"] == "pack.demo-custom"
    assert out["derived_from"] == "demo"
    assert out["class"] == "fair" and out["revision"] == "r1"
    assert src.read_bytes() == before  # source byte-identical (SC-005)


def test_save_as_new_refuses_bad_name(tmp_path):
    packs = tmp_path / "packs"
    packs.mkdir()
    with pytest.raises(ValueError):
        packedit.save_as_new({}, "NOPE", "demo", packs)


def test_validate_wiring_via_facade():
    """Editor pre-write gate == loader checks (validate_pack_doc)."""
    sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
    sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))
    from runtime import api  # noqa: E402
    ok = api.validate_pack_doc({"schema_version": 1,
                                "meta": {"pack_id": "pack.x"},
                                "capabilities": {"templates": [{
                                    "id": "t", "method": "game.status",
                                    "params_schema": {}}]}})
    assert ok["ok"] or ok["issues"]  # envelope shape either way
    bad = api.validate_pack_doc({"schema_version": 1, "meta": {},
                                 "capabilities": {"templates": [
                                     {"id": "t",
                                      "method": "bogus.method",
                                      "params_schema": {}}]}})
    assert bad["ok"] is False
    assert any("inventory" in i or "bogus" in i
               for i in bad["issues"])


def test_scan_skips_candidates(tmp_path):
    """packs/candidates is pipeline-owned — never a selectable pack."""
    from dashboard import overlay
    packs = tmp_path / "packs"
    (packs / "demo").mkdir(parents=True)
    (packs / "demo" / "pack.yaml").write_text("pack_id: pack.demo")
    (packs / "candidates").mkdir()
    (packs / "candidates" / "cand-mut-x.yaml").write_text(
        "pack_id: pack.cand")
    ids = [d["id"] for d in overlay.scan_pack_descriptors(packs)]
    assert ids == ["demo"]
