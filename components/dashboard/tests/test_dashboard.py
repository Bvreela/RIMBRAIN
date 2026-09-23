"""Dashboard API tests (T067) — ephemeral server + urllib, isolated profiles."""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "dashboard" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))

import runtime.registry as rr  # noqa: E402
from dashboard.server import Handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

EP = {"id": "ep1", "api": "openai-compat", "base_url": "http://x/v1",
      "api_key_ref": "env:TEST_DASH_KEY", "models": ["m1"],
      "capabilities": ["chat"]}


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv(rr.PROFILES_ENV, str(tmp_path / "profiles"))
    (tmp_path / "profiles").mkdir()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", tmp_path / "profiles"
    srv.shutdown()


def _get(base, path):
    return json.loads(urllib.request.urlopen(base + path, timeout=5).read())


def _send(base, path, method, body=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body or {}).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=5).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_page_serves(server):
    base, _ = server
    body = urllib.request.urlopen(base + "/", timeout=5).read()
    assert b"Model Endpoints" in body


def test_endpoint_crud_via_api(server):
    base, prof = server
    assert _get(base, "/api/endpoints")["endpoints"] == []
    r = _send(base, "/api/endpoints", "POST", EP)
    assert r["ok"]
    assert _get(base, "/api/endpoints")["endpoints"][0]["id"] == "ep1"
    r = _send(base, "/api/endpoints/ep1", "PUT", {"label": "renamed"})
    assert r["ok"] and r["result"]["label"] == "renamed"
    r = _send(base, "/api/endpoints/ep1", "DELETE")
    assert r["ok"]
    assert _get(base, "/api/endpoints")["endpoints"] == []


def test_yaml_is_authoritative(server):
    """Hand-edited YAML is what the API serves (SC-003)."""
    base, prof = server
    _send(base, "/api/endpoints", "POST", EP)
    doc = yaml.safe_load((prof / "endpoints.yaml").read_text())
    doc["endpoints"][0]["label"] = "hand-edited"
    (prof / "endpoints.yaml").write_text(yaml.safe_dump(doc))
    assert _get(base, "/api/endpoints")["endpoints"][0]["label"] == "hand-edited"


def test_secrets_never_in_responses(server, monkeypatch):
    monkeypatch.setenv("TEST_DASH_KEY", "supersecret-value")
    base, _ = server
    _send(base, "/api/endpoints", "POST", EP)
    for path in ("/api/endpoints", "/api/bindings", "/", "/api/discover"):
        body = urllib.request.urlopen(base + path, timeout=5).read()
        assert b"supersecret-value" not in body


def test_set_binding_via_api(server):
    base, _ = server
    _send(base, "/api/endpoints", "POST", EP)
    r = _send(base, "/api/bindings", "POST",
              {"role": "rimbrain.plan", "endpoint": "ep1", "model": "m1"})
    assert r["ok"]
    assert _get(base, "/api/bindings")["bindings"]["rimbrain.plan"]["endpoint"] == "ep1"


def test_probe_unknown_endpoint(server):
    base, _ = server
    r = _send(base, "/api/probe/ghost", "POST")
    assert not r["ok"] and r["error"]["code"] == "registry.endpoint.missing"
