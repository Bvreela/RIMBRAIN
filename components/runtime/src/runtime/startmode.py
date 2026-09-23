"""Start-mode driver (feature 008; FR-701..709).

Deterministic fresh-start bootstrap over the TaskLedger:

    site -> zone -> unforbid -> shelter -> roof -> haul -> baseline loop
    (beds / food source / recreation) -> start.completed -> disengage

Every phase is a ledger task whose effect spec is verified against
OBSERVED state (never dispatch ok). Site selection is deterministic
scoring of map.open_rects by pack-declared weights — no model places
structures. Engages only when the caller wires it (--mode start).
"""

from __future__ import annotations

import json
from pathlib import Path

from .dispatch import _dotted, _op_holds
from .planloop import observe
from .store import write_atomic

BOOTSTRAP = ["site", "zone", "unforbid", "shelter", "roof", "haul"]
BASELINE = ["beds", "food", "recreation"]


def observe_start(game, cfg: dict | None = None) -> dict:
    """Start-mode observation: enriched state + storage/rooms/stocks/base +
    loose+forbidden items + blueprints + open rects + food/recreation flags
    (per pack defs). Missing rpcs degrade to empty — effect checks then read
    as inconclusive (fail-closed)."""
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
    # food/recreation flags from observed zones/things (cfg-declared defs)
    cfg = cfg or {}
    zones = obs.get("storage") or []
    if isinstance(zones, dict):
        zones = zones.get("zones") or zones.get("stockpiles") or []
    obs["zones_growing"] = sum(
        1 for z in zones if isinstance(z, dict)
        and (z.get("plant") or "grow" in str(z.get("label", "")).lower()))
    for d in (cfg.get("recreation", {}) or {}).get("defs", ["HorseshoesPin"]):
        r = game.rpc("map.find", {"def": d})
        if r.get("ok") and (r.get("result") or {}).get("count", 0) > 0:
            obs["recreation_present"] = True
            break
    obs.setdefault("recreation_present", False)
    obs["food_source_present"] = obs["zones_growing"] > 0
    return obs


def _things(res: dict) -> list:
    t = res.get("things") if isinstance(res, dict) else None
    return t if isinstance(t, list) else []


def rank_site(obs: dict, cfg: dict) -> dict | None:
    """Score open rects by pack weights: nearer the item cluster and home
    center wins. Deterministic — same obs => same site."""
    rects = obs.get("open_rects") or []
    if isinstance(rects, dict):
        rects = rects.get("rects") or []
    if not rects:
        return None
    items = _things(obs.get("items") or {})
    if items:
        cx = sum(t.get("pos", [0, 0])[0] for t in items) / len(items)
        cz = sum(t.get("pos", [0, 0])[1] for t in items) / len(items)
    else:
        cx, cz = 0, 0
    home = obs.get("home_center")
    if not isinstance(home, (list, tuple)) or len(home) < 2:
        home = [cx, cz]
    w = cfg.get("weights") or {}
    wi, wh = w.get("items_proximity", 2.0), w.get("home_proximity", 1.0)

    def _cell(rect):
        if isinstance(rect, dict):
            return rect.get("min") or rect.get("cell") or [0, 0]
        return rect

    def score(rect) -> float:
        cell = _cell(rect)
        x, z = cell[0], cell[1]
        return wi * -((x - cx) ** 2 + (z - cz) ** 2) ** 0.5 \
            + wh * -((x - home[0]) ** 2 + (z - home[1]) ** 2) ** 0.5

    best = max(rects, key=score)
    cell = _cell(best)
    sc = cfg.get("site", {})
    w_, h_ = sc.get("zone_w", 9), sc.get("zone_h", 9)
    return {"min": list(cell)[:2], "rect": [cell[0], cell[1], w_, h_],
            "score": score(best)}


