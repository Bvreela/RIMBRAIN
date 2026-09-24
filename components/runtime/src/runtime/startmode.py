"""Start-mode interpreter (feature 008/012; FR-701..709, UR-BRN-011..013).

The mode is a generic phase interpreter: the pack's ``start.phases[]`` is
an ordered list of ``{id, effect, steps, requires?, need?, repeat?,
adopt?, set?}`` objects. Phase order, effects, dispatch steps, thresholds,
and placement arithmetic are pack data; this module only:

- measures the world (``observe_start`` — capability metrics),
- proposes/locks/verifies ledger tasks per phase,
- evaluates pack predicates/resolvers via ``policy.py``,
- evaluates the pack's ``start.exit.conditions`` map.

Delete or reorder phases in the pack and behavior changes with zero code
edits. Established colonies skip phases whose effect already holds.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import brain, policy, views, vitals
from .planloop import observe
from .store import write_atomic

TERMINAL = ("succeeded", "failed", "expired")


def observe_start(game, cfg: dict | None = None) -> dict:
    """Observation surface for pack predicates: enriched state + storage/
    rooms/stocks/base + loose+forbidden items + blueprints + open rects +
    measured fields (beds, food, meals, recreation, cookstation) whose def
    lists come from pack cfg. Missing rpcs degrade to empty — predicates
    then read as not-held (fail-closed)."""
    obs = observe(game)
    for name, rpc in (("storage", "state.storage"),
                      ("rooms", "state.rooms"),
                      ("stocks", "state.stocks"),
                      ("base", "state.base"),
                      ("designations", "state.designations")):
        r = game.rpc(rpc)
        obs[name] = r.get("result") if r.get("ok") else {}
    items = game.rpc("map.find", {"kind": "item", "radius": 80})
    obs["items"] = items.get("result") if items.get("ok") else {}
    forb = game.rpc("map.find", {"kind": "item", "forbidden": True,
                                 "radius": 80})
    obs["forbidden"] = forb.get("result") if forb.get("ok") else {}
    bp = game.rpc("map.find", {"kind": "blueprint"})
    obs["blueprints"] = bp.get("result") if bp.get("ok") else {}
    # frames are construction-in-progress — a separate entity kind, but
    # still pending build work the pack must see (FR-1315)
    fr = game.rpc("map.find", {"kind": "frame"})
    if fr.get("ok"):
        rows = _things(fr.get("result") or {})
        if rows:
            tgt = obs["blueprints"]
            if isinstance(tgt, dict):
                tgt = dict(tgt)
                tgt["things"] = _things(tgt) + rows
                tgt["count"] = int(tgt.get("count") or 0) + len(rows)
            else:
                tgt = {"count": len(rows), "things": rows}
            obs["blueprints"] = tgt
    site_cfg = (cfg or {}).get("site") or {}
    sw = int(site_cfg.get("search_w") or site_cfg.get("zone_w") or 9)
    sh = int(site_cfg.get("search_h") or site_cfg.get("zone_h") or 9)
    # Footprint-aware anchor: candidates are open rects big enough for
    # the whole base plan; anchor_off shifts site.min inside the patch
    # so the plan's negative-offset geometry still lands on open ground.
    rects = game.rpc("map.open_rects", {"w": sw, "h": sh})
    rows = rects.get("result") if rects.get("ok") else []
    off = [int(site_cfg.get("anchor_dx") or 0),
           int(site_cfg.get("anchor_dy") or 0)]
    if not rows and (sw, sh) != (9, 9):
        rects = game.rpc("map.open_rects", {"w": 9, "h": 9})
        rows = rects.get("result") if rects.get("ok") else []
        off = [0, 0]
    for r in (rows if isinstance(rows, list) else []):
        if isinstance(r, dict):
            r["anchor_off"] = off
    obs["open_rects"] = rows
    base = obs.get("base") or {}
    if isinstance(base, dict):
        if isinstance(base.get("anchors"), dict):
            obs["anchors"] = dict(base["anchors"])
        elif isinstance(base.get("anchors"), list):
            obs["anchors"] = list(base["anchors"])
        if base.get("home_center"):
            obs["home_center"] = base["home_center"]
    storage = obs.get("storage")
    obs["zone_count"] = len(storage) if isinstance(storage, list) \
        else len(_things(storage or {}))
    zones = obs.get("storage") or []
    if isinstance(zones, dict):
        zones = zones.get("zones") or zones.get("stockpiles") or []
    obs["zones_growing"] = sum(
        1 for z in zones if isinstance(z, dict)
        and (z.get("plant") or "grow" in str(z.get("label", "")).lower()))
    cfg = cfg or {}
    for d in (cfg.get("recreation", {}) or {}).get("defs",
                                                  ["HorseshoesPin"]):
        r = game.rpc("map.find", {"def": d})
        if r.get("ok") and (r.get("result") or {}).get("count", 0) > 0:
            obs["recreation_present"] = True
            break
    obs.setdefault("recreation_present", False)
    obs["food_source_present"] = obs["zones_growing"] > 0
    if not obs["food_source_present"]:
        plant = (cfg.get("food", {}) or {}).get("plant")
        if plant:
            r = game.rpc("map.find", {"def": plant})
            if r.get("ok") and (r.get("result") or {}).get("count", 0) > 0:
                obs["food_source_present"] = True
    bed_defs = (cfg.get("shelter", {}) or {}).get(
        "bed_defs", ["Bed", "DoubleBed", "SleepingSpot",
                     "DoubleSleepingSpot"])
    beds = 0
    for d in bed_defs:
        r = game.rpc("map.find", {"def": d})
        if r.get("ok"):
            beds += int((r.get("result") or {}).get("count", 0) or 0)
    obs["beds_in_rooms"] = beds
    rooms = obs.get("rooms") or []
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms") or []
    obs["beds_total"] = max(
        beds, sum(int(r.get("beds", 0) or 0) for r in rooms
                  if isinstance(r, dict)))
    obs["bed_blueprints"] = sum(
        1 for t in _things(obs.get("blueprints") or {})
        if isinstance(t, dict)
        and any(d in str(t.get("def") or t.get("build_def")
                        or t.get("entity_def") or t.get("defName")
                        or "")
                for d in bed_defs))
    cook = cfg.get("cooking") or {}
    obs["cookstation_ids"] = []
    for d in cook.get("station_defs") or ["CookingSpot"]:
        r = game.rpc("map.find", {"def": d})
        if r.get("ok"):
            obs["cookstation_ids"] += [t.get("id") for t in
                                       _things(r.get("result") or {})
                                       if t.get("id")]
    obs["meals_present"] = False
    for d in cook.get("meal_defs") or ["MealSimple"]:
        r = game.rpc("map.find", {"def": d})
        if r.get("ok") and (r.get("result") or {}).get("count", 0) > 0:
            obs["meals_present"] = True
            break
    billed = False
    if obs["cookstation_ids"]:
        r = game.rpc("state.bills", {"thing": obs["cookstation_ids"][0]})
        res = r.get("result") if r.get("ok") else None
        bills = (res.get("bills") if isinstance(res, dict)
                 else res if isinstance(res, list) else None) or []
        recipe = cook.get("recipe", "CookMealSimple")
        billed = any(recipe in str(b.get("recipe") if isinstance(b, dict)
                                     else b) for b in bills)
    obs["cookbill_configured"] = billed
    obs["cookstation_ready"] = bool(obs["cookstation_ids"]) and billed
    return obs


def _things(res) -> list:
    t = res.get("things") if isinstance(res, dict) else None
    return t if isinstance(t, list) else []


class StartMode:
    """Interprets the pack's ``start.phases`` through the ledger, then —
    when the run holds past completion — its ``govern.goals``."""

    def __init__(self, pack: dict, ledger, *,
                 sink=None, clock=None, hold: bool = False):
        self.pack = pack
        self.cfg = pack.get("start") or {}
        self.hold = hold
        self.ledger = ledger
        self._sink = sink
        self._clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self.completed = False
        self.vars: dict = {}
        self._rule_state: dict = {}
        self._game = None
        self._poll = 0
        self.last_eval: dict | None = None
        self.decisions: list | None = None  # Quick-Action Matrix sink
        self._mode_path = ledger._path.parent / "startmode.json"
        ledger._effect_eval = self._eval_effect
        if self._mode_path.is_file():
            try:
                saved = json.loads(self._mode_path.read_text())
                self.vars = dict(saved.get("vars") or {})
                if "site" not in self.vars and saved.get("site"):
                    self.vars["site"] = saved["site"]  # legacy shape
                self.completed = bool(saved.get("completed"))
            except (json.JSONDecodeError, OSError):
                pass  # corrupt mode file -> re-derive from observation

    @property
    def site(self):
        return self.vars.get("site")

    def _save_mode(self) -> None:
        write_atomic(self._mode_path, json.dumps(
            {"vars": self.vars, "completed": self.completed},
            sort_keys=True).encode() + b"\n")

    def _ctx(self, obs, tick=0) -> policy.Ctx:
        return policy.Ctx(cfg=self.pack, obs=obs, game=self._game,
                          state=self._rule_state, persist=self.vars,
                          tick=tick, decisions=self.decisions)

    def _eval_effect(self, eff: dict, obs: dict) -> bool:
        """Ledger effect hook — evaluates the phase's pack predicate with
        the task's frozen `need` bound."""
        ctx = policy.Ctx(cfg=self.pack, obs=obs, game=self._game,
                         state=self._rule_state, persist=self.vars,
                         vars={"need": eff.get("need")},
                         tick=obs.get("tick") or 0)
        return bool(policy.check(eff["pred"], ctx))

    # -- phase plumbing --------------------------------------------------------

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

    def _apply_vars(self, ph: dict, ctx) -> None:
        """Bind pack-declared vars: `adopt` restores persisted world state
        (anchors) after a checkpoint reload and refreshes stale bindings —
        the in-game anchor is truth, our mode file is only a cache. `set`
        resolves once when the var remains unset (sticky — e.g. site
        selection)."""
        changed = False
        for var, spec in (ph.get("adopt") or {}).items():
            if isinstance(spec, dict) and spec.get("from_anchor"):
                name = policy.resolve(spec["from_anchor"], ctx)
                anch = policy.FN["anchor"](ctx, name) if name else None
                if anch is not None and anch != self.vars.get(var):
                    self.vars[var] = anch
                    changed = True
        for var, spec in (ph.get("set") or {}).items():
            if self.vars.get(var) is None:
                v = policy.resolve(spec, ctx)
                if v is not None:
                    self.vars[var] = v
                    changed = True
        if changed:
            self._save_mode()

    # -- main step --------------------------------------------------------------

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

    def _govern_step(self, dispatcher, ctx, obs: dict, tick: int) -> dict:
        """Standing goals (pack ``govern.goals``): evaluated in declared
        order each poll once the exit contract holds. ``when`` gates
        engagement (e.g. colony stable); a terminal goal re-arms only
        while its observed effect has lapsed, so sustainment and
        long-horizon objectives share the phase machinery. The first
        active goal does work this poll (UR-RUN-009)."""
        for g in (self.pack.get("govern") or {}).get("goals") or []:
            gid = g.get("id")
            if not gid:
                continue
            self._apply_vars(g, ctx)
            if g.get("when") and not policy.check(g["when"], ctx):
                continue
            tid = self._tid(gid, ns="govern")
            task = self.ledger.tasks.get(tid)
            if task and task.get("state") in TERMINAL:
                if self.ledger._check_effect(task, obs) is not False:
                    continue  # standing satisfied — leave it be
                if task.get("state") != "succeeded":
                    # failed goals back off before re-arming — a
                    # permanently-blocked goal must not starve every
                    # lower-priority goal in the declared order
                    retry = int(policy.resolve(
                        g.get("retry_polls"), ctx) or 25)
                    last = self._rule_state.setdefault(
                        "govern_retry", {}).get(gid, -10 ** 9)
                    if ctx.poll - last < retry:
                        continue
                    self._rule_state["govern_retry"][gid] = ctx.poll
                task = None  # effect lapsed -> re-arm below
            if task is None:
                missing = [v for v in g.get("requires") or []
                           if self.vars.get(v) is None]
                if missing:
                    return {"phase": f"govern.{gid}", "state": "blocked",
                            "reason": "missing:" + ",".join(missing)}
                need = policy.resolve(g.get("need"), ctx) \
                    if "need" in g else None
                self._propose(gid, {"pred": g.get("effect"),
                                    "need": need},
                              g.get("resources") or [], tick, g,
                              ns="govern")
                task = self.ledger.tasks[tid]
            out = self._drive(gid, g, tid, task, dispatcher, ctx, obs,
                              tick, source=f"govern:{gid}")
            if out is not None:
                out["phase"] = f"govern.{gid}"
                return out
        return {"phase": "govern", "state": "holding"}

    def step(self, dispatcher, game, obs: dict, tick: int,
             poll: int | None = None) -> dict:
        """One poll: first non-terminal phase proposes/dispatches/verifies;
        all terminal -> pack exit evaluation -> govern goals when held."""
        self._game = game
        self._poll += 1
        ctx = self._ctx(obs, tick)
        ctx.poll = poll if poll is not None else self._poll
        for ph in self.cfg.get("phases") or []:
            pid = ph.get("id")
            if not pid:
                continue
            tid = self._tid(pid)
            task = self.ledger.tasks.get(tid)
            # var bindings track the world even when the phase's own task
            # is terminal — a reloaded save or stale mode file must not
            # leave downstream phases reading dead coordinates
            self._apply_vars(ph, ctx)
            if task and task.get("state") in TERMINAL:
                continue
            missing = [v for v in ph.get("requires") or []
                       if self.vars.get(v) is None]
            if task is None:
                if missing:
                    return {"phase": pid, "state": "blocked",
                            "reason": "missing:" + ",".join(missing)}
                need = policy.resolve(ph.get("need"), ctx) \
                    if "need" in ph else None
                self._propose(pid, {"pred": ph.get("effect"),
                                    "need": need},
                              ph.get("resources") or [], tick, ph)
                task = self.ledger.tasks[tid]
            out = self._drive(pid, ph, tid, task, dispatcher, ctx, obs,
                              tick, source=f"phase:{pid}")
            if out is not None:
                return out
        # all phases terminal: pack exit evaluation
        ev = self._exit_eval(obs, ctx)
        self.last_eval = ev
        if ev["complete"]:
            first = not self.completed
            self.completed = True
            self._save_mode()
            out = {"phase": "exit", "state": "completed", "eval": ev,
                   "first": first}
            if self.hold:
                # the run doesn't end at the baseline contract — the
                # pack's standing goals take over (UR-RUN-009)
                out["govern"] = self._govern_step(dispatcher, ctx, obs,
                                                tick)
            return out
        # unmet condition -> re-propose a fix phase. `exit.fix` maps a
        # condition to an ordered fallback chain of {phase, when?} (bare
        # strings allowed); the first whose `when` holds is re-proposed.
        fix = (self.cfg.get("exit", {}) or {}).get("fix") or {}
        phase_ids = {ph.get("id") for ph in self.cfg.get("phases") or []}
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
                if target not in phase_ids:
                    continue
                tid = self._tid(target)
                if self.ledger.tasks.get(tid, {}).get("state") in TERMINAL:
                    ph = next(p for p in self.cfg["phases"]
                              if p.get("id") == target)
                    need = policy.resolve(ph.get("need"), ctx) \
                        if "need" in ph else None
                    self._propose(target, {"pred": ph.get("effect"),
                                           "need": need}, [], tick, ph)
                break
            break
        return {"phase": "baseline", "state": "waiting", "eval": ev}

    def _exit_eval(self, obs: dict, ctx) -> dict:
        """Evaluate the pack's start.exit.conditions map generically —
        keys are pack-chosen names; conditions the pack doesn't declare
        are not required."""
        conds = (self.cfg.get("exit", {}) or {}).get("conditions") or {}
        out = {name: bool(policy.check(pred, ctx))
               for name, pred in conds.items()}
        return {"conditions": out, "complete": bool(out) and all(
            out.values())}

    def completed_event(self, obs: dict, ev: dict) -> dict:
        """start.completed envelope (FR-705/707)."""
        colonists = int(obs.get("colonists", {}).get("count", 0)
                        if isinstance(obs.get("colonists"), dict)
                        else obs.get("colonists") or 0)
        return {
            "schema_version": 0,
            "event_id": "evt.start-000001",
            "sequence": 0,
            "event_type": "start.completed",
            "game_tick": obs.get("tick"),
            "wall_time_utc": self._clock(),
            "source": "rimbrainagent.runtime.startmode",
            "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": {
                "mode": "start",
                "colonists": max(colonists, 1),
                "conditions": {k: bool(v)
                               for k, v in ev["conditions"].items()},
                "phases_completed": [ph.get("id") for ph in
                                     self.cfg.get("phases") or []],
            },
            "privacy": {"classification": "internal", "redactions": []},
        }


