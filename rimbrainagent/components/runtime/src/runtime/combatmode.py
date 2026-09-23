"""Bounded combat interpreter (feature 010/012; FR-1004, UR-BRN-011).

Runs strictly after start.completed. The pack's ``combat`` script drives
everything:

    setup[]   -> once (e.g. save checkpoint)
    per round: spawn[] -> engage rule-loop (until predicate / budgets)
               -> cleanup[] (strip, heal, undraft, reload checkpoint)

Spawn kinds, factions, counts, offsets, the engage predicate and its
rules, and every cleanup write are pack data executed through the single
dispatcher (FR-805). Round/verdict/casualty/tick accounting and the
checkpoint reload are engine bookkeeping — not strategy.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .planloop import observe
from .startmode import wire_sink
from . import policy, views


def _hostiles(game) -> list[dict]:
    """Live hostile pawns — state.threats hostiles, else empty
    (fail-closed). Dead/zero-health entries are dropped."""
    r = game.rpc("state.threats")
    res = r.get("result") if r.get("ok") else None
    if not isinstance(res, dict):
        return []
    hostiles = res.get("hostiles") or res.get("enemies") or []
    if isinstance(hostiles, dict):
        hostiles = hostiles.get("things") or hostiles.get("pawns") or []
    out = []
    for h in (hostiles if isinstance(hostiles, list) else []):
        if isinstance(h, dict) and (
                h.get("dead") or (h.get("health") is not None
                                  and float(h.get("health") or 0) <= 0)):
            continue
        out.append(h)
    return out


def _colonist_ids(obs: dict) -> list[str]:
    lst = ((obs.get("colonists") or {}).get("colonist_list")
           or obs.get("colonist_list") or [])
    out = []
    for c in lst:
        if isinstance(c, dict) and c.get("id"):
            out.append(c["id"])
        elif isinstance(c, str):
            out.append(c)
    return out


def _wait_playing(game, timeout_s: float = 30.0) -> bool:
    """game.load is async — poll until the map is live before any writes."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = game.rpc("game.status")
        res = r.get("result") if r.get("ok") else None
        if isinstance(res, dict) and res.get("state") in (None, "playing") \
                and isinstance(res.get("tick"), int):
            return True
        time.sleep(0.5)
    return False


def completed_event(rounds: int, spawned: int, cleared: int,
                    casualties: int, ticks: int, verdict: str,
                    seq: int, clock) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.combat-{seq:06d}",
        "sequence": seq,
        "event_type": "combat.completed",
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": "rimbrainagent.runtime.combatmode",
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": {
            "mode": "combat",
            "rounds": rounds,
            "hostiles_spawned": spawned,
            "hostiles_cleared": cleared,
            "colonist_casualties": casualties,
            "ticks": ticks,
            "verdict": verdict,
        },
        "privacy": {"classification": "internal", "redactions": []},
    }


