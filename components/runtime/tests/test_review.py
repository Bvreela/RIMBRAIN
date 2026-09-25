"""Review-gate tests (feature 005; FR-403, SC-401).

The deterministic gate is decisive: a violating proposal is rejected even
when the review model approves — and the model is never consulted on a
violating plan (SC-401). Clean plans get advisory feedback; a dead review
endpoint degrades to model_unavailable with the gate verdict standing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import review, templates  # noqa: E402

PACK = "core-survival-v0"


@pytest.fixture()
def pack():
    return templates.load_pack(PACK)


def _proposal(pack, actions=None, mutations=None):
    return {"schema_version": 0, "plan_id": "plan.review-test",
            "base_revision": pack["hash"], "horizon_ticks": 1000,
            "actions": actions or [],
            "policy_mutations": mutations or [], "rationale": "t"}


def _approve_chat(calls):
    def c(endpoint_id, model, messages, **kw):
        calls.append(endpoint_id)
        return {"ok": True, "body": {
            "choices": [{"message": {"content": "looks great, ship it"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 7}}}
    return c


def _resolver(role, **kw):
    return {"ok": True,
            "resolved": {"endpoint_id": "openrouter",
                         "model": "nemotron", "api": "openai-compat"},
            "degraded": False, "reason": "primary", "tried": []}


def test_gate_rejects_unknown_template_despite_model_approval(pack):
    """SC-401: approving model cannot rescue a violating plan."""
    calls: list = []
    bad = _proposal(pack, actions=[{"template_id": "does-not-exist",
                                  "params": {}}])
    v = review.review(bad, pack, resolver=_resolver,
                      chat=_approve_chat(calls))
    assert v["verdict"] == "rejected"
    assert any("unknown template" in s for s in v["violations"])
    assert calls == []  # model never consulted on a violating plan


def test_gate_rejects_bad_params_and_stale_base(pack):
    bad = _proposal(pack, actions=[{"template_id": "rescue",
                                  "params": {"pawn": "c1"}}])
    bad["base_revision"] = "deadbeef"
    v = review.review(bad, pack, resolver=_resolver, chat=lambda *a, **k: {})
    assert v["verdict"] == "rejected"
    assert any("stale base_revision" in s for s in v["violations"])
    assert any("required param" in s or "required" in s
               for s in v["violations"])


def test_gate_rejects_illegal_mutation(pack):
    bad = _proposal(pack, mutations=[
        {"op": "add_template", "target": "new-act",
         "patch": {"id": "new-act", "method": "ui.not_a_method",
                   "params_schema": {"type": "object"}}}])
    v = review.review(bad, pack, resolver=_resolver, chat=lambda *a, **k: {})
    assert v["verdict"] == "rejected"
    assert any("not in bridge inventory" in s for s in v["violations"])


def test_clean_plan_approved_with_feedback(pack):
    calls: list = []
    good = _proposal(pack, actions=[
        {"template_id": "haul-designate",
         "params": {"designator": "haul", "cells": [[3, 3]]}}])
    v = review.review(good, pack, resolver=_resolver,
                      chat=_approve_chat(calls))
    assert v["verdict"] == "approved"
    assert v["feedback"] == "looks great, ship it"
    assert calls == ["openrouter"]


def test_review_model_unavailable_still_approves_clean(pack):
    def dead_resolver(role, **kw):
        return {"ok": False, "error": {"code": "bindings.unresolved",
                                       "message": "none"}}
    good = _proposal(pack)
    v = review.review(good, pack, resolver=dead_resolver,
                      chat=lambda *a, **k: {})
    assert v["verdict"] == "approved"
    assert v["model_unavailable"] is True


_STATE = {
    "colonists": {"downed": 0, "downed_id": None,
                  "members": [{"id": "c1", "name": "Gomez", "downed": False},
                              {"id": "c2", "name": "Hicklin",
                               "downed": False}]},
}


def test_gate_rejects_invented_pawn(pack):
    """Project rule: plans act on observed colony state only (live-smoke
    finding — the planner invented 'Pawn1' against the real colony)."""
    bad = _proposal(pack, actions=[{
        "template_id": "prioritize-work",
        "params": {"pawn": "Pawn1", "priorities": {"Growing": 1}}}])
    v = review.review(bad, pack, state=_STATE,
                      resolver=_resolver, chat=lambda *a, **k: {})
    assert v["verdict"] == "rejected"
    assert any("not an observed colony entity" in s
               for s in v["violations"])


def test_gate_accepts_observed_entities(pack):
    good = _proposal(pack, actions=[{
        "template_id": "rescue",
        "params": {"pawn": "Gomez", "job": "Rescue", "target": "c2"}}])
    v = review.review(good, pack, state=_STATE,
                      resolver=_resolver, chat=lambda *a, **k: {})
    assert v["verdict"] == "approved"


def test_gate_entity_check_skipped_without_roster(pack):
    """No roster in state => cannot verify => schema-valid plan passes."""
    plan = _proposal(pack, actions=[{
        "template_id": "prioritize-work",
        "params": {"pawn": "anyone", "priorities": {"Growing": 1}}}])
    v = review.review(plan, pack, state={"tick": 5},
                      resolver=_resolver, chat=lambda *a, **k: {})
    assert v["verdict"] == "approved"


def test_rules_only_reviewer_counts_unavailable(pack):
    def sentinel(role, **kw):
        return {"ok": True,
                "resolved": {"kind": "fallback", "name": "rules-only"},
                "degraded": True, "reason": "fallback", "tried": []}
    v = review.review(_proposal(pack), pack, resolver=sentinel,
                      chat=lambda *a, **k: {})
    assert v["verdict"] == "approved"
    assert v["model_unavailable"] is True
