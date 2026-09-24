"""Pack schema v0->v1 migration tests (feature 017; FR-1404).

Covers: v0 packs load normalized to v1 surfaces; native v1 loads
unchanged; cfg aliases keep `@cfg:start.*`/`@cfg:govern.*` resolvers
working; emergency -> reflexes dialect adaptation; normalized hash
stable across a v0 file and an equivalent v1 candidate; schema_version
> 1 rejected.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import policy, templates  # noqa: E402
from runtime.dispatch import _reflex_pred  # noqa: E402


V0_DOC = {
    "schema_version": 0,
    "pack_id": "pack.mig-test", "revision": "r0",
    "templates": [{"id": "noop", "method": "game.status",
                   "params_schema": {"type": "object"}}],
    "jobs": [], "decision_map": [],
    "emergency": [{"id": "fire", "priority": 1,
                   "condition": {"combinator": "all", "predicates": [
                       {"field": "map.fires", "op": "gt", "value": 0}]},
                   "action": {"template_id": "noop", "params": {}}}],
    "universal": {"idle_patterns": ["idle"],
                  "rules": [{"id": "r1", "when": {"op": "truthy",
                                                "field": "@obs:tick"},
                             "try": []}]},
    "start": {"site": {"zone_w": 9},
              "phases": [{"id": "site", "effect": {"op": "truthy",
                                                   "field": "@obs:tick"},
                          "steps": []}],
              "exit": {"conditions": {"done": {"op": "truthy",
                                              "field": "@obs:tick"}},
                       "fix": {}}},
    "govern": {"research": {"queue": ["Battery"]},
               "goals": [{"id": "g1", "effect": {"op": "truthy",
                                                "field": "@obs:tick"},
                          "steps": []}]},
    "goal_options": [{"id": "opt1"}],
    "mutate": {"goals_per_pass": 2},
}


def test_v0_doc_migrates_to_v1_surfaces():
    m = templates.migrate_v0(copy.deepcopy(V0_DOC))
    assert m["schema_version"] == 1
    assert m["capabilities"]["templates"] == V0_DOC["templates"]
    assert m["phases"][0]["id"] == "init"
    assert m["phases"][0]["prescriptive"] is True
    assert m["phases"][0]["steps"] == V0_DOC["start"]["phases"]
    assert m["phases"][0]["complete"] == V0_DOC["start"]["exit"]
    assert m["standing_goals"] == V0_DOC["govern"]["goals"]
    assert m["options"] == V0_DOC["goal_options"]
    assert m["rules"] == V0_DOC["universal"]["rules"]
    # cfg alias blocks retained so @cfg:start.* / @cfg:govern.* resolve
    assert m["start"]["site"]["zone_w"] == 9
    assert m["govern"]["research"]["queue"] == ["Battery"]


def test_reflex_condition_adapts_to_policy_dialect():
    m = templates.migrate_v0(copy.deepcopy(V0_DOC))
    rule = templates.reflexes_of(m)[0]
    pred = _reflex_pred(rule)
    ctx = policy.Ctx(cfg=m, obs={"map": {"fires": 3}}, game=None)
    assert policy.check(pred, ctx)
    ctx.obs = {"map": {"fires": 0}}
    assert not policy.check(pred, ctx)
    # a native v1 `when` predicate passes through untouched
    rule2 = {"when": {"field": "@obs:map.fires", "op": "gt", "value": 0}}
    assert _reflex_pred(rule2) == rule2["when"]


def test_v0_to_v1_path_rewrite():
    f = templates.v0_to_v1_path
    assert f("govern.goals.3.steps") == "standing_goals.3.steps"
    assert f("start.phases") == "phases.0.steps"
    assert f("goal_options.2") == "options.2"
    assert f("universal.rules.0") == "rules.0"
    assert f("mutate.cooldown_polls") == "mutate.cooldown_polls"


def test_native_v1_and_migrated_v0_accessors_agree():
    v1 = dict(templates.migrate_v0(copy.deepcopy(V0_DOC)))
    for acc in (templates.templates_of, templates.phases_of,
                templates.standing_goals_of, templates.options_of,
                templates.rules_of, templates.reflexes_of):
        assert acc(v1) == acc(templates.migrate_v0(
            copy.deepcopy(V0_DOC)))


def test_normalized_hash_stable_across_v0_and_v1():
    """Pack hash is computed on the normalized doc — a v0 file and its
    v1 candidate differ on disk but hash the same when semantically
    equal (contract pack-schema-v1)."""
    h_v0 = templates._hash_of(copy.deepcopy(V0_DOC))
    v1 = templates.migrate_v0(copy.deepcopy(V0_DOC))
    assert templates._hash_of(v1) == h_v0


def test_schema_version_gt_1_rejected(tmp_path, monkeypatch):
    d = tmp_path / "packs"
    d.mkdir()
    doc = dict(V0_DOC, schema_version=2)
    (d / "future-pack").mkdir()
    (d / "future-pack" / "pack.yaml").write_text(
        yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv(templates.PACKS_ENV, str(d))
    with pytest.raises(templates.PackError) as exc:
        templates.load_pack("future-pack")
    assert exc.value.envelope["error"]["code"] == "pack.schema_version"
