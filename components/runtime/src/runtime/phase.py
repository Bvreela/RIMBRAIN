"""Unified phase engine (feature 017; FR-1401..1403, FR-1427).

One interpreter drives the whole colony lifecycle off ``pack.phases``:

- a ``prescriptive`` phase holds the ordered work units (the former
  ``start.phases[]`` — each ``{id, effect, steps, requires?, need?,
  repeat?, adopt?, set?}``) plus a ``complete`` contract (the former
  ``start.exit``: ``conditions`` map + ``fix`` fallback chains);
- a non-prescriptive phase holds scoped ``goals`` evaluated with the
  same standing-goal machinery while the phase is current, and
  completes when its own ``complete`` conditions hold (or runs
  indefinitely when none are declared — a resting state);
- ``pack.standing_goals`` (former ``govern.goals``) evaluate in
  declared order once prescriptive work is done — sustainment and
  long-horizon objectives share the phase machinery.

Phase order, effects, dispatch steps, thresholds, and placement
arithmetic are pack data; this module only proposes/locks/verifies
ledger tasks, evaluates pack predicates via ``policy.py``, and
evaluates completion contracts. Delete or reorder phases/goals in the
pack and behavior changes with zero code edits.

Ledger task namespaces: prescriptive steps ``start.<step>``, standing
goals ``govern.<goal>``, phase-scoped goals ``phase.<phid>.<goal>`` —
kept identical to feature 008/015 so existing ledgers/checkpoints and
``reset_ns`` tombstones carry over.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import policy, templates, views
from .observe import observe as _observe
from .observe import observe_combat as _observe_combat
from .runstate import RunState

TERMINAL = ("succeeded", "failed", "expired")


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


class PhaseEngine:
    """Interprets ``pack.phases`` + ``pack.standing_goals`` through the
    ledger. `runstate` owns vars/rule-state/completion; when omitted a
    fresh RunState is created (tests drive the engine bare).
    `scripted=True` enables ``kind: combat`` phases (dev-harness rounds;
    refused under the default fair path since the spawn/cleanup tooling
    is dev-class anyway)."""

    def __init__(self, pack: dict, ledger, *, runstate: RunState | None = None,
                 sink=None, clock=None, hold: bool = False,
                 scripted: bool = False, only: str | None = None):
        self.pack = pack
        self.phases = templates.phases_of(pack)
        self.standing = templates.standing_goals_of(pack)
        self.hold = hold
        self.ledger = ledger
        self._sink = sink
        self._clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self.rs = runstate or RunState()
        self.scripted = scripted
        self.only = only
        self._game = None
        self._poll = 0
        self.last_eval: dict | None = None
        self.decisions: list | None = None  # Quick-Action Matrix sink
        self.plan_goals: list = []          # promoted runtime goals
        self._plan_off: set = set()         # plan-deactivated goal ids
        self.apply_plan(self.rs.plan)
        ledger._effect_eval = self._eval_effect

    def apply_plan(self, plan: dict | None) -> None:
        """Install/reload the in-force plan's runtime effect: promoted
        goals join the standing drive, promoted phases append, and
        ``deactivate`` ids drop out of eligibility (FR-1414)."""
        plan = plan or {}
        self.plan_goals = [p["body"] for p in
                           plan.get("promoted") or []
                           if p.get("as") != "phase" and p.get("body")]
        self._plan_off = set(plan.get("deactivate") or [])
        for p in plan.get("promoted") or []:
            body = p.get("body") or {}
            if p.get("as") == "phase" and body.get("id") \
                    and not any(ph.get("id") == body["id"]
                                for ph in self.phases):
                self.phases.append(body)

    # -- state facades ------------------------------------------------

    @property
    def vars(self) -> dict:
        return self.rs.vars

    @property
    def completed(self) -> bool:
        return self.rs.completed

    @property
    def site(self):
        return self.rs.vars.get("site")

    def _done(self, pid: str) -> bool:
        return bool((self.rs.phase.get(pid) or {}).get("done"))

    def _mark_done(self, pid: str) -> None:
        self.rs.phase.setdefault(pid, {})["done"] = True

    def _ctx(self, obs, tick=0) -> policy.Ctx:
        return policy.Ctx(cfg=self.pack, obs=obs, game=self._game,
                          state=self.rs.rule_state, persist=self.rs.vars,
                          tick=tick, decisions=self.decisions)

    def _eval_effect(self, eff: dict, obs: dict) -> bool:
        """Ledger effect hook — evaluates the phase's pack predicate with
        the task's frozen `need` bound."""
        ctx = policy.Ctx(cfg=self.pack, obs=obs, game=self._game,
                         state=self.rs.rule_state, persist=self.rs.vars,
                         vars={"need": eff.get("need")},
                         tick=obs.get("tick") or 0)
        return bool(policy.check(eff["pred"], ctx))

    # -- phase plumbing -------------------------------------------------

    def _tid(self, phase: str, ns: str = "start") -> str:
        return f"{ns}.{phase}"

    def _propose(self, phase: str, effect: dict, resources: list,
                 tick: int, ph: dict | None = None,
                 ns: str = "start") -> None:
        ph = ph or {}
        self.ledger.propose({
            "task_id": self._tid(phase, ns), "kind": f"{ns}.{phase}",
            "action": {"template_id": None, "params": {}},
            "resources": resources, "effect": effect,
            "lease_ticks": int(ph.get("lease_ticks") or 200),
            "max_attempts": int(ph.get("attempts") or 3)}, tick=tick)

    def _apply_vars(self, ph: dict, ctx) -> bool:
        """Bind pack-declared vars: `adopt` restores persisted world state
        (anchors) after a checkpoint reload and refreshes stale bindings —
        the in-game anchor is truth, our runstate is only a cache. `set`
        resolves once when the var remains unset (sticky — e.g. site
        selection). Returns True when bindings changed (caller saves)."""
        changed = False
        for var, spec in (ph.get("adopt") or {}).items():
            if isinstance(spec, dict) and spec.get("from_anchor"):
                name = policy.resolve(spec["from_anchor"], ctx)
                anch = policy.FN["anchor"](ctx, name) if name else None
                if anch is not None and anch != self.rs.vars.get(var):
                    self.rs.vars[var] = anch
                    changed = True
        for var, spec in (ph.get("set") or {}).items():
            if self.rs.vars.get(var) is None:
                v = policy.resolve(spec, ctx)
                if v is not None:
                    self.rs.vars[var] = v
                    changed = True
        return changed

    # -- task drive ------------------------------------------------------

    def _drive(self, pid: str, spec: dict, tid: str, task: dict,
               dispatcher, ctx, obs: dict, tick: int,
               source: str) -> dict | None:
        """Advance one ledger task through proposed->locked->dispatched->
        verifying. Returns an outcome dict when the poll should stop on
        this unit of work, or None to fall through to the next entry."""
        ctx.vars["need"] = (task.get("effect") or {}).get("need")
        st = task["state"]
        effect_holds = self.ledger._check_effect(task, obs) is True
        if st == "proposed":
            if effect_holds:
                # established-colony skip: effect already holds
                self.ledger.acquire(tid, tick)
                self.ledger._transition(tid, "dispatched",
                                        "skipped_effect_present", tick)
                self.ledger.verify(tid, obs, tick)
                return None
            self.ledger.acquire(tid, tick)
            st = task["state"]
        if st == "locked":
            if effect_holds:
                self.ledger._transition(tid, "dispatched",
                                        "skipped_effect_present", tick)
                st = task["state"]
            else:
                res = policy.run_steps(spec.get("steps"), dispatcher,
                                       ctx, source=source)
                self.ledger.mark_dispatched(
                    tid, ok=bool(res.get("ok")), tick=tick)
                if not res.get("ok"):
                    return {"phase": pid, "state": task["state"],
                            "error": (res.get("error") or {})
                            .get("code")}
                # just dispatched — verify against this obs and return;
                # the repeat guard only fires on later polls so a
                # non-idempotent step isn't re-run against stale state
                v = self.ledger.verify(tid, obs, tick)
                return {"phase": pid, "state": task["state"],
                        "verdict": v.get("verdict", "transitioned")}
        if st in ("dispatched", "verifying"):
            absent = self.ledger._check_effect(task, obs) is False
            # pack-declared repeat guard: keep issuing the unit work
            # while the effect is absent and the guard holds
            rep = spec.get("repeat") or {}
            if rep and absent \
                    and (not rep.get("while")
                         or policy.check(rep["while"], ctx)):
                policy.run_steps(spec.get("steps"), dispatcher, ctx,
                                 source=source)
            # pack-declared escalation: after `after_attempts` failed
            # verify cycles the blocker is structural, not slow work —
            # run remediation steps (each step's `when` keeps it
            # idempotent: e.g. expand storage when hauling can't land)
            esc = spec.get("escalate") or {}
            if esc and absent and int(task.get("attempts") or 0) \
                    >= int(esc.get("after_attempts") or 2):
                policy.run_steps(esc.get("steps"), dispatcher, ctx,
                                 source=f"{source}:escalate")
            v = self.ledger.verify(tid, obs, tick)
            return {"phase": pid, "state": task["state"],
                    "verdict": v.get("verdict", "transitioned")}
        return {"phase": pid, "state": st}

    # -- goals ------------------------------------------------------------

    def _goal_entry(self, g: dict, dispatcher, ctx, obs: dict,
                    tick: int, ns: str) -> dict | None:
        """Drive one goal through propose->dispatch->verify. Returns an
        outcome dict when this goal did work (or is blocked) and the
        poll should stop on it, or None to fall through."""
        gid = g.get("id")
        if not gid or gid in self._plan_off:
            return None
        self._apply_vars(g, ctx)
        if g.get("when") and not policy.check(g["when"], ctx):
            return None
        tid = self._tid(gid, ns=ns)
        task = self.ledger.tasks.get(tid)
        if task and task.get("state") in TERMINAL:
            if self.ledger._check_effect(task, obs) is not False:
                return None  # standing satisfied — leave it be
            if task.get("state") != "succeeded":
                # failed goals back off before re-arming — a
                # permanently-blocked goal must not starve every
                # lower-priority goal in the declared order
                retry = int(policy.resolve(
                    g.get("retry_polls"), ctx) or 25)
                last = self.rs.rule_state.setdefault(
                    "govern_retry", {}).get(gid, -10 ** 9)
                if ctx.poll - last < retry:
                    return None
                self.rs.rule_state["govern_retry"][gid] = ctx.poll
            task = None  # effect lapsed -> re-arm below
        if task is None:
            missing = [v for v in g.get("requires") or []
                       if self.rs.vars.get(v) is None]
            if missing:
                return {"phase": f"{ns}.{gid}", "state": "blocked",
                        "reason": "missing:" + ",".join(missing)}
            need = policy.resolve(g.get("need"), ctx) \
                if "need" in g else None
            self._propose(gid, {"pred": g.get("effect"),
                                "need": need},
                          g.get("resources") or [], tick, g, ns=ns)
            task = self.ledger.tasks[tid]
        out = self._drive(gid, g, tid, task, dispatcher, ctx, obs,
                          tick, source=f"{ns}:{gid}")
        if out is not None:
            out["phase"] = f"{ns}.{gid}"
        return out

    def _goal_eligible(self, g: dict, ctx, obs: dict, ns: str) -> bool:
        """Select-stage eligibility: `when` holds, not terminal-
        satisfied, not in failed-goal retry backoff (mirrors the skip
        conditions of `_goal_entry` — a dead goal must not eat the
        action list)."""
        if not g.get("id") or g["id"] in self._plan_off:
            return False
        self._apply_vars(g, ctx)
        if g.get("when") and not policy.check(g["when"], ctx):
            return False
        task = self.ledger.tasks.get(self._tid(g["id"], ns=ns))
        if task and task.get("state") in TERMINAL:
            if self.ledger._check_effect(task, obs) is not False:
                return False            # standing satisfied
            if task.get("state") != "succeeded":
                retry = int(policy.resolve(
                    g.get("retry_polls"), ctx) or 25)
                last = self.rs.rule_state.get(
                    "govern_retry", {}).get(g["id"], -10 ** 9)
                if ctx.poll - last < retry:
                    return False        # backing off, not a candidate
        if task is None and g.get("effect") \
                and policy.check(g["effect"], ctx):
            return False  # already satisfied — nothing to offer
        return True

    def _sweep_goals(self, goals: list, ctx, obs: dict, tick: int,
                     ns: str) -> None:
        """Materialize untracked goals into the ledger — propose the
        standing contract and verify it immediately when the effect
        already holds. Keeps the audit trail complete while the select
        stage offers only actionable candidates."""
        for g in goals or []:
            gid = g.get("id")
            if not gid:
                continue
            tid = self._tid(gid, ns=ns)
            if tid in self.ledger.tasks:
                continue
            self._apply_vars(g, ctx)
            if g.get("when") and not policy.check(g["when"], ctx):
                continue
            if [v for v in g.get("requires") or []
                    if self.rs.vars.get(v) is None]:
                continue
            need = policy.resolve(g.get("need"), ctx) \
                if "need" in g else None
            self._propose(gid, {"pred": g.get("effect"), "need": need},
                          g.get("resources") or [], tick, g, ns=ns)
            task = self.ledger.tasks[tid]
            if self.ledger._check_effect(task, obs) is True:
                self.ledger.acquire(tid, tick)
                self.ledger._transition(
                    tid, "dispatched", "skipped_effect_present", tick)
                self.ledger.verify(tid, obs, tick)

    def prescriptive_active(self) -> bool:
        """A prescriptive phase still drives — the start contract isn't
        met yet, so phase-0 structural work runs before any
        model-assisted stage engages."""
        for ph in self.phases:
            pid = ph.get("id")
            if not pid or self._done(pid):
                continue
            if self.only and pid != self.only:
                continue
            return bool(ph.get("prescriptive"))
        return False

    def goal_sources(self) -> list[tuple[str, list]]:
        """(ns, goals) pairs feeding the select stage's colony scope:
        the active non-prescriptive phase's goals, or standing goals
        once every phase is done. While a prescriptive phase is active
        the colony scope is empty — init's structural steps stay
        deterministic (FR-1410)."""
        for ph in self.phases:
            pid = ph.get("id")
            if not pid or self._done(pid):
                continue
            if self.only and pid != self.only:
                continue
            if ph.get("prescriptive") or ph.get("kind") == "combat":
                return []        # init/scripted phase still driving
            return [(f"phase.{pid}", ph.get("goals") or [])]
        if self.only:
            return []
        goals = self.standing + self.plan_goals
        return [("govern", goals)] if goals else []

    def _goals_step(self, goals: list, dispatcher, ctx, obs: dict,
                    tick: int, ns: str) -> dict:
        """Standing goals evaluated in declared order each poll. ``when``
        gates engagement; a terminal goal re-arms only while its observed
        effect has lapsed, so sustainment and long-horizon objectives
        share the phase machinery. The first active goal does work this
        poll (UR-RUN-009)."""
        for g in goals or []:
            out = self._goal_entry(g, dispatcher, ctx, obs, tick, ns)
            if out is not None:
                return out
        return {"phase": ns, "state": "holding"}

    # -- prescriptive phase -----------------------------------------------

    def _prescriptive_step(self, ph: dict, dispatcher, ctx, obs: dict,
                           tick: int) -> dict:
        """One poll inside a prescriptive phase: first non-terminal work
        unit proposes/dispatches/verifies; all terminal -> completion
        contract evaluation + fix re-proposal."""
        pid = ph.get("id")
        steps = ph.get("steps") or []
        for unit in steps:
            uid = unit.get("id")
            if not uid:
                continue
            tid = self._tid(uid)
            task = self.ledger.tasks.get(tid)
            # var bindings track the world even when the unit's own task
            # is terminal — a reloaded save or stale runstate must not
            # leave downstream units reading dead coordinates
            self._apply_vars(unit, ctx)
            if task and task.get("state") in TERMINAL:
                continue
            missing = [v for v in unit.get("requires") or []
                       if self.rs.vars.get(v) is None]
            if task is None:
                if missing:
                    return {"phase": uid, "state": "blocked",
                            "reason": "missing:" + ",".join(missing)}
                need = policy.resolve(unit.get("need"), ctx) \
                    if "need" in unit else None
                self._propose(uid, {"pred": unit.get("effect"),
                                    "need": need},
                              unit.get("resources") or [], tick, unit)
                task = self.ledger.tasks[tid]
            out = self._drive(uid, unit, tid, task, dispatcher, ctx,
                              obs, tick, source=f"{pid}:{uid}")
            if out is not None:
                return out
        # all units terminal: completion contract evaluation
        ev = self._complete_eval(ph, ctx)
        self.last_eval = ev
        if ev["complete"]:
            first = not self._done(pid)
            self._mark_done(pid)
            if ph.get("prescriptive"):
                first = first and not self.rs.completed
                self.rs.completed = True
            return {"phase": "exit", "state": "completed", "eval": ev,
                    "first": first, "phase_id": pid}
        # unmet condition -> re-propose a fix unit. `complete.fix` maps a
        # condition to an ordered fallback chain of {phase, when?} (bare
        # strings allowed); the first whose `when` holds is re-proposed.
        fix = (ph.get("complete") or {}).get("fix") or {}
        unit_ids = {u.get("id") for u in steps}
        for cond, held in ev["conditions"].items():
            if held:
                continue
            chain = fix.get(cond, [cond])
            if not isinstance(chain, list):
                chain = [chain]
            for entry in chain:
                if isinstance(entry, dict):
                    if entry.get("when") \
                            and not policy.check(entry["when"], ctx):
                        continue
                    target = entry.get("phase")
                else:
                    target = entry
                if target not in unit_ids:
                    continue
                tid = self._tid(target)
                if self.ledger.tasks.get(tid, {}).get("state") \
                        in TERMINAL:
                    unit = next(u for u in steps
                                if u.get("id") == target)
                    need = policy.resolve(unit.get("need"), ctx) \
                        if "need" in unit else None
                    self._propose(target, {"pred": unit.get("effect"),
                                           "need": need}, [], tick,
                                  unit)
                break
            break
        return {"phase": "baseline", "state": "waiting", "eval": ev}

    def _complete_eval(self, ph: dict, ctx) -> dict:
        """Evaluate the phase's ``complete.conditions`` map generically —
        keys are pack-chosen names; undeclared conditions are not
        required."""
        conds = (ph.get("complete") or {}).get("conditions") or {}
        out = {name: bool(policy.check(pred, ctx))
               for name, pred in conds.items()}
        return {"conditions": out, "complete": bool(out) and all(
            out.values())}

    # -- main step ---------------------------------------------------------

    def step(self, dispatcher, game, obs: dict, tick: int,
             poll: int | None = None,
             select_out: dict | None = None) -> dict:
        """One poll: first non-done lifecycle phase does its work; all
        done -> pack standing goals (the held state). ``select_out`` is
        the decide stage's outcome when configured — it replaces the
        direct goal drive (the select pick already dispatched through
        the engine's goal machinery)."""
        self._game = game
        self._poll += 1
        ctx = self._ctx(obs, tick)
        ctx.poll = poll if poll is not None else self._poll
        for ph in self.phases:
            pid = ph.get("id")
            if not pid or self._done(pid):
                continue
            if self.only and pid != self.only:
                continue  # --stage: drive exactly one phase
            if ph.get("when") and not policy.check(ph["when"], ctx):
                # ordered phases: a gated phase blocks later ones so a
                # combat phase can't be skipped past by a build phase
                return {"phase": pid, "state": "blocked",
                        "reason": "when"}
            if ph.get("kind") == "combat":
                if not self.scripted:
                    # dev-harness phases never run in a normal drive —
                    # skipped (not done) so --stage can engage them
                    continue
                return self._combat_phase(ph, dispatcher, game, obs,
                                          tick, poll=ctx.poll)
            if ph.get("prescriptive"):
                return self._prescriptive_step(ph, dispatcher, ctx, obs,
                                               tick)
            if select_out is not None:
                self._sweep_goals(ph.get("goals") or [], ctx, obs,
                                  tick, ns=f"phase.{pid}")
                g_out = select_out
            else:
                g_out = self._goals_step(
                    ph.get("goals") or [], dispatcher, ctx, obs, tick,
                    ns=f"phase.{pid}")
            if ph.get("complete"):
                ev = self._complete_eval(ph, ctx)
                if ev["complete"]:
                    self._mark_done(pid)
                    continue
            if g_out.get("state") != "holding":
                return g_out
            # goals holding but phase not complete -> resting state
            return g_out
        # every declared phase done (or none declared): standing goals
        # are the colony's held state — the former `hold` govern path,
        # now unconditional when the pack declares them. A --stage run
        # ends with its phase, not with colony governance.
        if self.only:
            return {"phase": self.only, "state": "done"}
        if select_out is not None:
            # decide stage owns goal drive; sweep materializes the
            # standing contracts the pick didn't reach this poll
            self._sweep_goals(self.standing, ctx, obs, tick,
                              ns="govern")
            return select_out
        return self._goals_step(self.standing, dispatcher, ctx, obs,
                                tick, ns="govern")

    # -- combat phase kind (dev harness; FR-1429) -------------------------

    def _combat_phase(self, ph: dict, dispatcher, game, obs: dict,
                      tick: int, poll: int = 0) -> dict:
        """Execute the pack's combat script as a phase kind — the former
        combatmode.py orchestration, driven by phase cfg:

            setup[]   -> once (e.g. save checkpoint)
            per round: spawn[] -> engage rule-loop (until predicate /
                       budgets) -> cleanup[] (strip, heal, undraft,
                       reload checkpoint)

        Spawn kinds, factions, counts, the engage predicate and its
        rules, and every cleanup write are pack data; round/verdict/
        casualty accounting is engine bookkeeping (FR-805)."""
        import json
        cfg = ph.get("combat") or self.pack.get("combat") or {}
        pid = ph.get("id") or "combat"
        # FR-803: combat sits strictly after the init baseline unless
        # the pack waives it (combat.prereq / skip_prereq)
        if cfg.get("prereq", "start_completed") == "start_completed" \
                and not cfg.get("skip_prereq") and not self.rs.completed:
            return {"phase": pid, "state": "blocked",
                    "error": "combat.prereq",
                    "reason": "start.completed not reached"}

        state_dir = Path(getattr(self.ledger, "_path", "tasks.jsonl")) \
            .parent
        iterations = int(cfg.get("poll_iterations")
                         or cfg.get("iterations") or 60)
        speed = cfg.get("speed")
        prev = None
        if speed is not None:
            st = game.rpc("game.status")
            prev = st.get("result") if st.get("ok") else None
            game.rpc("game.speed", {"speed": speed})
        rounds = int(cfg.get("rounds", 1))
        engage = cfg.get("engage") or {}
        budget = int(engage.get("tick_budget", 12000))
        spawn_grace = int(engage.get("spawn_grace_ticks", 3000))
        uni_rules = templates.rules_of(self.pack) \
            if engage.get("universal_rules", True) else []
        engage_rules = engage.get("rules") or []
        # pack cfg block that owns delegate_order (combat: or dev_combat:)
        ocfg = policy._combat_cfg(policy.Ctx(cfg=self.pack))
        uni_state = self.rs.rule_state
        seq = getattr(dispatcher, "_events", 0)
        out = {"ok": True, "rounds": [], "spawned": 0, "cleared": 0,
               "casualties": 0, "ticks": 0}
        decisions = self.decisions if self.decisions is not None else []
        cursor = [0]

        def _flush(o, pl=0):
            views.write_views(
                state_dir,
                views.combat_snapshot(self.pack, o, out["rounds"], pl),
                decisions[cursor[0]:])
            cursor[0] = len(decisions)

        try:
            obs = _observe(game)
            ctx = policy.Ctx(cfg=self.pack, obs=obs, game=game,
                             state=uni_state, persist=self.rs.vars,
                             tick=obs.get("tick") or 0,
                             poll=0, decisions=decisions)
            policy.run_steps(cfg.get("setup"), dispatcher, ctx,
                             source="combat:setup")
            _flush(obs)
            for rnd in range(rounds):
                obs = _observe(game)
                base = _colonist_ids(obs)
                ctx = policy.Ctx(cfg=self.pack, obs=obs, game=game,
                                 state=uni_state, persist=self.rs.vars,
                                 vars={"round": rnd},
                                 tick=obs.get("tick") or 0, poll=0,
                                 decisions=decisions)
                policy.run_steps(cfg.get("spawn"), dispatcher, ctx,
                                 source=f"combat:spawn:r{rnd}")
                _flush(obs)
                round_start = obs.get("tick") or 0
                spawned_round = cleared_round = 0
                verdict = "failed"
                for i in range(iterations):
                    # lean combat obs: the engage loop spends polls acting,
                    # not watching (storage/items/blueprints skipped)
                    obs = _observe_combat(game, ocfg)
                    tick = obs.get("tick") or 0
                    ctx = policy.Ctx(cfg=self.pack, obs=obs, game=game,
                                     state=uni_state,
                                     persist=self.rs.vars,
                                     vars={"round": rnd},
                                     tick=tick, poll=i,
                                     decisions=decisions)
                    # hostile spawns auto-pause (raid letters) —
                    # re-assert speed or the round stalls paused
                    if speed is not None and engage.get(
                            "speed_reassert", True) and i % 10 == 0:
                        st = game.rpc("game.status")
                        res = st.get("result") if st.get("ok") else {}
                        if res.get("paused"):
                            game.rpc("game.speed", {"speed": speed})
                    # shares the ctx snapshot — one threats RPC per poll
                    hostiles = policy._hostile_rows(ctx)
                    if not spawned_round:
                        spawned_round = len(hostiles)
                    if spawned_round and engage.get("until") \
                            and policy.check(engage["until"], ctx):
                        verdict = "cleared"
                        cleared_round = spawned_round
                        break
                    if not spawned_round \
                            and tick - round_start > spawn_grace:
                        verdict = "no-spawn"
                        break
                    if tick - round_start > budget:
                        break
                    policy.run_rules(uni_rules + engage_rules,
                                     dispatcher, ctx, source="combat")
                    _flush(obs, i)
                    if callable(getattr(game, "advance", None)):
                        game.advance(i)
                after = _colonist_ids(_observe(game))
                casualties = max(0, len(set(base) - set(after)))
                out["casualties"] += casualties
                out["spawned"] += spawned_round
                out["cleared"] += cleared_round
                out["rounds"].append(
                    {"round": rnd, "verdict": verdict,
                     "hostiles": spawned_round,
                     "casualties": casualties})
                obs = _observe(game)
                ctx = policy.Ctx(cfg=self.pack, obs=obs, game=game,
                                 state=uni_state, persist=self.rs.vars,
                                 vars={"round": rnd},
                                 tick=obs.get("tick") or 0, poll=0,
                                 decisions=decisions)
                policy.run_steps(cfg.get("cleanup"), dispatcher, ctx,
                                 source=f"combat:cleanup:r{rnd}")
                _flush(ctx.obs)
                out["ticks"] += (ctx.obs.get("tick") or round_start) \
                    - round_start
                _wait_playing(game)
            verdict_all = ("cleared"
                           if all(r["verdict"] == "cleared"
                                  for r in out["rounds"]) else "failed")
            env = {
                "schema_version": 0,
                "event_id": f"evt.combat-{seq + 1:06d}",
                "sequence": seq + 1,
                "event_type": "combat.completed",
                "game_tick": None,
                "wall_time_utc": self._clock(),
                "source": "rimbrainagent.runtime.phase",
                "correlation": {},
                "revisions": {"schema_version": 0},
                "payload": {
                    "mode": "combat", "rounds": rounds,
                    "hostiles_spawned": out["spawned"],
                    "hostiles_cleared": out["cleared"],
                    "colonist_casualties": out["casualties"],
                    "ticks": out["ticks"], "verdict": verdict_all},
                "privacy": {"classification": "internal",
                            "redactions": []},
            }
            emit = self._sink or getattr(dispatcher, "_sink", None)
            if emit is not None:
                emit(env)
            out["verdict"] = verdict_all
            out["event"] = env
        finally:
            if prev is not None:
                game.rpc("game.speed", {"speed": prev.get("speed", 0)})
                game.rpc("game.pause",
                         {"paused": bool(prev.get("paused", True))})
        self._mark_done(pid)
        return {"phase": pid, "state": "completed",
                "combat": out, "verdict": out.get("verdict")}

    def _exit_eval(self, obs: dict, ctx) -> dict:
        """Compat alias (ported tests): evaluate the prescriptive phase's
        completion contract — same semantics as the old StartMode hook."""
        ph = next((p for p in self.phases if p.get("prescriptive")),
                  self.phases[0] if self.phases else {})
        return self._complete_eval(ph, ctx)

    # -- evidence -----------------------------------------------------------

    def completed_event(self, obs: dict, ev: dict, *,
                        phase_id: str = "init") -> dict:
        """Phase-completion envelope (FR-705/707 evidence — the former
        ``start.completed``)."""
        colonists = int(obs.get("colonists", {}).get("count", 0)
                        if isinstance(obs.get("colonists"), dict)
                        else obs.get("colonists") or 0)
        steps = []
        for ph in self.phases:
            if ph.get("id") == phase_id:
                steps = [u.get("id") for u in ph.get("steps") or []]
        return {
            "schema_version": 0,
            "event_id": "evt.start-000001",
            "sequence": 0,
            "event_type": "start.completed",
            "game_tick": obs.get("tick"),
            "wall_time_utc": self._clock(),
            "source": "rimbrainagent.runtime.phase",
            "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": {
                "mode": "start",
                "phase": phase_id,
                "colonists": max(colonists, 1),
                "conditions": {k: bool(v)
                               for k, v in ev["conditions"].items()},
                "phases_completed": steps,
            },
            "privacy": {"classification": "internal", "redactions": []},
        }