def exit_eval(obs: dict, cfg: dict, colonists: int) -> dict:
    """Per-colonist baseline check (FR-705). Returns the four condition
    booleans + complete flag. Reads normalized obs fields; missing data
    counts as not-held (fail-closed)."""
    rooms = obs.get("rooms") or []
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms") or []
    enclosed = sum(1 for r in rooms
                   if isinstance(r, dict)
                   and not (r.get("problems") or []))
    base = obs.get("base") or {}
    if isinstance(base, dict) and base.get("rooms"):
        brooms = [r for r in base["rooms"]
                  if not (r.get("problems") or [])]
        enclosed = max(enclosed, len(brooms))
    beds = 0
    for r in rooms:
        if isinstance(r, dict):
            beds += int(r.get("beds", 0) or 0)
    beds = max(beds, int(obs.get("beds_in_rooms", 0) or 0))
    food = bool(obs.get("food_source_present"))
    if not food:
        # growing zone or planted cells or a steward stock job count
        food = bool((obs.get("zones_growing") or 0) > 0
                    or (obs.get("steward_food_job")))
    rec = bool(obs.get("recreation_present"))
    cond = {
        "shelter": enclosed >= 1,  # a barracks counts; beds-in-room covers per-colonist
        "beds": beds >= colonists,
        "food": food,
        "recreation": rec,
    }
    return {**cond, "complete": all(cond.values()),
            "enclosed_rooms": enclosed, "beds_count": beds}


