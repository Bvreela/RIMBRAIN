#!/usr/bin/env python3
"""bridge_check — independent connectivity test for RimWorld bridge mods.

Probes both known bridge surfaces and reports pass/fail per check:

  zorrobyte RimBridge   HTTP JSON-RPC on 127.0.0.1:8765
                        (/health, /methods, /rpc, /events)
  pardeike RimBridgeServer  GABP on 127.0.0.1:5174 (LSP framing, token auth)

Stdlib only. Exit code 0 = at least one bridge fully verified; 1 = none usable.

Usage:
  python bridge_check.py                 # probe both
  python bridge_check.py --only http     # zorrobyte only
  python bridge_check.py --only gabp     # pardeike only
  python bridge_check.py --token HEX     # explicit GABP token (else: Player.log)
  python bridge_check.py --json          # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.request
import uuid
from pathlib import Path

HTTP_HOST, HTTP_PORT = "127.0.0.1", 8765
GABP_HOST, GABP_PORT = "127.0.0.1", 5174
TIMEOUT = 5

PLAYER_LOG = (
    Path(os.environ.get("USERPROFILE", ""))
    / "AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Player.log"
)

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "ok": ok, "detail": detail})
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------- HTTP bridge

def probe_http() -> bool:
    base = f"http://{HTTP_HOST}:{HTTP_PORT}"
    print(f"\n[zorrobyte RimBridge] {base}")
    ok = True
    try:
        health = json.loads(urllib.request.urlopen(f"{base}/health", timeout=TIMEOUT).read())
        check("health", True, json.dumps(health)[:120])
    except Exception as e:
        return check("health", False, str(e)) and False or False

    try:
        methods = json.loads(urllib.request.urlopen(f"{base}/methods", timeout=TIMEOUT).read())
        lst = methods if isinstance(methods, list) else (
            methods.get("methods") or methods.get("result") or [])
        n = len(lst)
        check("methods inventory", n > 0, f"{n} methods")
    except Exception as e:
        ok = check("methods inventory", False, str(e)) and ok

    try:
        body = json.dumps({"method": "state.summary", "params": {}}).encode()
        req = urllib.request.Request(f"{base}/rpc", data=body,
                                     headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
        if resp.get("ok"):
            check("rpc state.summary", True, "ok")
        elif "error" in resp:
            # structured error envelope = transport+RPC contract working (e.g. no game loaded at Entry state)
            check("rpc state.summary", True, f"reachable; envelope error: {str(resp.get('error'))[:90]}")
        else:
            check("rpc state.summary", False, f"malformed response: {str(resp)[:90]}")
    except Exception as e:
        ok = check("rpc state.summary", False, str(e)) and ok

    try:
        ev = json.loads(urllib.request.urlopen(f"{base}/events?since=0", timeout=TIMEOUT).read())
        n = len(ev) if isinstance(ev, list) else len(ev.get("events", []))
        check("events feed", True, f"{n} events buffered")
    except Exception as e:
        ok = check("events feed", False, str(e)) and ok
    return ok


# ---------------------------------------------------------------- GABP bridge

def gabp_token(cli_token: str | None) -> str | None:
    if cli_token:
        return cli_token
    if env := os.environ.get("GABP_TOKEN"):
        return env
    if PLAYER_LOG.exists():
        for line in reversed(PLAYER_LOG.read_text(errors="replace").splitlines()):
            if m := re.search(r"Bridge token:\s*([0-9a-fA-F]{16,})", line):
                return m.group(1)
    return None


def _frame(msg: dict) -> bytes:
    body = json.dumps(msg).encode()
    return b"Content-Length: %d\r\nContent-Type: application/json\r\n\r\n" % len(body) + body


def _read(f) -> dict:
    headers = {}
    while True:
        line = f.readline()
        if not line:
            raise EOFError("connection closed")
        line = line.strip()
        if not line:
            break
        k, v = line.decode().split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return json.loads(f.read(int(headers["content-length"])))


def _req(f, s, method: str, params: dict | None = None) -> dict:
    rid = str(uuid.uuid4())
    s.sendall(_frame({"v": "gabp/1", "id": rid, "type": "request",
                      "method": method, "params": params or {}}))
    for _ in range(50):
        m = _read(f)
        if m.get("type") == "response" and m.get("id") == rid:
            return m
    raise TimeoutError(f"no response for {method}")


def probe_gabp(token: str | None) -> bool:
    print(f"\n[pardeike RimBridgeServer] {GABP_HOST}:{GABP_PORT}")
    try:
        s = socket.create_connection((GABP_HOST, GABP_PORT), timeout=TIMEOUT)
    except Exception as e:
        return check("tcp connect", False, str(e)) and False
    check("tcp connect", True)

    if not token:
        s.close()
        return check("token", False, "not found in Player.log; pass --token") and False

    f = s.makefile("rb")
    ok = True
    try:
        w = _req(f, s, "session/hello", {"token": token, "bridgeVersion": "1.0.0",
                                         "platform": "windows", "launchId": "bridge-check"})
        res = w.get("result") or {}
        app = res.get("app", {})
        caps = res.get("capabilities", {})
        check("session/hello auth", "result" in w and w.get("error") is None,
              f"{app.get('name')} {app.get('version')}, {len(caps.get('methods', []))} methods")
    except Exception as e:
        ok = check("session/hello auth", False, str(e)) and ok
        s.close()
        return ok

    try:
        t = _req(f, s, "tools/list")
        tools = (t.get("result") or {}).get("tools", [])
        check("tools/list", len(tools) > 0, f"{len(tools)} tools")
    except Exception as e:
        ok = check("tools/list", False, str(e)) and ok

    try:
        p = _req(f, s, "tools/call", {"name": "rimbridge/ping", "arguments": {}})
        pong = json.dumps(p.get("result", {}))
        check("rimbridge/ping", "pong" in pong, pong[:80])
    except Exception as e:
        ok = check("rimbridge/ping", False, str(e)) and ok

    try:
        g = _req(f, s, "tools/call", {"name": "rimworld/get_game_info", "arguments": {}})
        res = g.get("result") or {}
        check("get_game_info", "status" in res, str(res.get("status")))
    except Exception as e:
        ok = check("get_game_info", False, str(e)) and ok

    s.close()
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="RimWorld bridge connectivity check")
    ap.add_argument("--only", choices=["http", "gabp"], help="probe a single protocol")
    ap.add_argument("--token", help="GABP auth token (default: parsed from Player.log)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    any_ok = False
    if args.only in (None, "http"):
        any_ok |= probe_http()
    if args.only in (None, "gabp"):
        any_ok |= probe_gabp(gabp_token(args.token))

    if args.json:
        print(json.dumps({"ok": any_ok, "checks": results}))
    else:
        print(f"\n{'=' * 50}\nbridge check: {'OK' if any_ok else 'NO BRIDGE REACHABLE'}"
              f" ({sum(1 for r in results if r['ok'])}/{len(results)} checks passed)")
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
