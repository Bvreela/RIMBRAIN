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

from . import policy
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
    rects = game.rpc("map.open_rects", {"w": 9, "h": 9})
    obs["open_rects"] = rects.get("result") if rects.get("ok") else []
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
        and any(d in str(t.get("def") or "") for d in bed_defs))
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
    """Interprets the pack's ``start.phases`` through the ledger."""

    def __init__(self, pack: dict, ledger, *,
                 sink=None, clock=None):
        self.pack = pack
        self.cfg = pack.get("start") or {}
        self.ledger = ledger
        self._sink = sink
        self._clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self.completed = False
        self.vars: dict = {}
        self._rule_state: dict = {}
        self._game = None
        self._poll = 0
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
                          tick=tick)

    def _eval_effect(self, eff: dict, obs: dict) -> bool:
        """Ledger effect hook — evaluates the phase's pack predicate with
        the task's frozen `need` bound."""
        ctx = policy.Ctx(cfg=self.pack, obs=obs, game=self._game,
                         state=self._rule_state, persist=self.vars,
                         vars={"need": eff.get("need")},
                         tick=obs.get("tick") or 0)
        return bool(policy.check(eff["pred"], ctx))

    # -- phase plumbing --------------------------------------------------------

    def _tid(self, phase: str) -> str:
        return f"start.{phase}"

    def _propose(self, phase: str, effect: dict, resources: list,
                 tick: int, ph: dict | None = None) -> None:
        ph = ph or {}
        self.ledger.propose({
            "task_id": self._tid(phase), "kind": f"start.{phase}",
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

    def step(self, dispatcher, game, obs: dict, tick: int) -> dict:
        """One poll: first non-terminal phase proposes/dispatches/verifies;
        all terminal -> pack exit evaluation."""
        self._game = game
        self._poll += 1
        ctx = self._ctx(obs, tick)
        ctx.poll = self._poll
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
                    continue
                self.ledger.acquire(tid, tick)
                st = task["state"]
            if st == "locked":
                if effect_holds:
                    self.ledger._transition(tid, "dispatched",
                                            "skipped_effect_present", tick)
                    st = task["state"]
                else:
                    res = policy.run_steps(ph.get("steps"), dispatcher,
                                           ctx)
                    self.ledger.mark_dispatched(
                        tid, ok=bool(res.get("ok")), tick=tick)
                    st = task["state"]
                    if not res.get("ok"):
                        return {"phase": pid, "state": st,
                                "error": (res.get("error") or {})
                                .get("code")}
                    # just dispatched — verify against this obs and return;
                    # the repeat guard only fires on later polls so a
                    # non-idempotent step isn't re-run against stale state
                    v = self.ledger.verify(tid, obs, tick)
                    return {"phase": pid, "state": task["state"],
                            "verdict": v.get("verdict", "transitioned")}
            if st in ("dispatched", "verifying"):
                # pack-declared repeat guard: keep issuing the unit work
                # while the effect is absent and the guard holds
                rep = ph.get("repeat") or {}
                if rep and self.ledger._check_effect(task, obs) is False \
                        and (not rep.get("while")
                             or policy.check(rep["while"], ctx)):
                    policy.run_steps(ph.get("steps"), dispatcher, ctx)
                v = self.ledger.verify(tid, obs, tick)
                return {"phase": pid, "state": task["state"],
                        "verdict": v.get("verdict", "transitioned")}
            return {"phase": pid, "state": st}
        # all phases terminal: pack exit evaluation
        ev = self._exit_eval(obs, ctx)
        if ev["complete"]:
            first = not self.completed
            self.completed = True
            self._save_mode()
            return {"phase": "exit", "state": "completed", "eval": ev,
                    "first": first}
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
              speed: int | None = None) -> dict:
    """Drive Start Mode: observe -> reconcile -> reflex -> phase step.

    `pack` is the full pack dict — phases come from ``pack['start']``,
    universal rules from ``pack['universal']``. `speed` sets game speed
    for the run (live only) and restores prior pause/speed on exit.
    """
    prev = None
    if speed is not None:
        st = game.rpc("game.status")
        prev = st.get("result") if st.get("ok") else None
        game.rpc("game.speed", {"speed": speed})
    try:
        return _run_start(dispatcher, game, ledger, pack,
                          iterations=iterations, sink=sink, clock=clock,
                          speed=speed)
    finally:
        if prev is not None:
            game.rpc("game.speed", {"speed": prev.get("speed", 0)})
            game.rpc("game.pause",
                     {"paused": bool(prev.get("paused", True))})


def _run_start(dispatcher, game, ledger, pack: dict, *,
               iterations: int = 12, sink=None, clock=None,
               speed: int | None = None) -> dict:
    uni_state: dict = {}
    mode = StartMode(pack, ledger, sink=sink, clock=clock)
    outcomes = []
    wire_sink(dispatcher, sink)
    if sink is not None:
        ledger._sink = getattr(dispatcher, "_sink", sink)
    seq = max(ledger._events, getattr(dispatcher, "_events", 0))
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
        ledger.reconcile(obs, tick)
        dispatcher.reflex(obs)
        # pack-declared universal rules run every poll, after reflexes
        uni_ctx = policy.Ctx(cfg=pack, obs=obs, game=game,
                             state=uni_state, persist=mode.vars,
                             tick=tick, poll=i)
        policy.run_rules(
            ((pack.get("universal") or {}).get("rules") or []),
            dispatcher, uni_ctx)
        out = mode.step(dispatcher, game, obs, tick)
        outcomes.append({"iteration": i, **out})
        if out.get("state") == "completed":
            if out.get("first"):
                seq += 1
                env = mode.completed_event(obs, out["eval"])
                env["sequence"] = seq
                env["event_id"] = f"evt.start-{seq:06d}"
                emit = sink or getattr(dispatcher, "_sink", None)
                if emit is not None:
                    emit(env)
            break
        if callable(getattr(game, "advance", None)):
            game.advance(i)
    return {"ok": True, "outcomes": outcomes, "completed": mode.completed,
            "site": mode.site}
