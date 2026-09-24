"""Unified run loop (feature 017; FR-1401/1422).

One poll: observe -> brain-reset -> vitals -> reconcile -> reflex ->
pack rules -> decide (select stage) -> phase step -> views -> reflect.
``--mode run --game sim`` is deterministic (SimGame + fixed clock, zero
endpoint calls — SC-303 bit-identity); ``--game live`` needs ``--live``.

CLI: ``python -m runtime loop --pack start-mode-v0 --mode run --game sim``
"""

from __future__ import annotations

import argparse
import json
import sys

from . import simgame as _simgame
from .bridgeclient import BridgeClient
from .dispatch import Dispatcher

SOURCE = "rimbrainagent.runtime.loop"


def _fixed_clock() -> str:
    return "2026-01-01T00:00:00Z"


class _Clock:
    """Deterministic wall-time for sim runs (SC-303 bit-identity)."""

    def __call__(self) -> str:
        return _fixed_clock()


def run(dispatcher: Dispatcher, game, ledger, pack: dict, *,
        iterations: int = 12, sink=None, clock=None,
        speed: int | None = None, live_brain: bool = False,
        live_mutate: bool = False, mutate_resolver=None,
        mutate_chat=None, stop_on_complete: bool = False,
        scripted: bool = False, stage: str | None = None,
        select_caller: bool = False) -> dict:
    """The unified phase run (feature 017; FR-1401). One loop for the
    whole colony lifecycle: observe -> brain-reset -> vitals ->
    reconcile -> reflex -> pack rules -> phase step -> views -> reflect.

    Replaces the mode matrix: pack ``phases`` drive the engine, pack
    ``standing_goals`` are the held state (the former ``hold`` govern
    path — now unconditional). ``stop_on_complete`` bounds the run at
    the prescriptive phase's completion for stage-scoped harness runs
    (the former ``hold=False`` path). `live_mutate` enables the 016
    reflection pass over the run's own event stream.
    """
    from . import brain, observe, policy, select as _select, \
        templates, views, vitals
    from .phase import PhaseEngine
    from .runstate import RunState
    from .dispatch import wire_sink

    state_dir = ledger._path.parent
    rs_path = state_dir / "runstate.json"
    rs = RunState.load(rs_path)
    if not rs.vars and not rs.completed \
            and (state_dir / "startmode.json").is_file():
        rs = RunState.load(state_dir / "startmode.json")  # legacy mode file
    decisions: list = []
    engine = PhaseEngine(pack, ledger, runstate=rs, sink=sink,
                         clock=clock, scripted=scripted, only=stage)
    engine.decisions = decisions
    outcomes = []
    wire_sink(dispatcher, sink)
    if sink is not None:
        ledger._sink = getattr(dispatcher, "_sink", sink)
    # FR-1401/1411: the mutation pass watches the run's own event stream —
    # wrap the composed sink so every envelope (dispatch + ledger +
    # engine) lands in PassState before onward emission.
    mut = None
    if live_mutate and (pack.get("mutate") or {}):
        from . import evolve as _mut
        # T038: the reflection pass state lives under RunState ownership —
        # a brain reset clears improve_state -> a fresh PassState
        mut = rs.improve_state.get("evolve")
        if mut is None:
            mut = rs.improve_state["evolve"] = _mut.PassState(
                pack["mutate"])
        _prev_emit = getattr(dispatcher, "_sink", None) or sink

        def _msink(env, _prev=_prev_emit, _ps=mut):
            _ps.note(env)
            if _prev is not None:
                _prev(env)

        dispatcher._sink = _msink
        ledger._sink = _msink
        sink = _msink
    seq = max(ledger._events, getattr(dispatcher, "_events", 0))
    # tap emitted event types — the plan stage's `on_events` trigger
    # consumes each poll's stream (drained before every decide)
    emitted_types: list = []
    _orig_emit = dispatcher._emit

    def _tapped_emit(t, p):
        emitted_types.append(t)
        return _orig_emit(t, p)

    dispatcher._emit = _tapped_emit
    vitals_every = int((pack.get("vitals") or {}).get("every") or 50)
    senses = (pack.get("senses") or pack.get("start") or {})
    prev_speed = None
    if speed is not None:
        st = game.rpc("game.status")
        prev_speed = st.get("result") if st.get("ok") else None
        game.rpc("game.speed", {"speed": speed})
    try:
        for i in range(iterations):
            # pause-on-load / event letters can re-pause mid-run —
            # re-assert speed periodically so construction advances
            if speed is not None and i % 10 == 0:
                st = game.rpc("game.status")
                res = st.get("result") if st.get("ok") else {}
                if res.get("paused"):
                    game.rpc("game.speed", {"speed": speed})
            obs = observe.observe(game, senses)
            tick = obs.get("tick") or i
            dispatcher._last_tick = tick  # evidence carries the live tick
            prev = len(decisions)
            # FR-1107/FR-1309: brain request — {} refreshes the active
            # pack, {pack: id} swaps, {unload: true} halts the brain.
            # Every path does a full reinit (UR-BRN-020): ledger pack
            # namespaces tombstoned, runstate dropped, goals re-derive
            # from the colony as-observed. Honored only under
            # --live-brain; scored runs never set the flag.
            req = brain.poll_request(state_dir, live_brain)
            if req is not None:
                err = None
                dropped = 0
                want_unload = bool(req.get("unload"))
                target = req.get("pack") or dispatcher._pack_file
                if want_unload:
                    dispatcher._pack = None  # every write -> no_pack
                elif target:
                    try:
                        pack = dispatcher.load_pack(target)["pack"]
                    except Exception as e:  # PackError — fail-closed
                        err = f"{type(e).__name__}: {e}"
                else:
                    err = "no pack to load"
                if err is None:
                    rs_path.unlink(missing_ok=True)
                    (state_dir / "startmode.json") \
                        .unlink(missing_ok=True)
                    dropped = ledger.reset_ns(
                        "start.", "govern.", "phase.", "combat.",
                        tick=tick)
                    rs.reset()
                    engine = None if want_unload else PhaseEngine(
                        pack, ledger, runstate=rs, sink=sink,
                        clock=clock, scripted=scripted, only=stage)
                    if engine is not None:
                        engine.decisions = decisions
                    # FR-1402: a swapped pack carries its own mutate:
                    # policy — rebuild the pass state (or drop it).
                    if live_mutate and not want_unload:
                        rs.improve_state.pop("evolve", None)
                        mut = (_mut.PassState(pack["mutate"])
                               if pack.get("mutate") else None)
                        if mut is not None:
                            rs.improve_state["evolve"] = mut
                        if mut is not None:
                            _prev_emit = getattr(
                                dispatcher, "_sink", None)

                            def _msink2(env, _prev=_prev_emit,
                                        _ps=mut):
                                _ps.note(env)
                                if _prev is not None:
                                    _prev(env)

                            dispatcher._sink = _msink2
                            ledger._sink = _msink2
                    elif want_unload:
                        mut = None
                status = {"ok": err is None,
                          "pack_id": dispatcher._pack_file,
                          "pack_revision": (dispatcher._pack or {})
                          .get("hash"),
                          "state": ("unloaded"
                                    if want_unload and err is None
                                    else "loaded"),
                          "dropped_tasks": dropped, "error": err}
                brain.write_status(state_dir, **status)
                decisions.append({
                    "tick": tick, "poll": i, "source": "ui:brain-reset",
                    "template": "brain-reset", "params": {},
                    "ok": err is None, "error": err})
                dispatcher._emit("brain.reset", dict(status))
            # FR-811: periodic colony-health vitals -> canonical events
            # so the improve loop can diagnose defects.
            if vitals_every and i % vitals_every == 0:
                v, evs = vitals.sample(game, rs.vitals_state,
                                       pack.get("vitals") or {})
                obs["vitals"] = v
                dispatcher._emit("colony.vitals", v)
                for e in evs:
                    dispatcher._emit(e["type"], e["payload"])
            reconcile = ledger.reconcile(obs, tick)
            dispatcher.reflex(obs)
            if engine is None:  # brain unloaded — observe only; no writes
                out = {"phase": "brain", "state": "unloaded"}
            else:
                # pack-declared standing rules run every poll, after
                # reflexes — v1 `rules` surface (ex-universal.rules)
                rule_ctx = policy.Ctx(
                    cfg=pack, obs=obs, game=game,
                    state=rs.rule_state, persist=rs.vars,
                    tick=tick, poll=i, decisions=decisions)
                policy.run_rules(
                    templates.rules_of(pack),
                    dispatcher, rule_ctx, source="rule")
                # FR-1407..1410: the decide stage compiles the bounded
                # action list and owns goal drive when configured;
                # prescriptive phases never see it (init structural
                # steps stay deterministic). Scripted harness phases
                # (combat) bypass the endpoint entirely.
                select_out = None
                if not scripted:
                    from . import planstage
                    # FR-1411: cadence/boundary/event triggers; the
                    # in-force plan reorders this poll's action list.
                    # caller wired only for live runs (T025: sim never
                    # resolves an endpoint — pack fallback decides).
                    plan = planstage.tick(
                        dispatcher, pack, engine, ledger, obs,
                        tick=tick, poll=i, state_dir=state_dir,
                        caller=planstage._default_caller
                        if select_caller else None,
                        emit=lambda e: dispatcher._emit(
                            e["event_type"], e["payload"]),
                        events=emitted_types)
                    del emitted_types[:]
                    select_out = _select.decide(
                        dispatcher, pack, engine, rule_ctx, obs,
                        tick=tick, poll=i, state_dir=state_dir,
                        plan=plan,
                        caller=_select._default_caller
                        if select_caller else None,
                        emit=lambda e: dispatcher._emit(
                            e["event_type"], e["payload"]))
                out = engine.step(dispatcher, game, obs, tick, poll=i,
                                  select_out=select_out)
            outcomes.append({"iteration": i, "reconcile": reconcile,
                             **out})
            # FR-1401: reflection pass — failure/near-failure/cadence
            # triggers over the run's own event stream; never raises.
            if mut is not None:
                mut.note_outcome(out)
                mut.note_decisions(decisions)
                try:
                    _mut.maybe_trigger(
                        mut, dispatcher=dispatcher, ledger=ledger,
                        pack_loaded=dispatcher._pack
                        or {"pack": pack, "hash": ""},
                        pack=pack, pack_id=dispatcher._pack_file,
                        state_dir=state_dir, tick=tick, poll=i,
                        fair=getattr(dispatcher, "_fair", True),
                        emit=dispatcher._sink or (lambda e: None),
                        clock=clock,
                        resolver=mutate_resolver, chat=mutate_chat)
                except Exception as exc:
                    dispatcher._emit("system.error", {
                        "text": f"evolve.maybe_trigger: {exc}"[:200]})
            views.write_views(
                state_dir,
                views.phase_snapshot(
                    engine, ledger, obs,
                    events_path=state_dir / "events.jsonl",
                    mutate_view=(mut.view() if mut is not None
                                 else None))
                if engine is not None else {"mode": "run",
                                            "phase": "brain",
                                            "state": "unloaded",
                                            "tick": obs.get("tick"),
                                            "poll": i, "goals": [],
                                            "exit_conditions": {},
                                            "complete": False},
                decisions[prev:])
            if out.get("first"):
                seq += 1
                env = engine.completed_event(
                    obs, out["eval"], phase_id=out.get("phase_id",
                                                     "init"))
                env["sequence"] = seq
                env["event_id"] = f"evt.start-{seq:06d}"
                emit = sink or getattr(dispatcher, "_sink", None)
                if emit is not None:
                    emit(env)
            rs.save(rs_path)
            # completion is a handoff, not an exit — standing goals keep
            # working the colony unless the caller bounds at the stage
            if out.get("state") == "completed" and stop_on_complete:
                break
            if callable(getattr(game, "advance", None)):
                game.advance(i)
    finally:
        dispatcher._emit = _orig_emit
        if prev_speed is not None:
            game.rpc("game.speed",
                     {"speed": prev_speed.get("speed", 0)})
            game.rpc("game.pause",
                     {"paused": bool(prev_speed.get("paused", True))})
        rs.save(rs_path)
    return {"ok": True, "outcomes": outcomes,
            "completed": rs.completed,
            "site": rs.vars.get("site")}