def wire_sink(dispatcher, sink) -> None:
    """Route dispatcher evidence through `sink`, composing with any prior
    sink so resumed runs don't double-write."""
    if sink is None:
        return
    prev = getattr(dispatcher, "_sink", None)
    if prev is None or prev is sink:
        dispatcher._sink = sink
    else:
        def _s(env: dict) -> None:
            prev(env)
            sink(env)
        dispatcher._sink = _s


def run_start(dispatcher, game, ledger, pack: dict, *,
              iterations: int = 12, sink=None, clock=None,
              speed: int | None = None, live_brain: bool = False,
              hold: bool = False, live_mutate: bool = False,
              mutate_resolver=None, mutate_chat=None) -> dict:
    """Drive Start Mode: observe -> reconcile -> reflex -> phase step.

    `pack` is the full pack dict — phases come from ``pack['start']``,
    universal rules from ``pack['universal']``. `speed` sets game speed
    for the run (live only) and restores prior pause/speed on exit.
    `live_brain` enables the brain-reset request channel (FR-1107).
    `hold` keeps the run alive after ``start.completed``: the pack's
    ``govern.goals`` take over as standing objectives (UR-RUN-009).
    Bounded sub-loops (cycle) pass ``hold=False``.
    `live_mutate` enables the feature-016 reflection pass — pack
    ``mutate:`` triggers fire `rimbrain.improve` proposals that
    materialize as candidates (never touching the active pack file).
    """
    prev = None
    if speed is not None:
        st = game.rpc("game.status")
        prev = st.get("result") if st.get("ok") else None
        game.rpc("game.speed", {"speed": speed})
    try:
        return _run_start(dispatcher, game, ledger, pack,
                          iterations=iterations, sink=sink, clock=clock,
                          speed=speed, live_brain=live_brain, hold=hold,
                          live_mutate=live_mutate,
                          mutate_resolver=mutate_resolver,
                          mutate_chat=mutate_chat)
    finally:
        if prev is not None:
            game.rpc("game.speed", {"speed": prev.get("speed", 0)})
            game.rpc("game.pause",
                     {"paused": bool(prev.get("paused", True))})


