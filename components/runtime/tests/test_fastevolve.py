"""Fast-evolve play mode tests (feature 021; ADR-020).

Unit tests drive ``FastEvolve.tick`` directly against SimGame with the
packs/state dirs redirected to tmp; the CLI tests exercise ``main()``.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import evolve, fastevolve, templates  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402
from runtime.loop import main as loop_main, run  # noqa: E402


@pytest.fixture()
def packs(tmp_path, monkeypatch):
    src = REPO_ROOT / "components" / "rimbrain" / "packs"
    dst = tmp_path / "packs"
    for pid in ("start-mode-v0", "improve-v0"):
        (dst / pid).mkdir(parents=True)
        shutil.copy(src / pid / "pack.yaml", dst / pid / "pack.yaml")
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(dst))
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    return dst


def _dispatcher(game, *, grant=True):
    d = Dispatcher(game, fair=True, allow_save_load=grant,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    return d


def _resolver_broken(name, **kw):
    return {"ok": False, "error": {"code": "bindings.unresolved",
                                   "message": "no role"}}


def _mk_fe(pack_doc, tmp_path, **over):
    pack = copy.deepcopy(pack_doc)
    cfg = dict(pack.get("fastevolve") or {})
    cfg.update(over)
    pack["fastevolve"] = cfg
    return fastevolve.FastEvolve(pack, tmp_path / "state",
                                 clock=lambda: "2026-01-01T00:00:00Z")


def _obs(day=0, downed=0, fires=0):
    return {"day": day, "tick": day * 60000,
            "colonists": {"downed": downed}, "map": {"fires": fires}}


def _types(events):
    return [e.get("event_type") for e in events]


# -- tracker / session ---------------------------------------------------------

def test_tracker_prefers_earliest_day_save(packs):
    game = SimGame(autosaves=[])          # none at run start
    tr = fastevolve.AutosaveTracker(fastevolve.DEFAULTS)
    s = fastevolve.DayState(); s.day = 3
    game.sim_autosave("autosave-day3-0900")
    names = tr.scan(game, day=3, poll=10)
    assert tr.anchor(s, names) == ("autosave-day3-0900", False)
    game.sim_autosave("autosave-day3-1700")  # later save never displaces
    names = tr.scan(game, day=3, poll=20)
    assert tr.anchor(s, names) == ("autosave-day3-0900", False)


def test_tracker_stale_fallback_and_max_age(packs):
    game = SimGame(autosaves=["autosave-old"])
    tr = fastevolve.AutosaveTracker(fastevolve.DEFAULTS)
    names = tr.scan(game, day=1, poll=0)   # observed on day 1
    s = fastevolve.DayState(); s.day = 2   # next day, nothing new yet
    assert tr.anchor(s, names) == ("autosave-old", True)
    s.day = 5                              # beyond max_anchor_age_days=1
    assert tr.anchor(s, names) == (None, False)


def test_daystate_roundtrip(tmp_path):
    s = fastevolve.DayState()
    s.day, s.anchor, s.reloads_used, s.exhausted = 4, "asv", 2, True
    s.attempts = [{"n": 1, "reloaded": True}]
    p = tmp_path / "fastevolve.json"
    s.save(p)
    r = fastevolve.DayState.load(p)
    assert (r.day, r.anchor, r.reloads_used, r.exhausted) \
        == (4, "asv", 2, True)
    assert r.attempts == [{"n": 1, "reloaded": True}]
    assert json.loads(p.read_text())["schema_version"] == 0


def test_simgame_save_load_roundtrip(packs):
    game = SimGame()
    game.items.append({"id": "x", "pos": [1, 1]})
    assert game.rpc("game.save", {"name": "a1"})["ok"]
    rows = game.rpc("game.list_saves")["result"]
    assert rows[0]["name"] == "a1" and rows[0]["modified"]
    game.items.clear()
    assert game.rpc("game.load", {"name": "a1"})["ok"]
    assert any(i["id"] == "x" for i in game.items)
    assert not game.rpc("game.load", {"name": "nope"})["ok"]


# -- tick orchestration --------------------------------------------------------

def _tick(fe, d, game, ledger, pack, obs, poll, events, **kw):
    return fe.tick(d, game, ledger, pack, obs, tick=0, poll=poll,
                   emit=events.append, resolver=_resolver_broken, **kw)


def test_failure_trigger_evolves_and_reloads(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
                0, events)
    assert out == {"reinit": True}
    types = _types(events)
    assert "fastevolve.day_start" in types
    assert "fastevolve.triggered" in types
    assert "mutation.triggered" in types      # the evolve pass ran
    assert "fastevolve.reloaded" in types
    assert fe.session.reloads_used == 1
    assert fe.session.attempts[0]["reloaded"] is True


def test_near_failure_trigger_fires(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=1),
                0, events)
    assert out == {"reinit": True}
    trig = next(e for e in events
                if e["event_type"] == "fastevolve.triggered")
    assert trig["payload"]["reason"] == "day_near_failure"


def test_pause_during_evolve(packs, tmp_path):
    seen = {}

    def _resolver(name, **kw):
        seen["paused"] = game._state.get("paused")
        return _resolver_broken(name, **kw)

    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl")
    fe = _mk_fe(d.pack["pack"], tmp_path)
    fe.tick(d, game, ledger, d.pack["pack"], _obs(downed=2), tick=0,
            poll=0, emit=lambda e: None, resolver=_resolver)
    assert seen["paused"] is True
    assert game._state["paused"] is False    # restored after the pass


def test_two_reloads_then_exhausted(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    for poll in range(3):                    # same day, keeps failing
        out = _tick(fe, d, game, ledger, d.pack["pack"],
                    _obs(downed=2), poll, events)
    types = _types(events)
    assert types.count("fastevolve.reloaded") == 2
    assert "fastevolve.exhausted" in types
    assert fe.session.exhausted and fe.session.reloads_used == 2
    assert out == {"reinit": False}          # third: evolve, no reload


def test_day_rollover_resets_budget(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    for poll in range(3):
        _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
              poll, events)
    assert fe.session.exhausted
    game.sim_autosave("autosave-2")
    out = _tick(fe, d, game, ledger, d.pack["pack"],
                _obs(day=1, downed=2), 3, events)
    s = fe.session
    assert (s.day, s.exhausted, s.reloads_used) == (1, False, 1)
    assert s.anchor == "autosave-2"
    assert out == {"reinit": True}


def test_missing_anchor_evolves_without_reload(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=[])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
                0, events)
    types = _types(events)
    assert "fastevolve.anchor_missing" in types
    assert "mutation.triggered" in types     # evolve still ran
    assert "fastevolve.reloaded" not in types
    assert fe.session.reloads_used == 0
    assert out == {"reinit": False}


def test_failed_load_consumes_attempt(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    orig = game.rpc

    def _flaky(method, params=None):
        if method == "game.load":
            return {"ok": False, "error": {"code": "x", "message": "no"}}
        return orig(method, params)

    game.rpc = _flaky
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
                0, events)
    assert fe.session.reloads_used == 1      # spent despite the failure
    assert fe.session.attempts[0]["reloaded"] is False
    assert out == {"reinit": False}


def test_midrun_promotion_installs_and_rebinds(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    state = tmp_path / "state"
    doc = yaml.safe_load(
        templates.pack_path("start-mode-v0").read_text(encoding="utf-8"))
    doc["revision"] = "v0+mut.fe"
    cdir = packs / "candidates"; cdir.mkdir(exist_ok=True)
    cand = cdir / "cand-mut-fe-01.yaml"
    cand.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    cand_hash = templates._hash_of(doc)
    evolve._append_lineage(state, {
        "candidate_id": cand.stem, "target_pack": "start-mode-v0",
        "candidate_path": str(cand), "candidate_hash": cand_hash,
        "state": "pending"})
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
                0, events)
    assert out == {"reinit": True}
    assert "fastevolve.promoted" in _types(events)
    assert templates.current_hash("start-mode-v0") == cand_hash
    assert d.pack["hash"] == cand_hash       # hash rebound — no drift
    assert evolve.lineage_rows(state)[-1]["mid_run"] is True


def test_fair_grant_is_scoped(packs, tmp_path):
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game, grant=True)
    assert d.dispatch("load-game", {"name": "autosave-1"})["ok"]
    # dev.* stays refused even under the grant
    tmpls = templates.templates_of(d._pack["pack"])
    tmpls.append({"id": "cheat", "method": "dev.god",
                  "params_schema": {}})
    r = d.dispatch("cheat", {})
    assert r["error"]["code"] == "dispatch.fair_mode"
    # and without the grant save/load stays refused
    d2 = _dispatcher(SimGame(autosaves=["a"]), grant=False)
    r = d2.dispatch("load-game", {"name": "a"})
    assert r["error"]["code"] == "dispatch.fair_mode"


def test_no_trigger_is_inert(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(), 0, events)
    assert out is None
    assert "fastevolve.triggered" not in _types(events)


# -- US3: retry policy is pack data ---------------------------------------

def _fail_env(tid="govern.g1"):
    return {"schema_version": 0, "event_id": "e1", "sequence": 1,
            "event_type": "task.transition", "game_tick": 1,
            "wall_time_utc": "t", "source": "test",
            "payload": {"task_id": tid, "to_state": "failed"},
            "correlation": {}, "revisions": {}, "privacy": {}}


def test_use_mutate_reuses_goal_triggers(packs, tmp_path):
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    fe.day_ps.note(_fail_env())          # a goal went terminal-failed
    reason, ev = fastevolve.check_day_triggers(
        _obs(), fe.day_ps, d.pack["pack"], fe.cfg, 1)
    assert reason == "day_failure" and ev.get("tasks")


def test_use_mutate_false_ignores_goal_triggers(packs, tmp_path):
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    fe = _mk_fe(d.pack["pack"], tmp_path,
                triggers={"use_mutate": False})
    fe.day_ps.note(_fail_env())
    reason, _ = fastevolve.check_day_triggers(
        _obs(), fe.day_ps, d.pack["pack"], fe.cfg, 1)
    assert reason is None


def test_zero_reload_budget_evolves_only(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path, max_reloads_per_day=0)
    out = _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2),
                0, events)
    types = _types(events)
    assert "mutation.triggered" in types         # evolve ran
    assert "fastevolve.exhausted" in types       # budget 0 -> exhausted
    assert "fastevolve.reloaded" not in types
    assert out == {"reinit": False}


def test_invalid_predicate_fails_pack_load(packs):
    doc = yaml.safe_load(
        (packs / "start-mode-v0" / "pack.yaml").read_text(encoding="utf-8"))
    doc["fastevolve"]["triggers"]["fail_when"] = \
        {"any": [{"field": "@obs:x", "op": "bogus"}]}
    (packs / "start-mode-v0" / "pack.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    import pytest as _pt
    with _pt.raises(Exception):
        _dispatcher(SimGame())


# -- US4: evidence ----------------------------------------------------------

def test_event_sequence_and_planning_block(packs, tmp_path):
    events: list[dict] = []
    game = SimGame(autosaves=["autosave-1"])
    d = _dispatcher(game)
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    fe = _mk_fe(d.pack["pack"], tmp_path)
    _tick(fe, d, game, ledger, d.pack["pack"], _obs(downed=2), 0, events)
    seq = [t for t in _types(events) if t.startswith("fastevolve.")]
    assert seq[:3] == ["fastevolve.day_start", "fastevolve.triggered",
                       "fastevolve.reloaded"]
    assert all(e.get("schema_version") == 0 for e in events)
    v = fe.view()
    assert v == {"day": 0, "anchor": "autosave-1", "reloads_used": 1,
                 "max_reloads": 2, "exhausted": False, "passes_used": 1}


# -- CLI ------------------------------------------------------------------

def test_cli_fastevolve_sim_runs(packs, tmp_path, capsys):
    rc = loop_main(["--mode", "fastevolve", "--game", "sim",
                    "--iterations", "2", "--pack", "start-mode-v0"])
    assert rc == 0


def test_cli_fastevolve_refuses_dev(packs, capsys):
    rc = loop_main(["--mode", "fastevolve", "--dev", "--game", "sim",
                    "--iterations", "1"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "loop.fastevolve_requires_fair"


def test_cli_fastevolve_live_needs_confirmation(packs, capsys):
    rc = loop_main(["--mode", "fastevolve", "--game", "live",
                    "--iterations", "1"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "loop.live_requires_confirmation"


def test_cli_fastevolve_refuses_scored(packs, capsys):
    rc = loop_main(["--mode", "fastevolve", "--scored", "--game", "sim",
                    "--iterations", "1"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "loop.fastevolve_scored"


def test_cli_run_still_default(packs, capsys):
    rc = loop_main(["--mode", "cycle", "--iterations", "1"])
    assert rc == 2   # cycle still requires --dev — unchanged behavior
