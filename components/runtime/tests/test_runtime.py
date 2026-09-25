"""Feature 002 runtime tests — all offline (stub HTTP servers)."""

from __future__ import annotations

import json

import pytest

from conftest import StubHandler, write_bindings, write_endpoints

from runtime import bindings as rb
from runtime import client as rc
from runtime import discover as rd
from runtime import probe as rp
from runtime import provenance as rp2
from runtime import registry as rr
from runtime.secrets import SecretError, resolve_api_key

EP_OA = {"id": "stub-oa", "api": "openai-compat", "base_url": None,
         "api_key_ref": None, "models": ["m1"], "capabilities": ["chat", "tool_calls"]}
EP_SO = {"id": "stub-so", "api": "systemone", "base_url": None,
         "decide_path": "/v1/systemone", "api_key_ref": None,
         "models": ["laya"], "capabilities": ["typed_decisions"]}


# ---------------------------------------------------------------- registry --

def test_load_missing_files_is_empty(profiles):
    assert rr.load_endpoints() == {"endpoints": []}
    assert rr.load_bindings() == {"bindings": {}, "degraded_paths": {}}


def test_registry_round_trip(profiles):
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x")])
    write_bindings(profiles, {"r1": {"endpoint": "stub-oa", "model": "m1"}})
    doc = rr.load_endpoints()
    assert doc["endpoints"][0]["id"] == "stub-oa"
    assert rr.load_bindings()["bindings"]["r1"]["endpoint"] == "stub-oa"


def test_add_update_delete_endpoint(profiles):
    write_endpoints(profiles, [])
    assert rr.add_endpoint(dict(EP_OA, base_url="http://x"))["ok"]
    assert not rr.add_endpoint(dict(EP_OA, base_url="http://x"))["ok"]  # dup
    assert rr.update_endpoint("stub-oa", {"label": "new"})["ok"]
    assert rr.get_endpoint("stub-oa")["label"] == "new"
    assert rr.delete_endpoint("stub-oa")["ok"]  # unbound -> deletes


def test_delete_bound_endpoint_refused(profiles):
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x")])
    write_bindings(profiles, {"r1": {"endpoint": "stub-oa", "model": "m1"}})
    res = rr.delete_endpoint("stub-oa")
    assert not res["ok"] and res["error"]["code"] == "registry.endpoint.bound"


def test_bindings_unknown_endpoint_fails_closed(profiles):
    write_endpoints(profiles, [])
    write_bindings(profiles, {"r1": {"endpoint": "ghost", "model": "m1"}})
    with pytest.raises(rr.RegistryError) as e:
        rr.load_bindings()
    assert e.value.envelope["error"]["code"] == "registry.endpoint.missing"


def test_invalid_doc_rejected(profiles):
    (profiles / "endpoints.yaml").write_text("endpoints: [{id: 'BAD ID!'}]")
    with pytest.raises(rr.RegistryError) as e:
        rr.load_endpoints()
    assert e.value.envelope["error"]["code"] == "registry.validation.failed"


# ----------------------------------------------------------------- secrets --

def test_env_ref_resolves(profiles, monkeypatch):
    monkeypatch.setenv("TEST_KEY_002", "sekrit")
    assert resolve_api_key("env:TEST_KEY_002") == "sekrit"


def test_unresolved_ref_errors(profiles, monkeypatch):
    monkeypatch.delenv("NOPE_002", raising=False)
    with pytest.raises(SecretError) as e:
        resolve_api_key("env:NOPE_002")
    assert e.value.envelope["error"]["code"] == "secrets.ref.unresolved"


def test_config_local_lookup(profiles, tmp_path, monkeypatch):
    cfg = tmp_path / "config.local.yaml"
    cfg.write_text("llm:\n  api_key: cfgsekrit\n")
    monkeypatch.setattr("runtime.secrets.CONFIG_LOCAL", cfg)
    assert resolve_api_key("config:api_key") == "cfgsekrit"


# -------------------------------------------------------------------- probe --

