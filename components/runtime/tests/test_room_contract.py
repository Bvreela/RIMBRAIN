"""Feature 020 room contract tests (SC-2004/SC-2005, room-archetypes/v0).

Load-time lint: room goals must verify on observed role/stat predicates;
a synthetic archetype absent from shipped packs loads and compiles with
data-only edits (no runtime change).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

import yaml  # noqa: E402

from runtime import policy  # noqa: E402
from runtime import templates  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402


def _goal(effect, steps=None):
    return {"id": "room-goal", "steps": steps or [
        {"template": "build-layout",
         "params": {"ops": "@fn:plan_room(@var:site.rect, bedroom)"}}],
        "effect": effect}


def test_enclosed_at_only_room_goal_rejected():
    """SC-2004: a room goal whose effect predicates on enclosed_at alone
    is a load-time violation."""
    bad = _goal({"field": "@fn:enclosed_at(@var:site.rect, 9)",
                 "op": "gte", "value": 1})
    doc = {"standing_goals": [bad]}
    problems = templates._room_goal_problems(doc)
    assert any("enclosed_at alone" in p for p in problems)


def test_role_stat_effect_accepted():
    good = _goal({"all": [
        {"field": "@fn:room_role_at(@var:site.min)", "op": "eq",
         "value": "Bedroom"},
        {"field": "@fn:room_stat(@var:site.min, impressiveness)",
         "op": "gte", "value": 40}]})
    assert templates._room_goal_problems(
        {"standing_goals": [good]}) == []


def test_non_room_enclosed_at_goals_unaffected():
    """Legacy enclosure goals (no plan_room / rooms.* markers) are not
    room goals — the lint leaves them alone."""
    legacy = {"id": "legacy", "steps": [
        {"template": "build-one", "params": {"def": "Wall"}}],
        "effect": {"field": "@fn:enclosed_at(@var:site.rect, 9)",
                   "op": "gte", "value": 1}}
    assert templates._room_goal_problems({"standing_goals": [legacy]}) == []


def test_room_archetype_field_validation():
    """Schema: bad archetype rule field / missing size is a load error."""
    base = {"schema_version": 1,
            "meta": {"pack_id": "pack.x", "revision": "r"},
            "revision": "r", "pack_id": "pack.x",
            "capabilities": {"templates": [
                {"id": "t", "method": "ui.build",
                 "params_schema": {}}]}}
    schema_ok = dict(base)
    schema_ok["rooms"] = {"tier_table": "auto", "archetypes": {
        "bedroom": {"size": {"w": 4, "h": 6},
                    "furniture": [{"def": "Bed", "count": 1,
                                   "anchor": "wall"},
                                  {"def": "Dresser", "linked_to": "Bed",
                                   "adjacent_to": "Bed", "separate": True,
                                   "optional": False, "links": 2,
                                   "at": "each_bench"}]}}}
    assert templates.validate_pack(schema_ok) == []
    # anchor outside the enum -> rejected by the jsonschema layer
    bad_anchor = dict(base)
    bad_anchor["rooms"] = {"archetypes": {"x": {
        "size": {"w": 4, "h": 6},
        "furniture": [{"def": "Bed", "anchor": "roof"}]}}}
    assert templates.validate_pack(bad_anchor) != []


def test_synthetic_archetype_data_only():
    """SC-2005: an archetype not present in shipped packs loads and
    compiles with data edits only."""
    g = SimGame()
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {
        "workroom": {"size": {"w": 5, "h": 5}, "wall": "Wall",
                     "door": "Door", "floor": "Carpet",
                     "furniture": [{"def": "Bed", "count": 1,
                                    "anchor": "wall"}]}}}}
    ctx = policy.Ctx(cfg=cfg, obs={}, game=g)
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], workroom)", ctx)
    assert out is not None
    assert any(o["def"] == "Bed" for o in out["ops"])


def test_shipped_pack_rooms_cfg_validates():
    """start-mode-v0 ships rooms:/mods: and passes the full load path."""
    res = templates.load_pack("start-mode-v0")
    rooms = res["pack"].get("rooms") or {}
    assert "bedroom" in rooms.get("archetypes", {})
    mods = res["pack"].get("mods") or {}
    rrr = mods.get("realistic_rooms_rewritten") or {}
    assert rrr.get("package_id") == "Lucifer.RealisticRooms"
    assert len(rrr.get("settings") or {}) >= 6
    # the shipped bedroom archetype compiles in sim
    g = SimGame()
    ctx = policy.Ctx(cfg=res["pack"], obs={}, game=g)
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)", ctx)
    assert out is not None


def test_pack_yaml_parses():
    p = (REPO_ROOT / "components" / "rimbrain" / "packs"
         / "start-mode-v0" / "pack.yaml")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(doc.get("rooms"), dict)
    assert isinstance(doc.get("mods"), dict)
