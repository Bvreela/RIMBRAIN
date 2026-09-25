"""Game-surface probe for the launcher (UR-ARC-009, feature 018).

Three checks against the loop's --bridge surface, stdlib-only so the
overlay answers them even when the runtime facade is unavailable:

- rimbridge — zorrobyte RimBridge HTTP JSON-RPC (default :8765):
  TCP then GET /health. The loop's dispatch target; required.
- steward — RimBridge:Steward add-on: POST /rpc steward.status.
  Optional: the loop runs without it, but govern.stock/hunting levers
  and standing orders are dead without it.
- gabp — pardeike RimBridgeServer (GABP, :5174): TCP presence only
  (auth needs the Player.log token; presence is the signal).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse


def _tcp(host: str, port: int, timeout_s: float) -> str | None:
    try:
        socket.create_connection((host, port), timeout=timeout_s).close()
        return None
    except OSError as exc:
        return str(exc)


def _get_json(req, timeout_s: float):
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read() or b"null"), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(getattr(exc, "reason", exc))


def _rpc(base: str, method: str, timeout_s: float):
    return _get_json(urllib.request.Request(
        base + "/rpc",
        data=json.dumps({"method": method, "params": {}}).encode(),
        headers={"Content-Type": "application/json"}), timeout_s)


def bridge_status(url: str, *, gabp_port: int = 5174,
                  timeout_s: float = 4.0) -> dict:
    """{ok, rimbridge, steward, gabp}; ok = required bridge answered."""
    p = urlparse(url or "http://127.0.0.1:8765")
    host = p.hostname or "127.0.0.1"
    port = p.port or (443 if p.scheme == "https" else 80)
    base = f"{p.scheme or 'http'}://{host}:{port}"
    out: dict = {"ok": False,
                 "rimbridge": {}, "steward": {}, "gabp": {}}

    err = _tcp(host, port, timeout_s)
    if err:
        out["rimbridge"] = {"ok": False,
                            "detail": f"TCP {host}:{port}: {err}"}
        out["steward"] = {"ok": False, "detail": "bridge down"}
        out["gabp"] = _gabp_row(host, gabp_port)
        return out

    body, herr = _get_json(base + "/health", timeout_s)
    if herr or not isinstance(body, dict) or not body.get("ok"):
        out["rimbridge"] = {"ok": False,
                            "detail": herr or "/health not ok"}
        out["steward"] = {"ok": False, "detail": "bridge unhealthy"}
        out["gabp"] = _gabp_row(host, gabp_port)
        return out

    out["rimbridge"] = {"ok": True,
                        "detail": f"health ok · v{body.get('version', '?')}"
                                  f" · {body.get('frames', '?')} frames"}
    out["ok"] = True

    res, rerr = _rpc(base, "steward.status", timeout_s)
    if rerr:
        out["steward"] = {"ok": False, "detail": rerr}
    elif isinstance(res, dict) and res.get("ok") \
            and isinstance(res.get("result"), dict):
        r = res["result"]
        orders = r.get("orders") or []
        en = sum(1 for o in orders if isinstance(o, dict)
                 and o.get("enabled"))
        engs = [k for k, v in (r.get("enabled") or {}).items() if v]
        out["steward"] = {"ok": True,
                          "detail": f"{'+'.join(engs) or 'idle'} on · "
                                    f"{en}/{len(orders)} orders"}
    else:
        out["steward"] = {"ok": False, "detail": "no steward.* — "
                          "RimBridgeSteward add-on not loaded (optional)"}

    out["gabp"] = _gabp_row(host, gabp_port)
    return out


def _gabp_row(host: str, port: int) -> dict:
    err = _tcp(host, port, 1.5)
    return {"ok": err is None,
            "detail": f"listening :{port}" if err is None
                      else "not listening (optional)"}
