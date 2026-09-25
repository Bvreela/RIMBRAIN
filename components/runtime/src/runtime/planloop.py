"""Planner/review loop (feature 005; FR-403..409, T097).

One round: colony state -> ``planning.propose`` -> ``review.review`` ->
accepted proposals materialize candidate packs under ``packs/candidates/``
(FR-404) and optionally dispatch ``actions[]`` through the feature-004
single writer (FR-406). Canonical ``plan.*`` events carry model provenance
and token usage (FR-405). The loop refuses while a scored episode is active
(FR-409) and sim mode never touches the live bridge or real endpoints —
the chat call is injectable for deterministic offline runs (FR-407).

CLI: ``python -m runtime plan --mode sim [--pack core-survival-v0] [--iterations N]``
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import planning, review, templates
from .bindings import resolve_role
from .bridgeclient import BridgeClient
from .client import openai_compat_chat
from .dispatch import Dispatcher
from .simgame import SimGame
from .usage import UsageTracker

SOURCE = "rimbrainagent.runtime.planloop"
_ZERO_USAGE = {"prompt_tokens": 0, "completion_tokens": 0}


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Emitter:
    """Canonical plan.* envelopes mirroring the dispatcher's shape."""

    def __init__(self, clock=None, sink=None) -> None:
        self._clock = clock or _utcnow
        self._sink = sink
        self._seq = 0
        self.game_tick: int | None = None
        self.events: list[dict] = []

    def emit(self, event_type: str, payload: dict) -> dict:
        self._seq += 1
        env = {
            "schema_version": 0,
            "event_id": f"evt.plan-{self._seq:06d}",
            "sequence": self._seq,
            "event_type": event_type,
            "game_tick": self.game_tick,
            "wall_time_utc": self._clock(),
            "source": SOURCE,
            "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": payload,
            "privacy": {"classification": "internal", "redactions": []},
        }
        self.events.append(env)
        if self._sink is not None:
            self._sink(env)
        return env


def _err(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message, "retryable": False}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


def _materialize_candidate(pack_file: str, base_doc: dict,
                           mutations: list) -> dict:
    """Write the pack's inactive slot via the shared evolve
    pipeline — one candidate format, one gate (feature 017, T037)."""
    from . import evolve
    return evolve.materialize_candidate(pack_file, base_doc, mutations)


def enrich(game, state: dict) -> dict:
    """Merge richer observation into a status dict so pack predicates and the
    entity gate see real fields on ANY bridge shape (live `game.status`
    returns `colonists` as a bare count and no `map.fires`; `state.summary` +
    `map.find` carry the truth). Only fills missing keys — never overrides
    observed data.
    """
    summary = game.rpc("state.summary")
    if summary.get("ok") and isinstance(summary.get("result"), dict):
        s = summary["result"]
        if s.get("colonist_list"):
            state["colonist_list"] = s["colonist_list"]
        state["summary"] = {k: v for k, v in s.items()
                            if k != "colonist_list"}
        if not isinstance(state.get("colonists"), dict):
            state["colonists"] = {"count": state.get("colonists")}
        state["colonists"].setdefault("downed", s.get("downed"))
        state["colonists"].setdefault(
            "downed_id",
            next((m.get("id") or m.get("name")
                  for m in s.get("colonist_list") or []
                  if isinstance(m, dict) and m.get("downed")), None))
    roster = planning.colonist_roster(state)
    if roster and not state.get("first_colonist"):
        state["first_colonist"] = (roster[0].get("name")
                                   or roster[0].get("id"))
    fires = game.rpc("map.find", {"def": "Fire"})
    if fires.get("ok") and isinstance(fires.get("result"), dict):
        f = fires["result"]
        if not isinstance(state.get("map"), dict):
            state["map"] = {}
        state["map"].setdefault("fires", f.get("count", 0))
        things = f.get("things") or []
        first = things[0] if things else {}
        if isinstance(first, dict) and first.get("pos"):
            state["map"].setdefault("fire_cell", first["pos"])
    return state


def observe(game) -> dict:
    """Poll the colony into one state dict the planner/gate can rely on.

    ``game.status`` gives the coarse frame (tick/day/paused); ``enrich()``
    adds the real colonist roster, downed fields, and fire counts. The
    planner may only reference entities that appear here — never invented
    (AGENTS.md rule).
    """
    status = game.rpc("game.status")
    return enrich(game, dict(status.get("result") or {}))


