"""Thin bridge RPC client for the dispatcher (feature 004; FR-301, T083).

Only the dispatcher uses this — no other runtime code path may invoke bridge
game RPCs (single writer, FR-301). Errors are structured
``{ok:false,error:{code,message,retryable,details}}`` (common/error), never
raised raw.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


def err(code: str, message: str, retryable: bool = False,
        details: dict | None = None) -> dict:
    error = {"code": code, "message": message, "retryable": bool(retryable)}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


class BridgeClient:
    """``POST <base>/rpc {method, params}`` -> ``{ok, result|error}``."""

    def __init__(self, base_url: str = DEFAULT_BRIDGE_URL,
                 timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)

    def rpc(self, method: str, params: dict | None = None) -> dict:
        body = json.dumps({"method": method, "params": params or {}}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/rpc", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            return err("bridge.transport.http",
                       f"{method}: HTTP {exc.code} from {self.base_url}",
                       retryable=exc.code >= 500,
                       details={"method": method, "status": exc.code})
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return err("bridge.transport.unreachable",
                       f"{method}: cannot reach {self.base_url}: {exc}",
                       retryable=True, details={"method": method})
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return err("bridge.transport.bad_response",
                       f"{method}: non-JSON response: {exc}",
                       retryable=True, details={"method": method})
        if isinstance(parsed, dict) and "ok" in parsed:
            return parsed
        return {"ok": True, "result": parsed}

    def status(self) -> dict:
        return self.rpc("game.status", {})
