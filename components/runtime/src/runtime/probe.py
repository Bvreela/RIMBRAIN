"""Endpoint health/capability probe (feature 002; FR-005/FR-006, US3).

Per endpoint: TCP connect → api-shaped model listing → declared-capability
note. Classification: transport/timeout → transient ``retryable:true``;
HTTP 4xx → hard; 5xx (demand limits etc.) → transient. ``strict`` endpoints
receive no extension headers/bodies.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from .registry import err, get_endpoint
from .secrets import SecretError, resolve_api_key

CONNECT_TIMEOUT_S = 5
HTTP_TIMEOUT_S = 10


def _tcp_check(host: str, port: int) -> str | None:
    try:
        socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S).close()
        return None
    except OSError as exc:
        return str(exc)


def _http_get(url: str, key: str | None) -> dict:
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return {"ok": True, "status": resp.status,
                    "body": json.loads(resp.read() or b"null")}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "transient": exc.code >= 500}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "transient": True,
                "detail": str(getattr(exc, "reason", exc))}


def _strip_model_prefix(mid: str) -> str:
    # Gemini's OpenAI shim advertises "models/<id>"; declared ids are bare.
    return mid.split("/", 1)[-1] if mid.startswith("models/") else mid


def _model_list(api: str, base_url: str, decide_path: str | None,
                key: str | None, declared_model: str | None = None) -> dict:
    if api == "openai-compat":
        r = _http_get(base_url.rstrip("/") + "/models", key)
        if r["ok"]:
            data = r["body"] or {}
            ids = [_strip_model_prefix(m.get("id"))
                   for m in data.get("data", []) if m.get("id")]
            return {"ok": True, "models": ids}
        return r
    if api == "systemone":
        health = _http_get(base_url.rstrip("/") + "/health", key)
        if health["ok"]:
            models = _http_get(base_url.rstrip("/") + "/v1/models", key)
            ids = []
            if models["ok"]:
                body = models["body"] or {}
                raw = body.get("data", body.get("models",
                              body if isinstance(body, list) else []))
                ids = [(m.get("id") or m.get("name"))
                       if isinstance(m, dict) else m for m in raw]
            return {"ok": True, "models": ids}
        # No /health (hosted decisions endpoints): the decide route is the
        # capability check — a minimal typed question must answer 2xx.
        if decide_path:
            decide = _decide_probe(base_url.rstrip("/") + decide_path, key,
                                   declared_model)
            if decide["ok"]:
                return {"ok": True, "models": decide.get("models", [])}
        return health
    return {"ok": False, "status": 0, "detail": f"unknown api {api!r}"}


def _decide_probe(url: str, key: str | None, model: str | None = None) -> dict:
    """POST a minimal typed question; reachable decide route == healthy."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {"state": "probe",
               "questions": {"p": {"type": "choice", "instructions": "probe",
                                   "criteria": {"a": "a", "b": "b"}}}}
    if model:
        payload["model"] = model  # hosted decisions requires it; locals route
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            body = json.loads(resp.read() or b"{}")
            return {"ok": True, "models": [] if not isinstance(body, dict)
                    else body.get("models", [])}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "transient": exc.code >= 500}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "transient": True,
                "detail": str(getattr(exc, "reason", exc))}


def probe_endpoint(id_or_entry, *, timeout_note: bool = True) -> dict:
    """Probe one endpoint by registry id or raw entry dict."""
    ep = get_endpoint(id_or_entry) if isinstance(id_or_entry, str) else id_or_entry
    if ep is None:
        return err("registry.endpoint.missing",
                   f"no endpoint id {id_or_entry!r}", {"endpoint": id_or_entry})
    parsed = urlparse(ep["base_url"])
    host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.monotonic()

    tcp_err = _tcp_check(host, port)
    if tcp_err:
        return err("probe.unreachable",
                   f"{ep['id']}: TCP {host}:{port} failed: {tcp_err}",
                   {"endpoint": ep["id"], "host": host, "port": port},
                   retryable=True)

    try:
        key = resolve_api_key(ep.get("api_key_ref"))
    except SecretError as exc:
        return exc.envelope

    declared_model = (ep.get("models") or [None])[0]
    listing = _model_list(ep["api"], ep["base_url"], ep.get("decide_path"),
                          key, declared_model)
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    if not listing["ok"]:
        transient = bool(listing.get("transient", listing["status"] >= 500))
        return err(
            "probe.models_failed" if not transient else "probe.transient",
            f"{ep['id']}: model listing failed"
            + (f" (HTTP {listing['status']})" if listing.get("status") else f" ({listing.get('detail')})"),
            {"endpoint": ep["id"], "status": listing.get("status")},
            retryable=transient,
        )

    advertised = set(listing["models"])
    missing = [m for m in ep.get("models", []) if advertised and m not in advertised]
    return {
        "ok": True,
        "endpoint": ep["id"],
        "models": listing["models"],
        "declared_missing": missing,
        "capabilities": ep.get("capabilities", []),
        "latency_ms": latency_ms,
        "probed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
