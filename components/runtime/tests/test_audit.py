"""Audit tests (feature 009; FR-804, SC-802)."""

from __future__ import annotations

import yaml

from runtime.audit import audit_code, audit_policy


def _pack(tmp_path, templates):
    p = tmp_path / "cand.yaml"
    p.write_text(yaml.safe_dump({
        "schema_version": 0, "pack_id": "pack.cand",
        "revision": "v1", "templates": templates, "jobs": [],
        "decision_map": [], "emergency": []}), encoding="utf-8")
    return p


def test_policy_audit_clean_pack(tmp_path):
    p = _pack(tmp_path, [{"id": "haul", "method": "ui.job",
                          "params_schema": {}}])
    v = audit_policy(p)
    assert v["verdict"] == "pass"
    assert v["details"]["templates_checked"] == 1


def test_policy_audit_refuses_model_executor(tmp_path):
    p = _pack(tmp_path, [{"id": "evil", "method": "ui.job",
                          "executor": "model", "params_schema": {}}])
    v = audit_policy(p)
    assert v["verdict"] == "fail"
    assert "models never execute" in v["reasons"][0]


def test_policy_audit_refuses_missing_method(tmp_path):
    p = _pack(tmp_path, [{"id": "bad", "params_schema": {}}])
    v = audit_policy(p)
    assert v["verdict"] == "fail"
    assert "lacks a method" in v["reasons"][0]


def test_policy_audit_refuses_unreadable(tmp_path):
    p = tmp_path / "cand.yaml"
    p.write_text("{{not yaml", encoding="utf-8")
    v = audit_policy(p)
    assert v["verdict"] == "fail"


def test_policy_audit_missing_file(tmp_path):
    v = audit_policy(tmp_path / "nope.yaml")
    assert v["verdict"] == "fail"


def test_code_audit_fail_closed(tmp_path):
    # runner that always fails -> verdict fail, never a silent pass
    v = audit_code(tmp_path, runner=lambda *a, **k: 1)
    assert v["verdict"] == "fail"
    assert v["reasons"]


def test_code_audit_passes_when_runners_pass(tmp_path):
    v = audit_code(tmp_path, runner=lambda *a, **k: 0)
    assert v["verdict"] == "pass"
