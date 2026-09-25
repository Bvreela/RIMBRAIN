"""Feature 018 T013 — brain verdict -> row mapping (stubbed facade)."""

from __future__ import annotations

import queue
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "dashboard" / "src"))

from dashboard import brains  # noqa: E402


class StubApi:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def probe_live(self, role, **_):
        self.calls.append(role)
        return self.results[role]


def _res(verdict, **kw):
    return {"ok": True, "role": "rimbrain.plan", "verdict": verdict,
            "endpoint": "ep", "model": "m", "api": "openai-compat",
            "fallbacks": [], "degraded": False, **kw}


def test_answered_is_green_with_latency():
    tone, text = brains.classify(_res("answered", latency_ms=55.2))
    assert tone == "ok" and "55ms" in text


def test_model_failed_is_amber_with_status():
    tone, text = brains.classify(_res("model_failed", status=429,
                                      retryable=True))
    assert tone == "warn" and "429" in text and "busy" in text


def test_unreachable_is_red():
    assert brains.classify(_res("unreachable"))[0] == "bad"


def test_missing_secret_is_red():
    assert brains.classify(_res("missing_secret"))[0] == "bad"


def test_fallback_only_is_dim_with_name():
    tone, text = brains.classify(_res("fallback_only",
                                      endpoint=None, model=None,
                                      name="rules-only"))
    assert tone == "dim" and "rules-only" in text


def test_unbound_is_dim():
    assert brains.classify(_res("unbound", endpoint=None,
                                model=None))[0] == "dim"


def test_error_envelope_is_bad():
    tone, text = brains.classify({"ok": False, "error": {
        "code": "probe.error", "message": "x"}})
    assert tone == "bad" and text == "probe.error"


def test_row_model_shows_target_and_fallbacks():
    res = _res("answered", endpoint="local-laya", model="laya",
               fallbacks=["openrouter-decisions:~t/jev", "rules"])
    row = brains.row_model(res)
    assert row["target"] == "local-laya · laya"
    assert row["fallbacks"] == ["openrouter-decisions:~t/jev", "rules"]
    fb = brains.row_model(_res("fallback_only", endpoint=None,
                               name="rules"))
    assert fb["target"] == "rules"


def test_check_all_posts_every_role():
    api = StubApi({role: _res("answered") for _l, role, _t in
                   brains.ROLES})
    q = queue.Queue()
    threads = brains.check_all(api, q)
    for t in threads:
        t.join(timeout=5)
    got = {q.get_nowait()[0] for _ in range(len(brains.ROLES))}
    assert got == {role for _l, role, _t in brains.ROLES}
    assert set(api.calls) == got


def test_check_all_survives_throwing_facade():
    class Boom:
        def probe_live(self, role, **_):
            raise RuntimeError("no runtime")
    q = queue.Queue()
    threads = brains.check_all(Boom(), q)
    for t in threads:
        t.join(timeout=5)
    role, res = q.get_nowait()
    assert res["ok"] is False
    tone, _ = brains.classify(res)
    assert tone == "bad"


def test_serve_cmd(tmp_path):
    exe = tmp_path / "srv.exe"
    exe.write_text("x")
    ep = {"serve": {"cmd": [str(exe), "serve", "--port", "8780"],
                    "path_prepend": [str(tmp_path)]}}
    assert brains.serve_cmd(ep) == [str(exe), "serve", "--port", "8780"]


def test_serve_cmd_missing_exe_or_block(tmp_path):
    assert brains.serve_cmd({}) is None
    assert brains.serve_cmd({"serve": {}}) is None
    assert brains.serve_cmd({"serve": {
        "cmd": [str(tmp_path / "nope.exe")]}}) is None
