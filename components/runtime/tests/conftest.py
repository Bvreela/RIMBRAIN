"""Runtime tests: offline via stub HTTP servers + isolated profiles dir."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

import runtime.registry as registry  # noqa: E402


@pytest.fixture()
def profiles(tmp_path, monkeypatch):
    """Isolated profiles dir; yields the dir for test-specific writes."""
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setenv(registry.PROFILES_ENV, str(d))
    return d


def write_endpoints(d: Path, endpoints: list[dict]) -> None:
    (d / "endpoints.yaml").write_text(
        yaml.safe_dump({"endpoints": endpoints}), encoding="utf-8")


def write_bindings(d: Path, bindings: dict, degraded: dict | None = None) -> None:
    doc = {"bindings": bindings, "degraded_paths": degraded or {}}
    (d / "bindings.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


class StubHandler(BaseHTTPRequestHandler):
    """Configurable stub: routes via class-level RESPONSES {path: (status, body)}."""

    RESPONSES: dict = {}
    RECEIVED: list = []

    def _reply(self, method: str):
        StubHandler.RECEIVED.append(
            (method, self.path, self.headers.get("Authorization")))
        body = b"{}"
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            StubHandler.RECEIVED[-1] = (*StubHandler.RECEIVED[-1], body)
        status, payload = StubHandler.RESPONSES.get(self.path, (404, {}))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    do_GET = lambda s: StubHandler._reply(s, "GET")
    do_POST = lambda s: StubHandler._reply(s, "POST")

    def log_message(self, *a):
        pass


@pytest.fixture()
def stub_server():
    """HTTPServer on an ephemeral port; configure via StubHandler.RESPONSES."""
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    StubHandler.RESPONSES = {}
    StubHandler.RECEIVED = []
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