def run_combat(dispatcher, game, ledger, pack: dict, *,
               iterations: int = 60, sink=None, clock=None,
               speed: int | None = None,
               mode_state_dir: Path | None = None) -> dict:
    """Execute the pack's combat script. `pack` is the full pack dict.

    Prereq: start.completed persisted in startmode.json beside the ledger
    (or combat.prereq == 'none' for tests)."""
    cfg = pack.get("combat") or {}
    state_path = (mode_state_dir
                  or Path(getattr(ledger, "_path", "tasks.jsonl")).parent) \
        / "startmode.json"
    if cfg.get("prereq", "start_completed") == "start_completed" \
            and not cfg.get("skip_prereq"):
        completed = False
        try:
            completed = bool(json.loads(
                state_path.read_text()).get("completed"))
        except (OSError, json.JSONDecodeError):
            pass
        if not completed:
            return {"ok": False,
                    "error": {"code": "combat.prereq",
                              "message": "start.completed not reached"}}

    prev = None
    if speed is not None:
        st = game.rpc("game.status")
        prev = st.get("result") if st.get("ok") else None
        game.rpc("game.speed", {"speed": speed})

    rounds = int(cfg.get("rounds", 1))
    engage = cfg.get("engage") or {}
    decisions: list = []
    state_dir = Path(getattr(ledger, "_path", "tasks.jsonl")).parent
    budget = int(engage.get("tick_budget", 12000))
    spawn_grace = int(engage.get("spawn_grace_ticks", 3000))
    uni_rules = ((pack.get("universal") or {}).get("rules") or []) \
        if engage.get("universal_rules", True) else []
    engage_rules = engage.get("rules") or []
    uni_state: dict = {}
    seq = getattr(dispatcher, "_events", 0)
    wire_sink(dispatcher, sink)
    out = {"ok": True, "rounds": [], "spawned": 0, "cleared": 0,
           "casualties": 0, "ticks": 0}
    cursor = [0]  # decisions.jsonl flush position across the whole run

    def _flush(obs, poll=0):
        views.write_views(
            state_dir,
            views.combat_snapshot(pack, obs, out["rounds"], poll),
            decisions[cursor[0]:])
        cursor[0] = len(decisions)

    try:
        obs = observe(game)
        ctx = policy.Ctx(cfg=pack, obs=obs, game=game, state=uni_state,
                         tick=obs.get("tick") or 0, poll=0,
                         decisions=decisions)
        policy.run_steps(cfg.get("setup"), dispatcher, ctx,
                         source="combat:setup")
        _flush(obs)
        for rnd in range(rounds):
            obs = observe(game)
            base = _colonist_ids(obs)
            ctx = policy.Ctx(cfg=pack, obs=obs, game=game,
                             state=uni_state, vars={"round": rnd},
                             tick=obs.get("tick") or 0, poll=0,
                             decisions=decisions)
            policy.run_steps(cfg.get("spawn"), dispatcher, ctx,
                             source=f"combat:spawn:r{rnd}")
            _flush(obs)
            round_start = obs.get("tick") or 0
            spawned_round = cleared_round = 0
            verdict = "failed"
            for i in range(iterations):
                obs = observe(game)
                tick = obs.get("tick") or 0
                ctx = policy.Ctx(cfg=pack, obs=obs, game=game,
                                 state=uni_state, vars={"round": rnd},
                                 tick=tick, poll=i,
                                 decisions=decisions)
                # hostile spawns auto-pause the game (raid letters) —
                # re-assert speed periodically or the round stalls paused
                if speed is not None and engage.get("speed_reassert",
                                                    True) \
                        and i % 10 == 0:
                    st = game.rpc("game.status")
                    res = st.get("result") if st.get("ok") else {}
                    if res.get("paused"):
                        game.rpc("game.speed", {"speed": speed})
                hostiles = _hostiles(game)
                if not spawned_round:
                    spawned_round = len(hostiles)
                # engage.until — pack predicate (e.g. living hostiles gone)
                if spawned_round and engage.get("until") \
                        and policy.check(engage["until"], ctx):
                    verdict = "cleared"
                    cleared_round = spawned_round
                    break
                if not spawned_round and tick - round_start > spawn_grace:
                    verdict = "no-spawn"
                    break
                if tick - round_start > budget:
                    break
                policy.run_rules(uni_rules + engage_rules, dispatcher,
                                 ctx, source="combat")
                _flush(obs, i)
                if callable(getattr(game, "advance", None)):
                    game.advance(i)
            after = _colonist_ids(observe(game))
            casualties = max(0, len(set(base) - set(after)))
            out["casualties"] += casualties
            out["spawned"] += spawned_round
            out["cleared"] += cleared_round
            out["rounds"].append({"round": rnd, "verdict": verdict,
                                  "hostiles": spawned_round,
                                  "casualties": casualties})
            obs = observe(game)
            ctx = policy.Ctx(cfg=pack, obs=obs, game=game,
                             state=uni_state, vars={"round": rnd},
                             tick=obs.get("tick") or 0, poll=0,
                             decisions=decisions)
            policy.run_steps(cfg.get("cleanup"), dispatcher, ctx,
                             source=f"combat:cleanup:r{rnd}")
            _flush(ctx.obs)
            out["ticks"] += (ctx.obs.get("tick") or round_start) \
                - round_start
            _wait_playing(game)
        verdict_all = ("cleared" if all(r["verdict"] == "cleared"
                                        for r in out["rounds"])
                       else "failed")
        env = completed_event(rounds, out["spawned"], out["cleared"],
                              out["casualties"], out["ticks"], verdict_all,
                              seq + 1, clock)
        emit = sink or getattr(dispatcher, "_sink", None)
        if emit is not None:
            emit(env)
        out["verdict"] = verdict_all
        out["event"] = env
        return out
    finally:
        if prev is not None:
            game.rpc("game.speed", {"speed": prev.get("speed", 0)})
            game.rpc("game.pause",
                     {"paused": bool(prev.get("paused", True))})
