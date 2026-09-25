"""Planning-tier tests (feature 005; FR-401/402/408, SC-402).

Injected resolver/chat stubs keep everything offline and deterministic:
- extractor handles fenced and bare JSON, rejects garbage;
- valid model output -> schema-valid PlanProposal with provenance;
- malformed output -> plan.malformed, zero side effects;
- rules-only sentinel -> pack fallback_plan with degraded provenance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import planning, templates  # noqa: E402

PACK = "core-survival-v0"

_VALID_PLAN = {
    "schema_version": 0,
    "plan_id": "plan.test-1",
    "horizon_ticks": 60000,
    "actions": [{"template_id": "haul-designate",
                 "params": {"designator": "haul", "cells": [[3, 3]]}}],
    "policy_mutations": [],
    "rationale": "test plan",
}


def _resolver(endpoint="openrouter", model="nemotron", degraded=False):
    def r(role, **kw):
        return {"ok": True,
                "resolved": {"endpoint_id": endpoint, "model": model,
                             "api": "openai-compat"},
                "degraded": degraded, "reason": "primary", "tried": []}
    return r


def _rules_resolver(role, **kw):
    return {"ok": True, "resolved": {"kind": "fallback", "name": "rules-only"},
            "degraded": True, "reason": "fallback:rules-only", "tried": []}


def _chat(content, usage=None):
    def c(endpoint_id, model, messages, **kw):
        return {"ok": True, "body": {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 5, "completion_tokens": 20}}}
    return c


@pytest.fixture()
def pack():
    return templates.load_pack(PACK)


def test_extract_fenced_and_bare():
    doc = {"a": 1}
    assert planning.extract_json(
        "sure!\n```json\n" + json.dumps(doc) + "\n```") == doc
    assert planning.extract_json("text " + json.dumps(doc) + " tail") == doc
    assert planning.extract_json("no json at all") is None
    assert planning.extract_json(None) is None


def test_propose_valid(pack):
    state = {"tick": 10, "colonists": {"downed": 0}}
    r = planning.propose(state, pack, resolver=_resolver(),
                         chat=_chat(json.dumps(_VALID_PLAN)))
    assert r["ok"]
    assert r["proposal"]["plan_id"] == "plan.test-1"
    assert r["proposal"]["base_revision"] == pack["hash"]  # auto-filled
    assert r["endpoint_id"] == "openrouter"
    assert r["usage"] == {"prompt_tokens": 5, "completion_tokens": 20}


def test_propose_malformed(pack):
    r = planning.propose({}, pack, resolver=_resolver(),
                         chat=_chat("I cannot decide."))
    assert not r["ok"]
    assert r["error"]["code"] == "plan.malformed"


def test_propose_schema_violation(pack):
    bad = dict(_VALID_PLAN, policy_mutations=[
        {"op": "nuke", "target": "x", "patch": {}}])
    r = planning.propose({}, pack, resolver=_resolver(),
                         chat=_chat(json.dumps(bad)))
    assert not r["ok"]
    assert r["error"]["code"] == "plan.malformed"


def test_propose_rules_only_fallback(pack):
    r = planning.propose({}, pack, resolver=_rules_resolver,
                         chat=_chat("unreachable"))
    assert r["ok"]
    assert r["degraded"] is True
    assert r["endpoint_id"] == "rules-only"
    assert r["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
    assert r["proposal"]["plan_id"] == "plan.rules-only-fallback"
    assert r["proposal"]["base_revision"] == pack["hash"]


def test_propose_endpoint_error(pack):
    def dead(endpoint_id, model, messages, **kw):
        return {"ok": False, "error": {"code": "client.unreachable",
                                       "message": "down", "retryable": True}}
    r = planning.propose({}, pack, resolver=_resolver(), chat=dead)
    assert not r["ok"]
    assert r["error"]["code"] == "plan.endpoint_error"


def test_propose_unresolved(pack):
    def none(role, **kw):
        return {"ok": False, "error": {"code": "bindings.unresolved",
                                       "message": "no usable endpoint"}}
    r = planning.propose({}, pack, resolver=none, chat=_chat("x"))
    assert not r["ok"]
    assert r["error"]["code"] == "plan.unresolved"