def run_plan(state: dict, pack_id: str, *,
             dispatcher: Dispatcher | None = None,
             resolver=resolve_role, chat=openai_compat_chat,
             usage_tracker: UsageTracker | None = None,
             sink=None, clock=None, dispatch_actions: bool = True,
             scored_episode_active: bool = False) -> dict:
    """One plan/review/materialize/dispatch round; named-error envelope out."""
    em = _Emitter(clock=clock, sink=sink)
    pack_hash = ""
    try:
        pack_hash = templates.current_hash(pack_id) or ""
    except Exception:
        pass

    em.game_tick = state.get("tick") if isinstance(state.get("tick"), int) \
        else None

    def _reject(code: str, message: str, **kw) -> dict:
        payload = {"plan_id": kw.get("plan_id", ""),
                   "pack_revision": pack_hash,
                   "code": code, "message": message,
                   "violations": kw.get("violations", [])}
        for key in ("endpoint_id", "model"):
            if kw.get(key):
                payload[key] = kw[key]
        if kw.get("usage") is not None:
            payload["usage"] = kw["usage"]
        em.emit("plan.rejected", payload)
        return {"ok": False, "error": {"code": code, "message": message,
                                       "retryable": False},
                "events": em.events}

    if scored_episode_active:
        return _reject("plan.scored_episode_active",
                       "planner loop is forbidden while a scored episode "
                       "is active")
    try:
        loaded = templates.load_pack(pack_id)
    except templates.PackError as exc:
        e = exc.envelope["error"]
        return _reject(e["code"], e["message"])
    pack_hash = loaded["hash"]

    prop = planning.propose(state, loaded, resolver=resolver, chat=chat,
                            usage_tracker=usage_tracker)
    if not prop.get("ok"):
        e = prop["error"]
        return _reject(e["code"], e["message"])
    proposal = prop["proposal"]
    em.emit("plan.proposed", {
        "plan_id": proposal["plan_id"], "pack_revision": pack_hash,
        "endpoint_id": prop["endpoint_id"], "model": prop["model"],
        "degraded": prop["degraded"], "usage": prop["usage"],
        "proposal": proposal})

    # Review + dispatch act on state-resolved params ({state.*} placeholders
    # are resolved against the observed state; the proposed event keeps the
    # raw model output for audit).
    from .dispatch import substitute_params
    exec_proposal = copy.deepcopy(proposal)
    for action in exec_proposal.get("actions", []):
        action["params"] = substitute_params(
            action.get("params") or {}, state, None)

    verdict = review.review(exec_proposal, loaded, state=state,
                            resolver=resolver,
                            chat=chat, usage_tracker=usage_tracker)
    em.emit("plan.reviewed", {
        "plan_id": proposal["plan_id"], "pack_revision": pack_hash,
        "endpoint_id": prop["endpoint_id"], "model": prop["model"],
        "verdict": verdict["verdict"], "violations": verdict["violations"],
        "feedback": verdict["feedback"],
        "model_unavailable": verdict["model_unavailable"],
        "usage": verdict["usage"]})
    if verdict["verdict"] == "rejected":
        return _reject("plan.rejected",
                       "deterministic review gate rejected the proposal",
                       plan_id=proposal["plan_id"],
                       violations=verdict["violations"],
                       endpoint_id=prop["endpoint_id"],
                       model=prop["model"],
                       usage=prop["usage"])

    candidates: list[dict] = []
    if proposal.get("policy_mutations"):
        cand = _materialize_candidate(pack_id, loaded["pack"],
                                      proposal["policy_mutations"])
        if not cand.get("ok"):
            e = cand["error"]
            return _reject(e["code"], e["message"],
                           plan_id=proposal["plan_id"])
        candidates.append({"path": cand["path"], "hash": cand["hash"]})

    dispatched: list[dict] = []
    if dispatch_actions and dispatcher is not None:
        for action in exec_proposal.get("actions", []):
            res = dispatcher.dispatch(action["template_id"],
                                      action.get("params") or {},
                                      decision_id=proposal["plan_id"])
            entry = {"template_id": action["template_id"],
                     "outcome": "ok" if res.get("ok") else "failed"}
            if not res.get("ok"):
                entry["error_code"] = res["error"]["code"]
            dispatched.append(entry)

    em.emit("plan.accepted", {
        "plan_id": proposal["plan_id"], "pack_revision": pack_hash,
        "endpoint_id": prop["endpoint_id"], "model": prop["model"],
        "usage": prop["usage"],
        "dispatched": dispatched, "candidates": candidates})
    return {"ok": True, "plan_id": proposal["plan_id"],
            "verdict": verdict["verdict"], "degraded": prop["degraded"],
            "dispatched": dispatched, "candidates": candidates,
            "events": em.events}


