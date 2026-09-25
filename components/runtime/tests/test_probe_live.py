"""Feature 018 T006 — probe_live verdict matrix (stubbed transports)."""

from __future__ import annotations

import json

from conftest import StubHandler, write_bindings, write_endpoints

from runtime import probe as rp

EP_OA = {"id": "stub-oa", "api": "openai-compat", "base_url": None,
         "api_key_ref": None, "models": ["m1"],
         "capabilities": ["chat", "tool_calls"]}
EP_SO = {"id": "stub-so", "api": "systemone", "base_url": None,
         "decide_path": "/v1/systemone", "api_key_ref": None,
         "models": ["laya"], "capabilities": ["typed_decisions"]}
EP_EMB = {"id": "stub-emb", "api": "openai-compat", "base_url": None,
          "api_key_ref": None, "models": ["emb1"],
          "capabilities": ["embeddings"]}


def _last_body():
    return json.loads(StubHandler.RECEIVED[-1][3] or b"{}")


def test_answered_decide_omits_model_on_local(profiles, stub_server):
    write_endpoints(profiles, [dict(EP_SO, base_url=stub_server)])
    write_bindings(profiles,
                   {"rimbrain.select": {"endpoint": "stub-so",
                                        "model": "laya"}},
                   {"rimbrain.select": ["rules"]})
    StubHandler.RESPONSES["/v1/systemone"] = (200, {"answers": {}})
    res = rp.probe_live("rimbrain.select")
    assert res["ok"] and res["verdict"] == "answered"
    assert res["endpoint"] == "stub-so" and res["model"] == "laya"
    assert res["api"] == "systemone" and res["latency_ms"] >= 0
    assert res["fallbacks"] == ["rules"]
    assert res["checked_utc"]
    # loopback decide probes omit `model` — locals route one family
    assert "model" not in _last_body()
    assert _last_body()["questions"]


def test_answered_chat_minimal_payload(profiles, stub_server):
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa",
                                      "model": "m1"}})
    StubHandler.RESPONSES["/v1/chat/completions"] = (
        200, {"choices": [{"message": {"content": ""}}]})
    res = rp.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "answered"
    assert res["endpoint"] == "stub-oa" and res["model"] == "m1"
    body = _last_body()
    assert body["model"] == "m1" and body["max_tokens"] == 1
    assert body["messages"] == [{"role": "user", "content": "ping"}]


def test_answered_embeddings_ping(profiles, stub_server):
    write_endpoints(profiles, [dict(EP_EMB, base_url=stub_server + "/v1")])
    write_bindings(profiles,
                   {"rimbrain.embed": {"endpoint": "stub-emb",
                                       "model": "emb1"}})
    StubHandler.RESPONSES["/v1/embeddings"] = (200, {"data": []})
    res = rp.probe_live("rimbrain.embed")
    assert res["ok"] and res["verdict"] == "answered"
    body = _last_body()
    assert body == {"model": "emb1", "input": ["ping"]}


def test_model_failed_http_error(profiles, stub_server):
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa",
                                      "model": "m1"}},
                   {"rimbrain.plan": ["rules-only"]})
    StubHandler.RESPONSES["/v1/chat/completions"] = (503, {})
    res = rp.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "model_failed"
    assert res["status"] == 503 and res["retryable"] is True
    assert res["fallbacks"] == ["rules-only"]


def test_unreachable_tcp(profiles):
    # nothing listens on the port -> TCP precheck fails before any HTTP
    write_endpoints(profiles, [dict(EP_OA, base_url="http://127.0.0.1:9/v1")])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa",
                                      "model": "m1"}})
    res = rp.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "unreachable"
    assert res["endpoint"] == "stub-oa"


def test_missing_secret(profiles, stub_server, monkeypatch):
    monkeypatch.delenv("MISSING_PROBE_KEY", raising=False)
    ep = dict(EP_OA, base_url=stub_server + "/v1",
              api_key_ref="env:MISSING_PROBE_KEY")
    write_endpoints(profiles, [ep])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa",
                                      "model": "m1"}})
    res = rp.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "missing_secret"
    assert "MISSING_PROBE_KEY" in res["detail"]


def test_fallback_only_sentinel(profiles):
    # no binding; degraded path resolves to the rules sentinel
    write_endpoints(profiles, [])
    write_bindings(profiles, {},
                   {"rimbrain.plan": ["rules-only"]})
    res = rp.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "fallback_only"
    assert res["name"] == "rules-only" and res["endpoint"] is None
    assert res["degraded"] is True


def test_unbound_role(profiles):
    write_endpoints(profiles, [])
    write_bindings(profiles, {})
    res = rp.probe_live("rimbrain.review")
    assert res["ok"] and res["verdict"] == "unbound"
    assert res["endpoint"] is None


def test_facade_delegates(profiles, stub_server):
    from runtime import api
    write_endpoints(profiles, [dict(EP_OA, base_url=stub_server + "/v1")])
    write_bindings(profiles,
                   {"rimbrain.plan": {"endpoint": "stub-oa",
                                      "model": "m1"}})
    StubHandler.RESPONSES["/v1/chat/completions"] = (200, {"choices": []})
    res = api.probe_live("rimbrain.plan")
    assert res["ok"] and res["verdict"] == "answered"