def test_probe_openai_compat(profiles, stub_server):
    StubHandler.RESPONSES["/v1/models"] = (200, {"data": [{"id": "m1"}, {"id": "m2"}]})
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    res = rp.probe_endpoint("stub-oa")
    assert res["ok"] and res["models"] == ["m1", "m2"]
    assert res["declared_missing"] == ["m1"] is False or True  # m1 advertised
    assert res["declared_missing"] == []


def test_probe_dead_endpoint_transient(profiles):
    write_endpoints(profiles, [dict(EP_OA, base_url="http://127.0.0.1:1/v1")])
    res = rp.probe_endpoint("stub-oa")
    assert not res["ok"] and res["error"]["retryable"]
    assert res["error"]["code"] == "probe.unreachable"


def test_probe_503_is_transient(profiles, stub_server):
    StubHandler.RESPONSES["/v1/models"] = (503, {})
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    res = rp.probe_endpoint("stub-oa")
    assert not res["ok"] and res["error"]["retryable"]


def test_probe_declared_model_missing(profiles, stub_server):
    StubHandler.RESPONSES["/v1/models"] = (200, {"data": [{"id": "other"}]})
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    res = rp.probe_endpoint("stub-oa")
    assert res["ok"] and res["declared_missing"] == ["m1"]


# ------------------------------------------------------------------ resolve --

def _setup(profiles):
    write_endpoints(profiles, [
        dict(EP_OA, base_url="http://x"),
        dict(EP_SO, base_url="http://y"),
    ])


def test_resolve_primary(profiles):
    _setup(profiles)
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa", "model": "m1"}})
    res = rb.resolve_role("rimbrain.plan")
    assert res["ok"] and not res["degraded"]
    assert res["resolved"]["endpoint_id"] == "stub-oa"


def test_capability_gate_select(profiles):
    _setup(profiles)
    # select requires typed_decisions|tool_calls; stub-oa has tool_calls -> ok
    write_bindings(profiles,
                   {"rimbrain.select": {"endpoint": "stub-oa", "model": "m1"}})
    assert rb.resolve_role("rimbrain.select")["ok"]


def test_capability_gate_embed_rejects(profiles):
    _setup(profiles)
    write_bindings(profiles,
                   {"rimbrain.embed": {"endpoint": "stub-oa", "model": "m1"},
                    "x": {"endpoint": "stub-oa", "model": "m1"}},
                   degraded={"rimbrain.embed": ["lexical-bm25"]})
    res = rb.resolve_role("rimbrain.embed")
    # embed requires embeddings; stub-oa lacks it -> falls to sentinel
    assert res["ok"] and res["resolved"]["kind"] == "fallback"
    assert res["resolved"]["name"] == "lexical-bm25" and res["degraded"]


def test_degraded_path_order(profiles):
    _setup(profiles)
    write_bindings(
        profiles,
        {"rimbrain.select": {"endpoint": "ghost-removed", "model": "m1"},
         "keep": {"endpoint": "stub-oa", "model": "m1"}},
        degraded={"rimbrain.select": ["stub-so:laya", "rules"]})
    # ghost endpoint makes load_bindings fail closed -> registry error
    res = rb.resolve_role("rimbrain.select")
    assert not res["ok"]
    write_bindings(
        profiles,
        {"rimbrain.select": {"endpoint": "stub-oa", "model": "nope"},
         "keep": {"endpoint": "stub-oa", "model": "m1"}},
        degraded={"rimbrain.select": ["stub-so:laya", "rules"]})
    res = rb.resolve_role("rimbrain.select")
    assert res["ok"] and res["resolved"]["endpoint_id"] == "stub-so"
    assert res["degraded"]


def test_unresolved_when_no_binding(profiles):
    _setup(profiles)
    write_bindings(profiles, {})
    res = rb.resolve_role("rimbrain.plan")
    assert not res["ok"] and res["error"]["code"] == "bindings.unresolved"


# ------------------------------------------------------------------- client --