# ---------------------------------------------------------------- CLI ------

_SIM_PLAN = {
    "schema_version": 0, "plan_id": "plan.sim-canned",
    "horizon_ticks": 60000,
    "actions": [
        {"template_id": "prioritize-work",
         "params": {"pawn": "Gomez",
                    "priorities": {"Firefight": 1, "Doctor": 2,
                                   "Growing": 2}}},
        {"template_id": "haul-designate",
         "params": {"designator": "haul", "cells": [[3, 3]]}},
    ],
    "policy_mutations": [],
    "rationale": "deterministic sim planner fixture",
}

_SIM_USAGE = {"prompt_tokens": 10, "completion_tokens": 40}


def _sim_chat(endpoint_id, model, messages, **kw) -> dict:
    """Deterministic canned planner/reviewer for sim mode (FR-407)."""
    joined = json.dumps(messages)
    if "rimbrain.review" in joined or "Critique the plan" in joined:
        content = "sim review: plan is consistent with the pack"
    else:
        content = json.dumps(_SIM_PLAN)
    return {"ok": True, "body": {
        "choices": [{"message": {"content": content}}],
        "usage": dict(_SIM_USAGE)}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="runtime.plan", description=__doc__)
    p.add_argument("--pack", default="core-survival-v0")
    p.add_argument("--mode", choices=["sim", "live"], default="sim")
    p.add_argument("--iterations", type=int, default=1)
    p.add_argument("--bridge", default="http://127.0.0.1:8765")
    p.add_argument("--no-dispatch", action="store_true",
                   help="review-only: skip dispatching plan actions")
    p.add_argument("--live", action="store_true",
                   help="confirm live mode (operator only)")
    p.add_argument("--fair", dest="fair", action="store_true", default=True,
                   help="fair run (default): refuse dev.* and save/load "
                        "dispatches (no debug cheating, UR-CTL-009)")
    p.add_argument("--dev", dest="fair", action="store_false",
                   help="development testing only: allow dev.* methods, "
                        "save/load dispatches, and dev-class packs")
    p.add_argument("--no-store", action="store_true",
                   help="do not persist events to state/events.jsonl")
    args = p.parse_args(argv)

    if args.mode == "live" and not args.live:
        print(json.dumps({"ok": False, "error": {
            "code": "plan.live_requires_confirmation",
            "message": "--mode live needs --live (operator only)",
            "retryable": False}}))
        return 2

    store = None
    if not args.no_store:
        from .store import EventStore
        store = EventStore()
    try:
        if args.mode == "sim":
            # sim: SimGame is BOTH the status source and the writer target;
            # chat is the canned fixture — no real bridge, no real endpoints
            game = SimGame()
            dispatcher = Dispatcher(game,
                                    clock=lambda: "2026-01-01T00:00:00Z",
                                    fair=args.fair,
                                    sink=None if store is None
                                    else store.append)
            dispatcher.load_pack(args.pack)
            chat, clock = _sim_chat, (lambda: "2026-01-01T00:00:00Z")
        else:
            game = BridgeClient(args.bridge)
            dispatcher = Dispatcher(game, fair=args.fair,
                                    sink=None if store is None
                                    else store.append)
            dispatcher.load_pack(args.pack)
            chat, clock = openai_compat_chat, None
        tracker = UsageTracker()
        results = []
        for _ in range(args.iterations):
            state = observe(game)
            results.append(run_plan(
                state, args.pack, dispatcher=dispatcher,
                chat=chat, clock=clock, usage_tracker=tracker,
                sink=None if store is None else store.append,
                dispatch_actions=not args.no_dispatch))
        print(json.dumps({"ok": all(r.get("ok") for r in results),
                          "usage": tracker.snapshot(),
                          "rounds": results}, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": {
            "code": "plan.crashed", "message": str(exc),
            "retryable": False}}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
