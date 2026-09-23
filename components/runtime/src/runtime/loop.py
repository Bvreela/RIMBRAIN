"""Dispatcher poll loop (feature 004; FR-308/309, T087).

Per poll: ``game.status`` -> emergency reflex (before any model call) -> if no
reflex fired, a select-tier decision (systemone) -> ``dispatch_from_decision``.
Deterministic in ``--mode sim`` (SimGame + fixed clock + scripted decider) so
five consecutive runs are bit-identical (SC-303); ``--mode live`` requires an
explicit ``--live`` flag (operator smoke only).

CLI: ``python -m runtime loop --pack core-survival-v0 --mode sim --iterations 5``
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import client as _client
from . import simgame as _simgame
from .bindings import resolve_role
from .bridgeclient import BridgeClient
from .dispatch import Dispatcher

SOURCE = "rimbrainagent.runtime.loop"


def _fixed_clock() -> str:
    return "2026-01-01T00:00:00Z"


class _Clock:
    """Deterministic wall-time for sim runs (SC-303 bit-identity)."""

    def __call__(self) -> str:
        return _fixed_clock()


def _sim_decider(state: dict, iteration: int) -> dict:
    """Scripted deterministic select answers: iterate a 4-choice cycle."""
    choices = ["haul", "forbid", "none", "haul"]
    choice = choices[iteration % len(choices)]
    return {"choice": choice, "score": 0.5, "noul": 0.3,
            "thing": "silver-1", "state": state.get("state", "playing")}


def _live_decider(question: str = "q.action") -> dict:
    """Systemone select via the runtime client (Laya primary, degraded paths)."""
    res = resolve_role("rimbrain.select", probe_live=True)
    if not res.get("ok"):
        return {"choice": "none", "error": res["error"]["code"]}
    endpoint_id = res["resolved"]["endpoint_id"]
    model = res["resolved"]["model"]
    questions = {question: {"type": "choice",
                            "instructions": "pick the best survival action",
                            "criteria": {"forbid": "forbid item",
                                         "haul": "haul to stockpile",
                                         "rescue": "rescue downed colonist",
                                         "firefight": "fight fire",
                                         "none": "no action"}}}
    r = _client.systemone_decide(endpoint_id, state="survival-poll",
                                 questions=questions, model=model)
    if not r.get("ok"):
        return {"choice": "none", "error": r["error"]["code"]}
    body = r.get("body") or {}
    answers = body.get("answers") or {}
    entry = answers.get(question) or {}
    return dict(entry)


def run_loop(dispatcher: Dispatcher, game, *, iterations: int = 5,
             decider=None, clock=None, sink=None, ledger=None) -> dict:
    """Run ``iterations`` polls; returns ``{ok, events, actions, outcomes}``.

    ``decider(state, iteration) -> answer dict`` (sim default); ``clock()``
    supplies envelope wall-times (fixed clock default for determinism);
    ``ledger`` (optional TaskLedger) is reconciled before attend each poll.
    """
    events: list[dict] = []
    outcomes: list[dict] = []

    def _sink(env: dict) -> None:
        events.append(env)
        if sink is not None:
            sink(env)

    dispatcher._sink = _sink
    if ledger is not None:
        ledger._sink = _sink  # task transitions join the run event stream
    tick = 0
    for i in range(iterations):
        status = game.rpc("game.status")
        state = status.get("result") or {}
        if not isinstance(state, dict):
            state = {}
        if status.get("ok"):
            from .planloop import enrich
            state = enrich(game, dict(state))
        if not status.get("ok"):
            outcomes.append({"iteration": i, "kind": "status_failed",
                             "error": status.get("error", {}).get("code")})
            break
        if isinstance(state.get("tick"), int):
            tick = state["tick"]
        if ledger is not None:
            # spine: reconcile precedes attend (UR-RUN-001/003)
            outcomes.append({"iteration": i, "kind": "reconcile",
                             "result": ledger.reconcile(state, tick)})
        reflex = dispatcher.reflex(state)
        if reflex:
            outcomes.append({"iteration": i, "kind": "reflex",
                             "actions": len(reflex)})
            if callable(getattr(game, "advance", None)):
                game.advance(i)
            continue
        answer = (decider or _sim_decider)(state, i)
        res = dispatcher.dispatch_from_decision(answer, state,
                                                decision_id=f"dec.sim-{i:03d}")
        outcomes.append({"iteration": i, "kind": "decision",
                         "choice": answer.get("choice"),
                         "ok": bool(res.get("ok")),
                         "error": res.get("error", {}).get("code")})
        if callable(getattr(game, "advance", None)):
            game.advance(i)
    return {"ok": True, "events": events, "actions": len(events),
            "outcomes": outcomes, "tick": tick}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="runtime.loop", description=__doc__)
    p.add_argument("--pack", default="core-survival-v0")
    p.add_argument("--mode", choices=["sim", "live", "start", "improve"],
                   default="sim")
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--bridge", default="http://127.0.0.1:8765")
    p.add_argument("--live", action="store_true",
                   help="confirm live mode (operator smoke only)")
    p.add_argument("--no-store", action="store_true",
                   help="do not persist events to state/events.jsonl")
    p.add_argument("--ledger", action="store_true",
                   help="reconcile the task ledger before attend each poll")
    p.add_argument("--feed", action="store_true",
                   help="narrate every emitted event into state/feed.md")
    args = p.parse_args(argv)
    if args.mode == "start" and args.pack == "core-survival-v0":
        args.pack = "start-mode-v0"  # the mode's own module
    if args.mode == "improve" and args.pack == "core-survival-v0":
        args.pack = "improve-v0"  # the mode's own module

    if args.mode in ("live", "start") and not args.live:
        print(json.dumps({"ok": False, "error": {
            "code": "loop.live_requires_confirmation",
            "message": f"--mode {args.mode} needs --live (operator smoke only)",
            "retryable": False}}))
        return 2

    store = None
    if not args.no_store or args.mode == "improve":
        from .store import EventStore
        store = EventStore()
    feed = None
    if args.feed:
        from .feed import FeedWriter
        from .store import state_dir
        feed = FeedWriter(state_dir() / "feed.md")

    def emit(env):
        if store is not None:
            store.append(env)
        if feed is not None:
            feed.write(env)
    sink = emit if (store is not None or feed is not None) else None

    ledger = None
    if args.ledger:
        from .tasks import TaskLedger
        ledger = TaskLedger()
    try:
        if args.mode == "sim":
            # the dispatcher's writer target IS the SimGame (single writer must
            # never silently point at the real bridge during a sim run)
            game = _simgame.SimGame()
            dispatcher = Dispatcher(game, game_tick=0, clock=_Clock())
            dispatcher.load_pack(args.pack)
            result = run_loop(dispatcher, game, iterations=args.iterations,
                              ledger=ledger,
                              sink=sink)
        elif args.mode == "start":
            game = BridgeClient(args.bridge)
            dispatcher = Dispatcher(game)
            dispatcher.load_pack(args.pack)
            from .startmode import run_start
            from .tasks import TaskLedger
            ledger = ledger or TaskLedger()
            cfg = (dispatcher.pack["pack"].get("start") or {})
            result = run_start(
                dispatcher, game, ledger, cfg,
                iterations=args.iterations,
                sink=sink)
        elif args.mode == "improve":
            # read-only over canonical evidence — no game, no writes
            from .improve import run_improve
            dispatcher = Dispatcher(None)
            dispatcher.load_pack(args.pack)
            cfg = (dispatcher.pack["pack"].get("improve") or {})
            result = run_improve(
                store, cfg, active_pack=dispatcher.pack["pack"],
                iterations=args.iterations, sink=sink, feed=feed)
        else:
            game = BridgeClient(args.bridge)
            dispatcher = Dispatcher(game)
            dispatcher.load_pack(args.pack)
            result = run_loop(dispatcher, game, iterations=args.iterations,
                              decider=lambda s, i: _live_decider(),
                              ledger=ledger,
                              sink=sink)
        print(json.dumps({"ok": True, **result}, default=str))
        return 0
    except Exception as exc:  # fail closed at the boundary
        print(json.dumps({"ok": False, "error": {
            "code": "loop.crashed", "message": str(exc),
            "retryable": False}}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