def test_chat_strict_strips_extensions(profiles, stub_server):
    StubHandler.RESPONSES["/v1/chat/completions"] = (200, {"choices": []})
    write_endpoints(profiles, [
        dict(EP_OA, base_url=stub_server + "/v1", strict=True)])
    r = rc.openai_compat_chat(
        "stub-oa", "m1", [{"role": "user", "content": "hi"}],
        extra_body={"chat_template_kwargs": {"enable_thinking": False},
                    "reasoning": {"enabled": True}})
    assert r["ok"]
    sent = json.loads(StubHandler.RECEIVED[-1][3])
    assert "chat_template_kwargs" not in sent and "reasoning" not in sent


def test_chat_nonstrict_passes_extensions(profiles, stub_server):
    StubHandler.RESPONSES["/v1/chat/completions"] = (200, {"choices": []})
    write_endpoints(profiles, [
        dict(EP_OA, base_url=stub_server + "/v1", strict=False)])
    r = rc.openai_compat_chat(
        "stub-oa", "m1", [{"role": "user", "content": "hi"}],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    assert r["ok"]
    sent = json.loads(StubHandler.RECEIVED[-1][3])
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}


def test_systemone_decide_uses_decide_path(profiles, stub_server):
    StubHandler.RESPONSES["/v1/systemone"] = (
        200, {"answers": {"q": {"choice": "act", "confidence": 0.9}}})
    write_endpoints(profiles, [dict(EP_SO, base_url=stub_server)])
    r = rc.systemone_decide("stub-so", "state", {"q": {"type": "choice"}})
    assert r["ok"] and r["body"]["answers"]["q"]["choice"] == "act"


# --------------------------------------------------------------- provenance --

def test_manifest_deterministic_and_secret_free(profiles):
    _setup(profiles)
    write_bindings(
        profiles,
        {"rimbrain.plan": {"endpoint": "stub-oa", "model": "m1"},
         "rimbrain.select": {"endpoint": "stub-so", "model": "laya"}},
        degraded={"rimbrain.select": ["rules"]})
    m1 = rp2.episode_manifest("ep.000001")
    m2 = rp2.episode_manifest("ep.000001")
    assert m1 == m2
    assert json.dumps(m1).count("stub-oa") == 1
    assert "api_key" not in json.dumps(m1)
    assert m1["roles"]["rimbrain.plan"]["endpoint_id"] == "stub-oa"
    m3 = rp2.episode_manifest("ep.000001")
    write_bindings(
        profiles,
        {"rimbrain.plan": {"endpoint": "stub-so", "model": "laya"},
         "rimbrain.select": {"endpoint": "stub-so", "model": "laya"}},
        degraded={"rimbrain.select": ["rules"]})
    m4 = rp2.episode_manifest("ep.000001")
    assert m3 != m4  # different bindings -> distinguishable manifests


# ------------------------------------------------------------------ discover --

def test_discover_finds_stub(profiles, stub_server, monkeypatch):
    StubHandler.RESPONSES["/v1/models"] = (200, {"data": [{"id": "found"}]})
    port = int(stub_server.rsplit(":", 1)[1])
    monkeypatch.setattr(rd, "_PORTS",
                        [(port, "openai-compat", "Stub", "http://127.0.0.1:{p}/v1", None)])
    found = rd.scan_local()
    assert len(found) == 1 and found[0]["models"] == ["found"]


def test_discover_tolerates_absent(profiles, monkeypatch):
    monkeypatch.setattr(rd, "_PORTS",
                        [(1, "openai-compat", "X", "http://127.0.0.1:{p}/v1", None)])
    assert rd.scan_local() == []


# ------------------------------------------- facade + convergence (T070-T073) --

def test_set_binding_capability_gate(profiles):
    write_endpoints(profiles, [dict(EP_SO, base_url="http://x")])
    # stub-so declares typed_decisions only; rimbrain.plan requires chat|tool_calls
    res = rr.set_binding("rimbrain.plan", "stub-so", "laya")
    assert not res["ok"]
    assert res["error"]["code"] == "registry.binding.capability"
    # capable role binds fine; unlisted role is ungated
    assert rr.set_binding("rimbrain.select", "stub-so", "laya")["ok"]
    assert rr.set_binding("custom.role", "stub-so", "laya")["ok"]