class StartMode:
    """Drives the bootstrap graph + baseline loop through the ledger."""

    def __init__(self, pack_cfg: dict, ledger, *,
                 sink=None, clock=None):
        self.cfg = pack_cfg
        self.ledger = ledger
        self._sink = sink
        self._clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self.completed = False
        self._mode_path = ledger._path.parent / "startmode.json"
        self.site: dict | None = None
        if self._mode_path.is_file():
            try:
                saved = json.loads(self._mode_path.read_text())
                self.site = saved.get("site")
                self.completed = bool(saved.get("completed"))
            except (json.JSONDecodeError, OSError):
                pass  # corrupt mode file -> re-derive from observation

    def _save_mode(self) -> None:
        write_atomic(self._mode_path, json.dumps(
            {"site": self.site, "completed": self.completed},
            sort_keys=True).encode() + b"\n")

    # -- phase plumbing --------------------------------------------------------

    def _tid(self, phase: str) -> str:
        return f"start.{phase}"

    def _propose(self, phase: str, effect: dict, resources: list,
                 tick: int) -> None:
        self.ledger.propose({
            "task_id": self._tid(phase), "kind": f"start.{phase}",
            "action": {"template_id": None, "params": {}},
            "resources": resources, "effect": effect,
            "lease_ticks": 200, "max_attempts": 3}, tick=tick)

    def _phase_effect(self, phase: str, obs: dict) -> dict:
        """Effect spec for a phase, with dynamic values (beds per colonist)."""
        eff = dict(self._effect_of(phase))
        if phase == "beds":
            col = obs.get("colonists")
            eff["value"] = (col.get("count", 1)
                            if isinstance(col, dict) else col or 1)
        return eff

    def _effect_of(self, phase: str) -> dict:
        """Declared effect spec per phase (verified on obs, never on ok)."""
        return {
            "site": {"field": "anchors.start", "op": "ne", "value": None},
            "zone": {"field": "zone_count", "op": "gte", "value": 1},
            "unforbid": {"field": "forbidden.count", "op": "eq", "value": 0},
            "shelter": {"field": "room_count", "op": "gte", "value": 1},
            "roof": {"field": "roofed_count", "op": "gte", "value": 1},
            "haul": {"field": "items.count", "op": "eq", "value": 0},
            "beds": {"field": "beds_total", "op": "gte", "value": 1},
            "food": {"field": "food_source_present", "op": "eq",
                     "value": True},
            "recreation": {"field": "recreation_present", "op": "eq",
                           "value": True},
        }[phase]

    def _dispatch(self, dispatcher, phase: str, obs: dict) -> dict:
        """Phase-specific write through the single writer. Params are computed
        here from obs + pack cfg — the pack declares the template/method, the
        mode supplies observed values."""
        cfg = self.cfg
        if phase == "site":
            site = rank_site(obs, cfg.get("site", {}))
            if site is None:
                return {"ok": False, "error": {"code": "start.no_site"}}
            self.site = site
            self._save_mode()
            return dispatcher.dispatch("set-anchor", {
                "name": cfg["site"].get("anchor_name", "start.storage"),
                "cell": site["min"], "rect": site["rect"]})
        if phase == "zone":
            return dispatcher.dispatch("create-stockpile", {
                "action": "create_stockpile",
                "label": cfg["site"].get("anchor_name", "start.storage"),
                "rect": self.site["rect"]})
        if phase == "unforbid":
            ids = [t.get("id") for t in _things(obs.get("forbidden") or {})
                   if t.get("id")]
            if not ids:
                return {"ok": True, "result": {"things": []}}
            return dispatcher.dispatch("unforbid-items", {
                "designator": "unforbid", "things": ids})
        if phase == "shelter":
            s = cfg.get("shelter", {})
            x, z = self.site["min"]
            w, h = s.get("room_w", 5), s.get("room_h", 5)
            stuff = (s.get("stuff_preference") or ["Wood"])[0]
            ops = [
                {"def": s.get("wall_def", "Wall"),
                 "rect": [x, z, w, h], "stuff": stuff},
                {"def": s.get("door_def", "Door"),
                 "at": [x + w // 2, z], "stuff": stuff},
            ]
            return dispatcher.dispatch("build-layout",
                                       {"ops": ops, "stop_on_error": False})
        if phase == "roof":
            return dispatcher.dispatch("roof-rect", {
                "designator": "Designator_Roof",
                "rect": self.site["rect"]})
        if phase == "haul":
            ids = [t.get("id") for t in _things(obs.get("items") or {})
                   if t.get("id")]
            if not ids:
                return {"ok": True, "result": {"things": []}}
            return dispatcher.dispatch("haul-items", {
                "designator": "haul", "things": ids})
        # baseline phases
        if phase == "beds":
            s = cfg.get("shelter", {})
            x, z = self.site["min"]
            return dispatcher.dispatch("build-one", {
                "def": s.get("bed_def", "Bed"),
                "at": [x + 1, z + 1],
                "stuff": (s.get("stuff_preference") or ["Wood"])[0]})
        if phase == "food":
            f = cfg.get("food", {})
            x, z = self.site["min"]
            return dispatcher.dispatch("create-growing", {
                "action": "create_growing",
                "rect": [x - f.get("zone_w", 7) - 1, z,
                         f.get("zone_w", 7), f.get("zone_h", 7)],
                "plant": f.get("plant", "Plant_Rice")})
        if phase == "recreation":
            x, z = self.site["min"]
            return dispatcher.dispatch("build-one", {
                "def": (cfg.get("recreation", {}).get("defs")
                        or ["HorseshoesPin"])[0],
                "at": [x - 1, z + 1]})
        return {"ok": False, "error": {"code": "start.unknown_phase"}}

    # -- main step -------------------------------------------------------------

    def step(self, dispatcher, game, obs: dict, tick: int) -> dict:
        """One poll of start-mode progression AFTER reflexes (caller order:
        observe -> reconcile -> reflex -> step). Returns an outcome dict."""
        storage = obs.get("storage")
        obs.setdefault("zone_count",
                       len(storage) if isinstance(storage, list)
                       else len(_things(storage or {})))
        obs.setdefault("anchors", {})
        phases = BOOTSTRAP + BASELINE
        # sequential graph: current phase = first not terminal
        for phase in phases:
            tid = self._tid(phase)
            task = self.ledger.tasks.get(tid)
            if task and task.get("state") in ("succeeded", "failed",
                                              "expired"):
                continue
            if task is None:
                if phase == "site" or self.site is not None:
                    self._propose(phase, self._phase_effect(phase, obs),
                                  ["site:anchor"] if phase == "site" else [],
                                  tick)
                    task = self.ledger.tasks[tid]
                else:
                    return {"phase": phase, "state": "blocked",
                            "reason": "no_site"}
            st = task["state"]
            self._inject(obs, phase, game)
            if st == "proposed":
                # established-colony skip: effect already holds -> no write
                if self.ledger._check_effect(task, obs) is True:
                    self.ledger.acquire(tid, tick)
                    self.ledger._transition(tid, "dispatched",
                                            "skipped_effect_present", tick)
                    self.ledger.verify(tid, obs, tick)
                    continue
                self.ledger.acquire(tid, tick)
                st = task["state"]
            if st == "locked":
                if self.ledger._check_effect(task, obs) is True:
                    self.ledger._transition(tid, "dispatched",
                                            "skipped_effect_present", tick)
                    st = task["state"]
                else:
                    res = self._dispatch(dispatcher, phase, obs)
                    self.ledger.mark_dispatched(
                        tid, ok=bool(res.get("ok")), tick=tick)
                    st = task["state"]
                    if not res.get("ok"):
                        return {"phase": phase, "state": st,
                                "error": res.get("error", {}).get("code")}
            if st in ("dispatched", "verifying"):
                # repeat-dispatch phases (beds): while the effect is absent
                # keep issuing the unit build — the verifier still decides
                if phase in ("beds",) and \
                        self.ledger._check_effect(task, obs) is False:
                    self._dispatch(dispatcher, phase, obs)
                v = self.ledger.verify(tid, obs, tick)
                return {"phase": phase, "state": task["state"],
                        "verdict": v.get("verdict", "transitioned")}
            return {"phase": phase, "state": st}
        # all phases terminal: exit evaluation
        colonists = int(obs.get("colonists", {}).get("count", 0)
                        if isinstance(obs.get("colonists"), dict)
                        else obs.get("colonists") or 0)
        ev = exit_eval(obs, self.cfg, max(colonists, 1))
        if ev["complete"] and not self.completed:
            self.completed = True
            self._save_mode()
            return {"phase": "exit", "state": "completed", "eval": ev}
        # unmet baseline condition -> re-propose that phase (terminal ids
        # may be re-proposed; the new lineage restarts its attempts budget)
        for phase, flag in (("beds", "beds"), ("food", "food"),
                            ("recreation", "recreation")):
            if not ev.get(flag):
                tid = self._tid(phase)
                if self.ledger.tasks.get(tid, {}).get("state") in \
                        ("succeeded", "failed", "expired"):
                    self._propose(phase, self._phase_effect(phase, obs),
                                  [], tick)
                break
        return {"phase": "baseline", "state": "waiting", "eval": ev}

    def _inject(self, obs: dict, phase: str, game=None) -> None:
        """Normalize obs fields the effect specs read (fail-closed)."""
        if phase == "site":
            obs.setdefault("anchors", {})
            if self.site is not None:
                obs["anchors"]["start"] = self.site["min"]
        elif phase == "unforbid":
            obs.setdefault("forbidden", {})
            obs["forbidden"]["count"] = len(
                _things(obs.get("forbidden") or {}))
        elif phase == "shelter":
            rooms = obs.get("rooms") or []
            if isinstance(rooms, dict):
                rooms = rooms.get("rooms") or []
            obs["room_count"] = len(rooms)
        elif phase == "roof":
            # roofed cells are sampled at the site corner via map.cell when
            # the game is available; absent evidence stays 0 (inconclusive
            # would stall forever — a missing roof read counts as unroofed)
            obs.setdefault("roofed_count", 0)
            if game is not None and self.site is not None:
                r = game.rpc("map.cell", {"cell": self.site["min"]})
                res = r.get("result") if r.get("ok") else None
                if isinstance(res, dict) and res.get("roof"):
                    obs["roofed_count"] = 1
        elif phase == "haul":
            obs.setdefault("items", {})
            obs["items"]["count"] = len(_things(obs.get("items") or {}))
        elif phase in BASELINE:
            flags = exit_eval(obs, self.cfg, 1)
            obs["beds_total"] = flags["beds_count"]
            obs["food_source_present"] = flags["food"]
            obs["recreation_present"] = flags["recreation"]

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
                "conditions": {k: bool(ev[k]) for k in
                               ("shelter", "beds", "food", "recreation")},
                "phases_completed": BOOTSTRAP + BASELINE,
            },
            "privacy": {"classification": "internal", "redactions": []},
        }


def run_start(dispatcher, game, ledger, cfg: dict, *,
              iterations: int = 12, sink=None, clock=None) -> dict:
    """Drive Start Mode: observe -> reconcile -> reflex -> phase step.

    Spine order holds (reconcile precedes attend; emergencies precede all
    start work). Returns when start.completed emits, iterations exhaust,
    or a phase hard-fails.
    """
    mode = StartMode(cfg, ledger, sink=sink, clock=clock)
    outcomes = []
    seq = max(ledger._events, getattr(dispatcher, "_events", 0))
    for i in range(iterations):
        obs = observe_start(game, cfg)
        tick = obs.get("tick") or i
        ledger.reconcile(obs, tick)
        dispatcher.reflex(obs)
        out = mode.step(dispatcher, game, obs, tick)
        outcomes.append({"iteration": i, **out})
        if out.get("state") == "completed":
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