def _dev_off(game):
    """--fair: hide the in-game dev UI for the run (UR-CTL-009). Returns
    prior {dev_mode, god_mode} so the caller can restore on exit."""
    prev = {}
    try:
        st = game.rpc("game.status")
        res = st.get("result") if st.get("ok") else {}
        prev = {"dev_mode": res.get("dev_mode", True),
                "god_mode": res.get("god_mode", False)}
        game.rpc("game.dev_mode", {"enabled": False, "god": False})
    except Exception:
        pass
    return prev


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="runtime.loop", description=__doc__)
    p.add_argument("--pack", default="core-survival-v0")
    p.add_argument("--mode", choices=["run", "cycle", "improve",
                                      # deprecated aliases (FR-1422)
                                      "sim", "live", "start", "combat"],
                   default="run")
    p.add_argument("--game", choices=["sim", "live"], default="sim",
                   help="world backend — sim is deterministic and never "
                        "touches the bridge; live needs --live")
    p.add_argument("--stage", default=None,
                   help="drive only the named phase/stage (debug entry; "
                        "'combat' runs the scripted phase and needs --dev)")
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--bridge", default="http://127.0.0.1:8765")
    p.add_argument("--live", "--live-flag", action="store_true",
                   help="confirm live mode (operator smoke only)")
    p.add_argument("--no-store", action="store_true",
                   help="do not persist events to state/events.jsonl")
    p.add_argument("--ledger", action="store_true",
                   help="reconcile the task ledger before attend each poll")
    p.add_argument("--feed", action="store_true",
                   help="narrate every emitted event into state/feed.md")
    p.add_argument("--fair", dest="fair", action="store_true", default=True,
                   help="fair run (default): refuse dev.* and save/load "
                        "dispatches (no debug cheating, UR-CTL-009)")
    p.add_argument("--dev", dest="fair", action="store_false",
                   help="development testing only: allow dev.* methods, "
                        "save/load dispatches, and dev-class packs")
    p.add_argument("--live-brain", action="store_true",
                   help="honor brain-reset requests: reload the pack + "
                        "re-plan mid-run (FR-1107; never for scored runs)")
    p.add_argument("--live-mutate", action="store_true",
                   help="live pack mutation: failure/near-failure/cadence "
                        "triggers run a rimbrain.improve reflection pass; "
                        "candidates promote at the next run boundary "
                        "(feature 016; never for scored runs)")
    p.add_argument("--no-hold", action="store_true",
                   help="run: stop at init completion instead of "
                        "holding under the pack's standing goals")
    args = p.parse_args(argv)
    # deprecated mode aliases -> the FR-1422 surface
    alias = {"start": ("run", "live", None),
             "combat": ("run", "live", "combat"),
             "sim": ("run", "sim", None),
             "live": ("run", "live", None)}
    if args.mode in alias:
        mode, game, stage = alias[args.mode]
        print(f"warning: --mode {args.mode} is deprecated; use "
              f"--mode {mode} --game {game}"
              + (f" --stage {stage}" if stage else ""),
              file=sys.stderr)
        args.mode, args.game = mode, game
        args.stage = args.stage or stage
    if args.mode == "run" and args.game == "live" \
            and args.pack == "core-survival-v0":
        args.pack = "start-mode-v0"  # the colony pack
    if args.mode == "cycle" and args.pack == "core-survival-v0":
        args.pack = "start-mode-v0"
    if args.mode == "improve" and args.pack == "core-survival-v0":
        args.pack = "improve-v0"  # the mode's own module

    if (args.game == "live" or args.mode == "cycle") \
            and args.mode != "improve" and not args.live:
        print(json.dumps({"ok": False, "error": {
            "code": "loop.live_requires_confirmation",
            "message": "--game live / --mode cycle needs --live "
                       "(operator smoke only)",
            "retryable": False}}))
        return 2
    if args.mode == "cycle" and args.fair:
        print(json.dumps({"ok": False, "error": {
            "code": "loop.cycle_requires_dev",
            "message": "cycle mode is a checkpoint save/load test harness; "
                       "run with --dev (development testing only)",
            "retryable": False}}))
        return 2
    if args.stage == "combat" and args.fair:
        print(json.dumps({"ok": False, "error": {
            "code": "loop.stage_requires_dev",
            "message": "--stage combat executes dev.* spawn/save/load "
                       "tooling; run with --dev (development only)",
            "retryable": False}}))
        return 2
    if args.live_mutate and not (args.mode == "run"
                                 and args.game == "live"):
        print(json.dumps({"ok": False, "error": {
            "code": "loop.live_mutate_requires_live",
            "message": "--live-mutate only applies to "
                       "--mode run --game live (which also needs --live)",
            "retryable": False}}))
        return 2

    store = None
    if not args.no_store or args.mode in ("improve", "cycle"):
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
    dev_prev: dict = {}
    try:
        if args.mode == "improve":
            # read-only over canonical evidence — no game, no writes
            from .evolve import run_improve
            dispatcher = Dispatcher(None, fair=args.fair)
            dispatcher.load_pack(args.pack)
            cfg = (dispatcher.pack["pack"].get("improve") or {})
            result = run_improve(
                store, cfg, active_pack=dispatcher.pack["pack"],
                iterations=args.iterations, sink=sink, feed=feed)
        elif args.mode == "cycle":
            game = BridgeClient(args.bridge)
            dispatcher = Dispatcher(game, fair=args.fair)
            dispatcher.load_pack(args.pack)
            from .cycle import run_cycle
            result = run_cycle(
                dispatcher, game, dispatcher.pack["pack"], store,
                iterations=args.iterations, sink=sink, speed=3)
        else:
            # --mode run: the unified phase loop (FR-1401/1422). sim is
            # SimGame + fixed clock (bit-identical streams, zero endpoint
            # calls); live is BridgeClient + operator-confirmed --live.
            clock = _Clock() if args.game == "sim" else None
            game = _simgame.SimGame() if args.game == "sim" \
                else BridgeClient(args.bridge)
            if args.fair and args.game == "live":
                dev_prev = _dev_off(game)
            dispatcher = Dispatcher(
                game, game_tick=0 if args.game == "sim" else None,
                clock=clock, fair=args.fair)
            if args.live_mutate:
                # feature 016 boundary: revert a regressed promotion, then
                # install a pending candidate — before load_pack, so the
                # run always starts on a validated, immutable pack file.
                from .evolve import boundary as _mut_boundary
                from .store import state_dir as _state_dir
                _mut_boundary(args.pack, _state_dir(), emit=sink,
                              fair=args.fair)
            dispatcher.load_pack(args.pack)
            from .tasks import TaskLedger
            ledger = ledger or TaskLedger()
            if args.stage in ("plan", "reflect"):
                # debug entries (FR-1422): one stage round over the
                # observed state — no phase loop
                from . import observe as _obs, planstage
                from .runstate import RunState
                from .phase import PhaseEngine
                state_dir = ledger._path.parent
                rs = RunState.load(state_dir / "runstate.json")
                engine = PhaseEngine(
                    dispatcher.pack["pack"], ledger, runstate=rs,
                    sink=sink, clock=clock)
                obs = _obs.observe(game, senses=(
                    dispatcher.pack["pack"].get("senses")
                    or dispatcher.pack["pack"].get("start") or {}))
                if args.stage == "plan":
                    result = {"stage": "plan", "plan": planstage.tick(
                        dispatcher, dispatcher.pack["pack"], engine,
                        ledger, obs, tick=obs.get("tick") or 0, poll=0,
                        state_dir=state_dir,
                        caller=planstage._default_caller
                        if args.game == "live" else None,
                        emit=lambda e: dispatcher._emit(
                            e["event_type"], e["payload"]),
                        force=True)}
                else:
                    from . import evolve as _mut
                    pcfg = dispatcher.pack["pack"].get("mutate") or {}
                    ps = _mut.PassState(pcfg)
                    result = {"stage": "reflect",
                              "reflect": _mut.maybe_trigger(
                                  ps, dispatcher=dispatcher,
                                  ledger=ledger,
                                  pack_loaded=dispatcher.pack
                                  or {"pack": dispatcher.pack["pack"],
                                      "hash": ""},
                                  pack=dispatcher.pack["pack"],
                                  pack_id=args.pack,
                                  state_dir=state_dir,
                                  tick=obs.get("tick") or 0, poll=0,
                                  fair=args.fair,
                                  emit=sink or (lambda e: None),
                                  clock=clock, force=True)}
                print(json.dumps({"ok": True, **result}, default=str))
                return 0
            result = run(
                dispatcher, game, ledger, dispatcher.pack["pack"],
                iterations=args.iterations,
                sink=sink, clock=clock,
                speed=3 if args.game == "live" else None,
                live_brain=args.live_brain,
                live_mutate=args.live_mutate,
                stop_on_complete=args.no_hold,
                scripted=args.stage == "combat",
                stage=args.stage,
                select_caller=args.game == "live")
        print(json.dumps({"ok": True, **result}, default=str))
        return 0
    except Exception as exc:  # fail closed at the boundary
        print(json.dumps({"ok": False, "error": {
            "code": "loop.crashed", "message": str(exc),
            "retryable": False}}))
        return 1
    finally:
        if dev_prev:  # restore the player's dev-mode preference
            try:
                BridgeClient(args.bridge).rpc("game.dev_mode", {
                    "enabled": dev_prev.get("dev_mode", True),
                    "god": dev_prev.get("god_mode", False)})
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