def test_api_duplicates_flagged(profiles):
    from runtime import api
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x"),
                             dict(EP_OA, id="oa2", base_url="http://x"),
                             dict(EP_SO, base_url="http://y")])
    doc = api.list_endpoints()
    assert doc["duplicates"] == ["http://x"]
    res = api.add_endpoint(dict(EP_OA, id="oa3", base_url="http://x"))
    assert res["ok"] and "duplicate base_url" in res["warning"]


def test_probe_cache_serves_last_known(profiles, stub_server):
    from runtime import api
    api.probe_cache().clear()
    StubHandler.RESPONSES["/v1/models"] = (200, {"data": [{"id": "m1"}]})
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    fresh = api.probe("stub-oa")
    assert fresh["ok"] and "cached" not in fresh and fresh["probed_utc"]
    calls = len(StubHandler.RECEIVED)
    cached = api.probe("stub-oa", fresh=False)
    assert cached["cached"] and len(StubHandler.RECEIVED) == calls
    assert api.probe_cached("stub-oa")["models"] == ["m1"]
    missing = api.probe_cached("ghost")
    assert not missing["ok"] and missing["error"]["code"] == "probe.no_cache"


def test_bind_role_facade(profiles):
    from runtime import api
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x")])
    write_bindings(profiles, {})
    res = api.bind_role("rimbrain.plan", "stub-oa", "m1")
    assert res["ok"] and res["result"]["role"] == "rimbrain.plan"
    bad = api.bind_role("rimbrain.select", "stub-oa", "m1")
    assert bad["ok"]  # stub-oa HAS tool_calls -> select requirement satisfied


# ------------------------------------------- convergence 2 (T074-T076) --------

def test_set_binding_rejects_unknown_model(profiles):
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x")])
    res = rr.set_binding("rimbrain.plan", "stub-oa", "ghost-model")
    assert not res["ok"] and res["error"]["code"] == "registry.binding.model"
    assert res["error"]["details"]["models"] == ["m1"]
    assert rr.set_binding("rimbrain.plan", "stub-oa", "m1")["ok"]


def test_pin_bindings_freezes_resolution(profiles):
    from runtime import api
    write_endpoints(profiles, [dict(EP_OA, base_url="http://x"),
                             dict(EP_OA, id="stub-oa2", base_url="http://y")])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa", "model": "m1"}})
    snap = api.pin_bindings()
    assert snap["roles"]["rimbrain.plan"]["endpoint_id"] == "stub-oa"
    # rebind live afterwards; pinned resolution is unchanged
    rr.set_binding("rimbrain.plan", "stub-oa2", "m1")
    live = rb.resolve_role("rimbrain.plan")
    assert live["resolved"]["endpoint_id"] == "stub-oa2"
    pinned = rb.resolve_role("rimbrain.plan", pinned=snap)
    assert pinned["pinned"] and pinned["resolved"]["endpoint_id"] == "stub-oa"
    assert pinned["resolved"]["model"] == "m1"
    missing = rb.resolve_role("rimbrain.review", pinned=snap)
    assert not missing["ok"] and missing["error"]["code"] == "bindings.unresolved"


def test_usage_tracker_and_manifest(profiles, stub_server):
    from runtime import api
    from runtime import provenance as rp2
    api.DEFAULT_TRACKER.reset()
    StubHandler.RESPONSES["/v1/chat/completions"] = (
        200, {"usage": {"prompt_tokens": 10, "completion_tokens": 4}})
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    rc.openai_compat_chat("stub-oa", "m1", [{"role": "user", "content": "hi"}],
                          usage_tracker=api.DEFAULT_TRACKER)
    rc.openai_compat_chat("stub-oa", "m1", [{"role": "user", "content": "hi2"}],
                          usage_tracker=api.DEFAULT_TRACKER)
    snap = api.DEFAULT_TRACKER.snapshot()
    assert snap["stub-oa"]["calls"] == 2
    assert snap["stub-oa"]["prompt_tokens"] == 20
    assert snap["stub-oa"]["completion_tokens"] == 8
    manifest = rp2.episode_manifest(usage=snap)
    assert manifest["usage"]["stub-oa"]["calls"] == 2
    # usage key never touches roles resolution
    assert "usage" not in rp2.episode_manifest()
