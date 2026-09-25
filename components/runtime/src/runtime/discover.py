"""Local endpoint discovery (feature 002; FR-007, US4).

Scans well-known local ports concurrently and returns candidate endpoint
entries with discovered models. Absent servers are silently skipped.
"""

from __future__ import annotations

import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_PORTS = [
    # (port, api, label, base_url template, decide_path)
    (1234, "openai-compat", "LM Studio", "http://127.0.0.1:{p}/v1", None),
    (11434, "openai-compat", "Ollama", "http://127.0.0.1:{p}/v1", None),
    (8000, "openai-compat", "vLLM", "http://127.0.0.1:{p}/v1", None),
    (8080, "openai-compat", "llama.cpp", "http://127.0.0.1:{p}/v1", None),
    (8780, "systemone", "Laya decision server", "http://127.0.0.1:{p}", "/v1/systemone"),
]

_CONNECT_S = 0.75
_HTTP_S = 3


def _probe_port(port: int, api: str, label: str, url_tpl: str,
                decide_path: str | None) -> dict | None:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=_CONNECT_S).close()
    except OSError:
        return None
    base = url_tpl.format(p=port)
    models: list[str] = []
    try:
        if api == "openai-compat":
            body = json.loads(urllib.request.urlopen(
                base + "/models", timeout=_HTTP_S).read() or b"{}")
            models = [m["id"] for m in body.get("data", []) if m.get("id")]
        else:  # systemone: health then /v1/models
            urllib.request.urlopen(base + "/health", timeout=_HTTP_S).read()
            try:
                body = json.loads(urllib.request.urlopen(
                    base + "/v1/models", timeout=_HTTP_S).read() or b"[]")
                raw = body.get("data", body if isinstance(body, list) else [])
                models = [m.get("id") if isinstance(m, dict) else m for m in raw]
            except Exception:
                pass
    except Exception:
        return None  # port open but wrong protocol — not this kind of server
    ep = {
        "id": f"discovered-{label.lower().replace(' ', '-')}-{port}",
        "label": f"{label} (auto-discovered :{port})",
        "api": api,
        "base_url": base,
        "api_key_ref": None,
        "models": models,
        "capabilities": (["typed_decisions"] if api == "systemone"
                         else ["chat", "embeddings"]),
    }
    if decide_path:
        ep["decide_path"] = decide_path
    return ep


def scan_local() -> list[dict]:
    """Concurrent scan; returns candidate endpoint entries (not registered)."""
    with ThreadPoolExecutor(max_workers=len(_PORTS)) as pool:
        results = list(pool.map(lambda a: _probe_port(*a), _PORTS))
    return [r for r in results if r]
