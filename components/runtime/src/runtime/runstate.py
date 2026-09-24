"""Per-run state owner (feature 017; FR-1427).

One holder for everything that used to be scattered: pack ``set:`` vars
(``mode.vars``), universal-rule state (``uni_state``), improvement pass
state, vitals hediff-diff state (``vstate``), and phase bookkeeping.
One persistence owner → ``state/runstate.json`` (replaces
``startmode.json``); the TaskLedger stays canonical for task lifecycles.

Brain lifecycle (load/unload/swap/reset) calls ``reset()`` then
``save()`` — no residue may survive a brain swap (constitution X).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path


class RunState:
    """Mutable per-run state; dict fields are shared by reference so
    existing call sites (``state=uni_state``, ``vstate``) keep working."""

    def __init__(self) -> None:
        self.vars: dict = {}          # pack-set vars (site, anchors, flags)
        self.rule_state: dict = {}    # universal rules last-fired state
        self.improve_state: dict = {} # improve/reflect pass bookkeeping
        self.vitals_state: dict = {}  # vitals hediff-diff across samples
        self.phase: dict = {}         # engine: active phase id, iter, history
        self.plan: dict | None = None  # in-force plan (planstage, US3)
        self.completed: bool = False  # prescriptive-phase done flag

    # -- persistence -------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "RunState":
        rs = cls()
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return rs
        if isinstance(saved, dict):
            rs.vars = dict(saved.get("vars") or {})
            if "site" not in rs.vars and saved.get("site"):
                rs.vars["site"] = saved["site"]  # legacy startmode.json
            rs.phase = dict(saved.get("phase") or {})
            rs.plan = saved.get("plan") or None
            rs.completed = bool(saved.get("completed"))
        return rs

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2,
                                  sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def snapshot(self) -> dict:
        """Serializable copy — persisted fields only. rule/vitals/improve
        state are per-run diff caches (rule cooldowns, hediff sets):
        never persisted (feature-008 semantics — fresh each run) but
        cleared on reset() for lifecycle cleanliness."""
        return {
            "vars": dict(self.vars),
            "phase": dict(self.phase),
            "plan": copy.deepcopy(self.plan),
            "completed": self.completed,
        }

    def reset(self) -> None:
        """Clear every field in place — references held by callers stay
        valid (``dict.clear()`` semantics, constitution X residue rule)."""
        self.vars.clear()
        self.rule_state.clear()
        self.improve_state.clear()
        self.vitals_state.clear()
        self.phase.clear()
        self.plan = None
        self.completed = False
