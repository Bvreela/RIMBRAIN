"""Deterministic in-memory game stub (feature 004; FR-309, T086).

Implements exactly the RPC surface the v0 templates use (game.status,
ui.set_work, ui.job, ui.designate) as a pure state machine: state changes only
through writes and ``advance(iteration)``, whose scripted evolution is a pure
function of (state, iteration). Five consecutive loop runs are therefore
bit-identical (SC-303). Envelope grammar matches the bridge
(``{ok, result|error}``).
"""

from __future__ import annotations

from copy import deepcopy

TEMPLATE_SURFACE = ("game.status", "state.summary", "state.pawns",
                    "ui.set_work", "ui.job", "ui.designate")


def err(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message,
                                   "retryable": False}}


def default_state() -> dict:
    return {
        "state": "playing",
        "tick": 0,
        "day": 0,
        "paused": False,
        "speed": 0,
        "first_colonist": "Gomez",
        "colonists": {
            "downed": 0,
            "downed_id": None,
            "members": [
                {"id": "c1", "name": "Gomez", "downed": False},
                {"id": "c2", "name": "Hicklin", "downed": False},
            ],
        },
        "map": {"fires": 0, "fire_cell": None},
        "haul_cell": [3, 3],
        "priorities": {},
        "jobs": [],
        "designations": [],
    }


class SimGame:
    """Deterministic fake; call ``rpc`` for the template surface."""

    def __init__(self, state: dict | None = None) -> None:
        self._state = deepcopy(state) if state else default_state()

    @property
    def current(self) -> dict:
        return deepcopy(self._state)

    def advance(self, iteration: int) -> None:
        """Scripted deterministic evolution (pure function of state+iteration).

        Iteration 0: clean. Iteration 1: fire starts. Iteration 2: a colonist
        goes down. Iteration 3: both clear again. Exercises the reflex paths.
        """
        self._state["tick"] += 25
        self._state["day"] = self._state["tick"] // 60000
        if iteration == 1:
            self._state["map"]["fires"] = 1
            self._state["map"]["fire_cell"] = [10, 10]
        elif iteration == 2:
            self._state["colonists"]["downed"] = 1
            self._state["colonists"]["downed_id"] = "c2"
            self._state["colonists"]["members"][1]["downed"] = True
        elif iteration == 3:
            self._state["map"]["fires"] = 0
            self._state["map"]["fire_cell"] = None
            self._state["colonists"]["downed"] = 0
            self._state["colonists"]["downed_id"] = None
            self._state["colonists"]["members"][1]["downed"] = False

    def _roster(self) -> list[dict]:
        return [{"id": m["id"], "name": m["name"], "kind": "Colonist",
                 "downed": m.get("downed", False)}
                for m in self._state["colonists"]["members"]]

    def rpc(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        if method == "game.status":
            return {"ok": True, "result": deepcopy(self._state)}
        if method == "state.pawns":
            return {"ok": True, "result": self._roster()}
        if method == "state.summary":
            return {"ok": True, "result": {
                "colonists": len(self._state["colonists"]["members"]),
                "downed": self._state["colonists"]["downed"],
                "colonist_list": self._roster(),
                "day": self._state["day"], "hour": self._state["tick"] // 2500}}
        if method == "ui.set_work":
            pawn, priorities = params.get("pawn"), params.get("priorities")
            if not isinstance(pawn, str) or not isinstance(priorities, dict):
                return err("sim.params_invalid",
                           "ui.set_work needs {pawn, priorities}")
            self._state["priorities"][pawn] = dict(priorities)
            return {"ok": True, "result": {"applied": True,
                                           "pawn": pawn,
                                           "priorities": dict(priorities)}}
        if method == "ui.job":
            pawn, job = params.get("pawn"), params.get("job")
            if not isinstance(pawn, str) or not isinstance(job, str):
                return err("sim.params_invalid", "ui.job needs {pawn, job}")
            record = {"pawn": pawn, "job": job, "target": params.get("target")}
            self._state["jobs"].append(record)
            return {"ok": True, "result": {"applied": True, "job": record}}
        if method == "ui.designate":
            designator = params.get("designator")
            if designator not in ("forbid", "unforbid", "haul"):
                return err("sim.params_invalid",
                           f"unsupported designator {designator!r}")
            entry = {"designator": designator,
                     "cells": params.get("cells"),
                     "things": params.get("things")}
            self._state["designations"].append(entry)
            return {"ok": True, "result": {"applied": True,
                                           "designation": entry}}
        return err("sim.unknown_method", f"method '{method}' not simulated")