def _run_start(dispatcher, game, ledger, pack: dict, *,
               iterations: int = 12, sink=None, clock=None,
               speed: int | None = None, live_brain: bool = False,
               hold: bool = False, live_mutate: bool = False,
               mutate_resolver=None, mutate_chat=None) -> dict:
    uni_state: dict = {}
    decisions: list = []  # Quick-Action Matrix rows for this poll window
    mode = StartMode(pack, ledger, sink=sink, clock=clock, hold=hold)
    mode.decisions = decisions
    state_dir = ledger._path.parent
    outcomes = []
    wire_sink(dispatcher, sink)
    if sink is not None:
        ledger._sink = getattr(dispatcher, "_sink", sink)
    # FR-1401/1411: the mutation pass watches the run's own event stream —
    # wrap the composed sink so every envelope (dispatch + ledger + mode)
    # lands in PassState before onward emission.
    mut = None
    if live_mutate and (pack.get("mutate") or {}):
        from . import mutate as _mut
        mut = _mut.PassState(pack["mutate"])
        _prev_emit = getattr(dispatcher, "_sink", None) or sink

        def _msink(env, _prev=_prev_emit, _ps=mut):
            _ps.note(env)
            if _prev is not None:
                _prev(env)

        dispatcher._sink = _msink
        ledger._sink = _msink
        sink = _msink
    seq = max(ledger._events, getattr(dispatcher, "_events", 0))
    vstate: dict = {}  # vitals hediff-diff state across samples (FR-811)
    vitals_every = int((pack.get("vitals") or {}).get("every") or 50)
    for i in range(iterations):
        # pause-on-load / event letters can re-pause mid-run — re-assert
        # speed periodically so construction actually advances
        if speed is not None and i % 10 == 0:
            st = game.rpc("game.status")
            res = st.get("result") if st.get("ok") else {}
            if res.get("paused"):
                game.rpc("game.speed", {"speed": speed})
        obs = observe_start(game, pack.get("start") or {})
        tick = obs.get("tick") or i
        dispatcher._last_tick = tick  # evidence carries the live tick
        prev = len(decisions)
        # FR-1107/FR-1309: brain request — {} refreshes the active pack,
        # {pack: id} swaps, {unload: true} halts the brain. Every path
        # does a full reinit (UR-BRN-020): ledger pack namespaces
        # tombstoned, mode vars/rule/cooldown/vitals state dropped, so
        # goals re-derive from the colony as-observed. Honored only
        # under --live-brain; scored runs never set the flag.
        req = brain.poll_request(state_dir, live_brain)
        if req is not None:
            err = None
            dropped = 0
            want_unload = bool(req.get("unload"))
            target = req.get("pack") or dispatcher._pack_file
            if want_unload:
                dispatcher._pack = None  # every write now -> no_pack
            elif target:
                try:
                    pack = dispatcher.load_pack(target)["pack"]
                except Exception as e:  # PackError — stay fail-closed
                    err = f"{type(e).__name__}: {e}"
            else:
                err = "no pack to load"
            if err is None:
                (state_dir / "startmode.json").unlink(missing_ok=True)
                dropped = ledger.reset_ns(
                    "start.", "govern.", "combat.", tick=tick)
                uni_state.clear()
                vstate.clear()
                mode = None if want_unload else StartMode(
                    pack, ledger, sink=sink, clock=clock, hold=hold)
                if mode is not None:
                    mode.decisions = decisions
                # FR-1402: a swapped pack carries its own mutate: policy —
                # rebuild the pass state (or drop it on unload).
                if live_mutate and not want_unload:
                    mut = (_mut.PassState(pack["mutate"])
                           if pack.get("mutate") else None)
                    if mut is not None:
                        _prev_emit = getattr(dispatcher, "_sink", None)

                        def _msink2(env, _prev=_prev_emit, _ps=mut):
                            _ps.note(env)
                            if _prev is not None:
                                _prev(env)

                        dispatcher._sink = _msink2
                        ledger._sink = _msink2
                elif want_unload:
                    mut = None
            status = {"ok": err is None, "pack_id": dispatcher._pack_file,
                      "pack_revision": (dispatcher._pack or {})
                      .get("hash"),
                      "state": ("unloaded" if want_unload and err is None
                                else "loaded"),
                      "dropped_tasks": dropped, "error": err}
            brain.write_status(state_dir, **status)
            decisions.append({
                "tick": tick, "poll": i, "source": "ui:brain-reset",
                "template": "brain-reset", "params": {},
                "ok": err is None, "error": err})
            dispatcher._emit("brain.reset", dict(status))
        # FR-811: periodic colony-health vitals -> canonical events so the
        # improve loop can diagnose mood/sickness/downed/death defects.
        if vitals_every and i % vitals_every == 0:
            v, evs = vitals.sample(game, vstate, pack.get("vitals") or {})
            dispatcher._emit("colony.vitals", v)
            for e in evs:
                dispatcher._emit(e["type"], e["payload"])
        ledger.reconcile(obs, tick)
        dispatcher.reflex(obs)
        if mode is None:          # brain unloaded — observe only;
            out = {"phase": "brain", "state": "unloaded"}  # no writes
        else:
            # pack-declared universal rules run every poll, after
            # reflexes
            uni_ctx = policy.Ctx(cfg=pack, obs=obs, game=game,
                                 state=uni_state, persist=mode.vars,
                                 tick=tick, poll=i, decisions=decisions)
            policy.run_rules(
                ((pack.get("universal") or {}).get("rules") or []),
                dispatcher, uni_ctx, source="rule")
            out = mode.step(dispatcher, game, obs, tick, poll=i)
        outcomes.append({"iteration": i, **out})
        # FR-1401: reflection pass — failure/near-failure/cadence triggers
        # over the run's own event stream; never raises into the loop.
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
                    "text": f"mutate.maybe_trigger: {exc}"[:200]})
        views.write_views(
            state_dir,
            views.start_snapshot(mode, ledger, obs,
                                 events_path=state_dir / "events.jsonl",
                                 mutate_view=(mut.view()
                                              if mut is not None
                                              else None))
            if mode is not None else {"phase": "brain",
                                      "state": "unloaded"},
            decisions[prev:])
        if out.get("first"):
            seq += 1
            env = mode.completed_event(obs, out["eval"])
            env["sequence"] = seq
            env["event_id"] = f"evt.start-{seq:06d}"
            emit = sink or getattr(dispatcher, "_sink", None)
            if emit is not None:
                emit(env)
        # completion is a handoff, not an exit, when the run holds —
        # govern goals + universal rules keep working the colony
        if out.get("state") == "completed" and not hold:
            break
        if callable(getattr(game, "advance", None)):
            game.advance(i)
    return {"ok": True, "outcomes": outcomes,
            "completed": bool(mode and mode.completed),
            "site": mode.site if mode is not None else None}
