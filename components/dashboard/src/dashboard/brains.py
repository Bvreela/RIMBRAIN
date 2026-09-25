"""Brains panel model (feature 018; FR-006..009).

One row per bound role — the BIGbrain tier (plan/review/improve), the
fastbrain selector, and the embed role. ``check_all`` runs one
``api.probe_live`` call per role on worker threads and posts results to
a queue; ``classify`` maps a result envelope to a (tone, text) row.

Pure logic — the facade object is passed in so tests stub it and the
standalone overlay can hand a sentinel when runtime is unimportable.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

# (label, role, tier) — display order
ROLES = [
    ("plan", "rimbrain.plan", "BIGbrain"),
    ("review", "rimbrain.review", "BIGbrain"),
    ("improve", "rimbrain.improve", "BIGbrain"),
    ("select", "rimbrain.select", "fastbrain"),
    ("embed", "rimbrain.embed", "embed"),
]


def classify(res: dict) -> tuple[str, str]:
    """(tone, text) for one probe_live envelope. tone in
    ok|warn|bad|dim — the row color and verdict text."""
    if not res.get("ok"):
        code = (res.get("error") or {}).get("code", "error")
        return "bad", code
    v = res.get("verdict")
    if v == "answered":
        return "ok", f"answered {res.get('latency_ms', 0):.0f}ms"
    if v == "model_failed":
        t = "model failed"
        if res.get("status"):
            t += f" HTTP {res['status']}"
        if res.get("retryable"):
            t += " (busy)"
        return "warn", t
    if v == "unreachable":
        return "bad", "unreachable"
    if v == "missing_secret":
        return "bad", "missing secret"
    if v == "fallback_only":
        return "dim", f"fallback only: {res.get('name') or '?'}"
    if v == "unbound":
        return "dim", "unbound"
    return "dim", str(v or "?")


def row_model(res: dict) -> dict:
    """Row render model: {role, verdict, tone, text, target, fallbacks}."""
    tone, text = classify(res)
    ep, model = res.get("endpoint"), res.get("model")
    target = f"{ep} · {model}" if ep else (res.get("name") or "—")
    return {"role": res.get("role"), "verdict": res.get("verdict"),
            "tone": tone, "text": text, "target": target,
            "fallbacks": list(res.get("fallbacks") or [])}


def serve_cmd(ep: dict) -> list | None:
    """Argv to launch this endpoint's local server, or None when the
    endpoint declares no ``serve`` block or its exe is absent."""
    cmd = ((ep or {}).get("serve") or {}).get("cmd")
    if isinstance(cmd, list) and cmd and Path(str(cmd[0])).is_file():
        return [str(c) for c in cmd]
    return None


def check_all(api, out_queue: "queue.Queue", roles=None) -> list:
    """Spawn one daemon thread per role; each posts
    ``(role, result_dict)`` to ``out_queue``. Never raises — a throwing
    facade yields an error envelope per role."""
    threads = []
    for _label, role, _tier in (roles or ROLES):
        def work(r=role):
            try:
                res = api.probe_live(r)
            except Exception as exc:
                res = {"ok": False, "error": {
                    "code": "probe.error", "message": str(exc)[:160],
                    "retryable": True}}
            out_queue.put((r, res))
        t = threading.Thread(target=work, daemon=True)
        t.start()
        threads.append(t)
    return threads
