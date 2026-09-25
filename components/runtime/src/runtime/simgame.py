"""Deterministic in-memory game stub (feature 004; FR-309, T086;
extended for the unified phase engine, feature 017).

Pure state machine: state changes only through writes and
``advance(iteration)``, whose scripted evolution is a pure function of
(state, iteration) — repeated runs are bit-identical (SC-303) and no
endpoint is ever touched (FR-1420). Envelope grammar matches the bridge
(``{ok, result|error}``).

Two surfaces in one world:

- the v0 reflex surface (game.status, state.summary, state.pawns,
  ui.set_work, ui.job, ui.designate) plus the scripted fire/downed
  evolution used by the reflex tests;
- the colony surface the start-mode pack needs end-to-end (map.find /
  open_rects / cell, zones/rooms/stocks/steward, anchors, builds,
  bills, research, letters, saves) — mutation lag models colony labor:
  write effects land on the NEXT advance() so verify must observe,
  never assume.
"""

from __future__ import annotations

from copy import deepcopy

TEMPLATE_SURFACE = (
    "game.status", "game.list_saves", "game.save", "game.load",
    "state.summary", "state.pawns", "state.pawn", "state.storage",
    "state.rooms", "state.stocks", "state.base", "state.designations",
    "state.bills", "state.threats", "state.factions", "state.research",
    "state.letters",
    "map.find", "map.open_rects", "map.cell",
    "anchor.set",
    "steward.status", "steward.stock.set", "steward.stock.run",
    "steward.research",
    "ui.set_work", "ui.job", "ui.designate", "ui.zone", "ui.storage",
    "ui.build", "ui.build_many", "ui.add_bill", "ui.draft",
    "ui.attack", "ui.letter", "ui.set_research",
    "dev.incident", "dev.spawn_pawn", "dev.heal",
)


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
                {"id": "c3", "name": "Reyes", "downed": False},
            ],
        },
        "map": {"fires": 0, "fire_cell": None},
        "haul_cell": [3, 3],
        "priorities": {},
        "jobs": [],
        "designations": [],
    }


class SimGame:
    """Deterministic fake; call ``rpc`` for the template surface.

    ``established=True`` starts mid-colony (zones/rooms/beds/food/
    recreation already true) so runs can exercise post-init phases
    without replaying bootstrap.
    """

    def __init__(self, state: dict | None = None,
                 established: bool = False,
                 autosaves: list[str] | None = None) -> None:
        self._state = deepcopy(state) if state else default_state()
        members = self._state["colonists"]["members"]
        # colony world (the start-mode surface)
        self.colonists = len(members)
        self.items = [{"id": f"item-{i}", "pos": [25 + i % 3, 20 + i // 3]}
                      for i in range(6)] if not established else []
        self.forbidden = list(self.items)
        self.zones: list[dict] = []
        self.storage_full = False
        self.rooms: list[dict] = []
        self.blueprints: list[dict] = []
        self.roofed: set[tuple] = set()
        self.beds = 0
        self.food_source = False
        self.recreation = False
        self.traps = 0
        self.turbines = 0
        self.cookstations = 0
        self.bills: dict[str, list] = {}
        self.meals = 0
        self.anchors: dict[str, dict] = {}
        self.saves: dict[str, dict] = {}
        self._save_seq = 0                  # deterministic modified clock
        self._save_meta: dict[str, str] = {}
        self.hostiles: list[dict] = []
        self.drafted: set[str] = set()
        self.pawns = [{"id": m["id"], "name": m["name"],
                       "faction": "Player", "job": "Construct",
                       "weapon": None}
                      for m in members]
        self.skills = {"c1": {"Shooting": "8", "Melee": "1"},
                       "c2": {"Shooting": "1", "Melee": "7"},
                       "c3": {"Shooting": "3", "Melee": "3"}}
        self.weapons = [{"id": "w-gun", "def": "Gun_Revolver"},
                        {"id": "w-melee", "def": "MeleeWeapon_Gladius"}]
        self.armor = [{"id": "a-1", "def": "Apparel_FlakVest"}]
        self.fertility = {}
        self.stripped: list[str] = []
        self.zone_filters: dict[str, dict] = {}
        self.zone_plants: dict[str, str] = {}
        self.zone_rects: list[dict] = []
        self.terrain: dict[tuple, str] = {}
        self.flora = [
            {"id": "tree-1", "pos": [7, 4], "def": "TreeOak",
             "kind": "tree"},
            {"id": "tree-2", "pos": [9, 4], "def": "TreeOak",
             "kind": "tree"},
            {"id": "rock-1", "pos": [30, 30], "def": "ChunkGranite",
             "kind": "resource_rock"}]
        self.gens: list[dict] = []
        self.built: list[dict] = []
        self.benches = 0
        self.research = {"current": None,
                         "available": ["Battery", "SolarPanels"],
                         "finished": 0}
        self.letters: list[dict] = []
        self.stocks_nutrition = 0.0
        self.stock_jobs = [
            {"id": 3, "kind": "hunting", "target": 375, "current": 0,
             "suspended": False, "managed": True},
            {"id": 4, "kind": "hunting_leather", "target": 100,
             "current": 0, "suspended": False, "managed": True},
            {"id": 5, "kind": "mining", "target": 300, "current": 0,
             "suspended": False, "managed": True}]
        self.stock_runs: list[str] = []
        self._pending: list[str] = []
        self.writes: list[tuple] = []
        if established:
            self.zones = [{"label": "start.storage"},
                          {"label": "start.overflow"},
                          {"label": "growing", "plant": "Plant_Rice"}]
            self.rooms = [{"role": "Bedroom", "beds": 3, "problems": []},
                          {"role": "Bedroom", "beds": 0, "problems": []},
                          {"role": "Bedroom", "beds": 0, "problems": []}]
            self.beds = 3
            self.food_source = True
            self.recreation = True
            self.cookstations = 1
            self.bills = {"cs-0": ["CookMealSimple"]}
            self.meals = 2
            self.anchors = {"start.storage": {"min": [14, 14]}}
            self.roofed = {(14, 14)}
            for p in self.pawns:
                p["weapon"] = "w-gun"
                p["equipment"] = [{"id": "w-gun", "def": "Gun_Revolver"}]
            self.weapons = []
            self.armor = []
        for a in autosaves or []:
            self.sim_autosave(a)

    @property
    def current(self) -> dict:
        return deepcopy(self._state)

    def _downed(self, pid: str) -> bool:
        if any(m["id"] == pid and m.get("downed")
               for m in self._state["colonists"]["members"]):
            return True
        return any(h.get("id") == pid and h.get("downed")
                   for h in self.hostiles)

    def advance(self, iteration: int = 0) -> None:
        """Scripted deterministic evolution (pure function of
        state+iteration): pending write effects land (one-poll labor
        lag), then the legacy reflex script — iteration 1 fire starts,
        2 a colonist goes down, 3 both clear."""
        self._state["tick"] += 25
        self._state["day"] = self._state["tick"] // 60000
        for p in self._pending:
            if p == "unforbid":
                self.forbidden = []
            elif p == "haul":
                if not self.storage_full or any(
                        z.get("label") == "start.overflow"
                        for z in self.zones):
                    self.items = []
            elif p == "shelter":
                self.blueprints = []
                self.rooms = [{"role": "Bedroom", "beds": 0,
                               "problems": []}]
            elif p.startswith("roof:"):
                _, xy = p.split(":")
                x, z = (int(v) for v in xy.split(","))
                self.roofed.add((x, z))
            elif p == "bed":
                self.beds += 1
                self.built.append({"id": f"bed{self.beds}", "def": "Bed",
                                   "pos": [14, 14]})
                if self.rooms:
                    self.rooms[0]["beds"] = self.beds
            elif p == "food":
                self.food_source = True
            elif p == "cookstation":
                self.cookstations += 1
            elif p == "meal":
                if self.cookstations and self.bills and self.food_source:
                    self.meals += 1
            elif p == "attack":
                if self.hostiles:
                    self.hostiles.pop()
            elif p == "recreation":
                self.recreation = True
            elif p == "bench":
                self.benches += 1
            elif p == "trap":
                self.traps += 1
            elif p.startswith("turbine:"):
                _, xy = p.split(":", 1)
                x, z = (int(v) for v in xy.split(","))
                self.turbines += 1
                self.gens.append({"id": f"g{len(self.gens)}",
                                  "pos": [x, z], "def": "WindTurbine"})
            elif p.startswith("cut:"):
                ids = set(p[4:].split(","))
                self.flora = [f for f in self.flora
                              if f["id"] not in ids]
            elif p.startswith("furnish:"):
                _, d, xy = p.split(":", 2)
                self.built.append({"id": f"f{len(self.built)}", "def": d,
                                   "pos": [int(v) for v in xy.split(",")]})
            elif p.startswith("floor:"):
                _, d, rcs = p.split(":", 2)
                rx, rz, rw, rh = (int(v) for v in rcs.split(","))
                for cx in range(rx, rx + rw):
                    for cz in range(rz, rz + rh):
                        self.terrain[(cx, cz)] = d
        self._pending = []
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
            st = deepcopy(self._state)
            st["colonists"]["count"] = self.colonists
            return {"ok": True, "result": st}
        if method == "state.summary":
            return {"ok": True, "result": {
                "colonists": self.colonists,
                "downed": self._state["colonists"]["downed"],
                "colonist_list": [{"id": p["id"], "name": p["name"]}
                                  for p in self.pawns],
                "day": self._state["day"],
                "hour": self._state["tick"] // 2500}}
        if method == "state.pawns":
            return {"ok": True, "result": [
                {**p, "kind": "Colonist", "downed": self._downed(p["id"]),
                 "drafted": p["id"] in self.drafted}
                for p in self.pawns]}
        if method == "state.pawn":
            pid = params.get("pawn")
            prow = next((p for p in self.pawns if p["id"] == pid), {})
            return {"ok": True, "result": {
                "id": pid, "skills": self.skills.get(pid, {}),
                "drafted": pid in self.drafted,
                "downed": self._downed(pid),
                "equipment": list(prow.get("equipment") or []),
                "apparel": list(prow.get("apparel") or [])}}
        if method == "map.find" and params.get("def") == "Fire":
            fires = self._state["map"]["fires"]
            cell = self._state["map"].get("fire_cell")
            return {"ok": True, "result": {
                "count": fires,
                "things": [{"pos": cell}] * fires if cell else []}}
        if method == "map.find":
            if params.get("def") in ("Bed", "DoubleBed", "SleepingSpot",
                                     "DoubleSleepingSpot"):
                n = self.beds if params.get("def") == "Bed" else 0
                return {"ok": True, "result": {
                    "count": n, "things": [{"id": "b"}] * n}}
            if params.get("def") == "Plant_Rice":
                return {"ok": True, "result": {
                    "count": 1 if self.food_source else 0,
                    "things": []}}
            if params.get("def") in ("HorseshoesPin", "ChessTable",
                                     "Telescope"):
                n = 1 if self.recreation else 0
                return {"ok": True, "result": {
                    "count": n, "things": [{"id": "rec-1"}] * n}}
            if params.get("def") in ("Campfire", "FueledStove",
                                     "ElectricStove"):
                n = self.cookstations if params.get("def") == "Campfire" \
                    else 0
                return {"ok": True, "result": {
                    "count": n,
                    "things": [{"id": f"cs-{i}"} for i in range(n)]}}
            if params.get("def") in ("MealSimple", "MealFine",
                                     "MealLavish"):
                n = self.meals if params.get("def") == "MealSimple" else 0
                return {"ok": True, "result": {
                    "count": n, "things": [{"id": "m"}] * n}}
            if params.get("def") in ("SimpleResearchBench",
                                     "HiTechResearchBench"):
                return {"ok": True, "result": {
                    "count": self.benches,
                    "things": [{"id": "rb"}] * self.benches}}
            if params.get("def") == "TrapSpike":
                return {"ok": True, "result": {
                    "count": self.traps,
                    "things": [{"id": f"t{i}", "pos": [16, -2]}
                               for i in range(self.traps)]}}
            if params.get("def") in ("WindTurbine", "WoodFiredGenerator"):
                rows = [g for g in self.gens
                        if g["def"] == params.get("def")]
                return {"ok": True, "result": {
                    "count": len(rows), "things": list(rows)}}
            if params.get("kind") in ("tree", "harvestable",
                                      "resource_rock"):
                near = params.get("near") or [0, 0]
                rad = float(params.get("radius") or 9999)
                rows = [f for f in self.flora
                        if f["kind"] == params["kind"] and
                        ((f["pos"][0] - near[0]) ** 2
                         + (f["pos"][1] - near[1]) ** 2) ** 0.5 <= rad]
                return {"ok": True, "result": {
                    "count": len(rows), "things": list(rows)}}
            if params.get("def") == "Healroot":
                n = 1 if any(z.get("plant") == "Healroot"
                             for z in self.zones if isinstance(z, dict)) \
                        or "Healroot" in self.zone_plants.values() else 0
                return {"ok": True, "result": {
                    "count": n, "things": [{"id": "hr"}] * n}}
            wdef = params.get("def")
            wpool = ([t for t in self.weapons if t["def"] == wdef]
                     or [t for t in self.armor if t["def"] == wdef])
            if wpool:
                return {"ok": True, "result": {
                    "count": len(wpool), "things": list(wpool)}}
            if params.get("kind") == "building":
                return {"ok": True, "result": {
                    "count": len(self.built),
                    "things": list(self.built)}}
            if params.get("kind") == "blueprint":
                return {"ok": True, "result": {
                    "count": len(self.blueprints),
                    "things": list(self.blueprints)}}
            if params.get("def") is not None:
                rows = [b for b in self.built
                        if b.get("def") == params["def"]]
                return {"ok": True, "result": {
                    "count": len(rows), "things": list(rows)}}
            src = self.forbidden if params.get("forbidden") else self.items
            return {"ok": True, "result": {
                "count": len(src), "things": list(src)}}
        if method == "map.open_rects":
            if (params.get("w") or 9) > 9 or (params.get("h") or 9) > 9:
                return {"ok": True, "result": []}
            return {"ok": True, "result": [
                {"min": [60, 60]}, {"min": [14, 14]}, {"min": [30, 40]}]}
        if method == "map.cell":
            cell = tuple((params.get("cell") or [0, 0])[:2])
            zone = next((z["label"] for z in self.zone_rects
                         if z["rect"][0] <= cell[0] < z["rect"][0]
                            + z["rect"][2]
                         and z["rect"][1] <= cell[1] < z["rect"][1]
                            + z["rect"][3]), None)
            return {"ok": True, "result": {
                "roof": cell in self.roofed, "walkable": True,
                "fertility": self.fertility.get(cell, 1.0),
                "terrain": self.terrain.get(cell, "Soil"),
                "zone": zone}}
        if method == "state.storage":
            return {"ok": True, "result": list(self.zones)}
        if method == "state.rooms":
            return {"ok": True, "result": list(self.rooms)}
        if method == "state.stocks":
            return {"ok": True, "result": {
                "total": len(self.items), "counted": {},
                "nutrition": self.stocks_nutrition}}
        if method == "steward.status":
            return {"ok": True, "result": {
                "enabled": {"scorer": True, "stock": True},
                "pawns": [], "stock": [dict(j) for j in self.stock_jobs]}}
        if method == "steward.stock.set":
            row = next((j for j in self.stock_jobs
                        if j["kind"] == params.get("kind")
                        or j["id"] == params.get("id")), None)
            if row is None:
                return err("sim.no_stock", "no such stock job")
            for k in ("target", "suspended", "managed"):
                if k in params:
                    row[k] = params[k]
            return {"ok": True, "result": dict(row)}
        if method == "steward.stock.run":
            self.stock_runs.append(str(params.get("kind") or
                                       params.get("id")))
            return {"ok": True, "result": {"ran": True}}
        if method == "state.base":
            return {"ok": True, "result": {
                "rooms": list(self.rooms), "anchors": self.anchors}}
        if method == "state.designations":
            return {"ok": True, "result": {}}
        if method == "state.bills":
            return {"ok": True, "result": {
                "bills": [{"recipe": r}
                          for r in self.bills.get(params.get("thing"), [])]}}
        if method == "state.threats":
            return {"ok": True, "result": {
                "hostiles": list(self.hostiles),
                "home_center": [50, 50]}}
        if method == "game.list_saves":
            # bridge shape: [{name, modified}] — modified is a
            # deterministic monotonic tag (sim-tNNNNNN), not wall time
            return {"ok": True, "result": [
                {"name": n, "modified": self._save_meta.get(n)}
                for n in self.saves]}
        if method == "game.save":
            self.saves[params["name"]] = self._snapshot()
            self._save_seq += 1
            self._save_meta[params["name"]] = \
                f"sim-t{self._save_seq:06d}"
            return {"ok": True, "result": {"name": params["name"]}}
        if method == "game.load":
            snap = self.saves.get(params["name"])
            if snap is None:
                return err("sim.no_save", "no such save")
            for k, v in deepcopy(snap).items():
                setattr(self, k, v)
            return {"ok": True, "result": {"name": params["name"]}}
        # ---- writes ----
        if method == "anchor.set":
            self.anchors[params["name"]] = {"min": params.get("cell"),
                                            "rect": params.get("rect")}
            return {"ok": True, "result": {"name": params["name"]}}
        if method == "ui.set_work":
            pawn, priorities = params.get("pawn"), params.get("priorities")
            if not isinstance(pawn, str) or not isinstance(priorities, dict):
                return err("sim.params_invalid",
                           "ui.set_work needs {pawn, priorities}")
            self._state["priorities"][pawn] = dict(priorities)
            return {"ok": True, "result": {"applied": True,
                                           "pawn": pawn,
                                           "priorities": dict(priorities)}}
        if method == "ui.zone":
            if params.get("rect"):
                self.zone_rects.append({"label": params.get("label", "z"),
                                        "rect": list(params["rect"])})
            if params.get("action") == "create_stockpile":
                self.zones.append({"label": params.get("label", "z")})
                return {"ok": True, "result": {"zone": params.get("label")}}
            if params.get("action") == "create_growing":
                self.zones.append({"label": params.get("label", "growing"),
                                   "plant": params.get("plant")})
                self._pending.append("food")
                return {"ok": True, "result": {"zone": "growing"}}
            if params.get("action") == "set_plant":
                self.zone_plants[params.get("label")] = params.get("plant")
                return {"ok": True, "result": {"plant": params.get("plant")}}
            return {"ok": True, "result": {"zone": params.get("label")}}
        if method == "ui.storage":
            self.zone_filters[params.get("zone")] = dict(params)
            return {"ok": True, "result": {"zone": params.get("zone")}}
        if method == "ui.designate":
            d = params.get("designator")
            handled = ("forbid", "unforbid", "haul", "strip",
                       "Designator_AreaBuildRoof", "cut", "harvest")
            if d not in handled:
                return err("sim.params_invalid",
                           f"unsupported designator {d!r}")
            self._state["designations"].append({
                "designator": d, "cells": params.get("cells"),
                "things": params.get("things")})
            if d == "unforbid":
                self._pending.append("unforbid")
            elif d == "haul":
                self._pending.append("haul")
            elif d == "strip":
                self.stripped.extend(params.get("things") or [])
            elif d == "Designator_AreaBuildRoof":
                rect = params.get("rect") or [0, 0, 0, 0]
                self._pending.append(f"roof:{rect[0]},{rect[1]}")
            elif d in ("cut", "harvest"):
                ids = set(params.get("things") or [])
                for c in params.get("cells") or []:
                    ids.update(f["id"] for f in self.flora
                               if list(f["pos"][:2]) == list(c[:2]))
                r = params.get("rect")
                if r:
                    ids.update(f["id"] for f in self.flora
                               if r[0] <= f["pos"][0] < r[0] + r[2]
                               and r[1] <= f["pos"][1] < r[1] + r[3])
                self._pending.append("cut:" + ",".join(sorted(ids)))
            return {"ok": True, "result": {"applied": True}}
        if method == "ui.build_many":
            self.blueprints.extend({"pos": [14, 14]} for _ in
                                   params.get("ops", []))
            self._pending.append("shelter")
            return {"ok": True, "result": {"placed": 2, "failed": []}}
        if method == "ui.build":
            if params.get("dry_run"):
                return {"ok": True, "result": {"placed": [params.get("at")],
                                               "failed": []}}
            if params.get("rect") and params.get("fill"):
                r = params["rect"]
                self._pending.append(
                    f"floor:{params.get('def')}:"
                    + ",".join(str(v) for v in r))
                return {"ok": True, "result": {"placed": r[2] * r[3]}}
            if params.get("def") == "Bed":
                self._pending.append("bed")
            elif params.get("def") == "HorseshoesPin":
                self._pending.append("recreation")
            elif params.get("def") in ("SimpleResearchBench",
                                       "HiTechResearchBench"):
                self._pending.append("bench")
            elif params.get("def") in ("Campfire", "FueledStove",
                                       "ElectricStove"):
                self._pending.append("cookstation")
            elif params.get("def") == "TrapSpike":
                self._pending.append("trap")
            elif params.get("def") in ("WindTurbine", "WoodFiredGenerator"):
                self._pending.append(
                    "turbine:" + ",".join(
                        str(v) for v in (params.get("at") or [0, 0])[:2]))
            else:
                self._pending.append(
                    "furnish:" + str(params.get("def")) + ":"
                    + ",".join(
                        str(v) for v in (params.get("at") or [0, 0])[:2]))
            return {"ok": True, "result": {"placed": 1}}
        if method == "ui.add_bill":
            self.bills.setdefault(params["thing"], []).append(
                params["recipe"])
            self._pending.append("meal")
            return {"ok": True, "result": {"bill": params["recipe"]}}
        if method == "dev.incident":
            for _i in range(2):
                self.hostiles.append(
                    {"id": f"raider-{len(self.hostiles)}", "kind": "Pirate",
                     "pos": [20 + len(self.hostiles), 20],
                     "dist_home": 40})
            return {"ok": True, "result": {"fired": params.get("def")}}
        if method == "dev.spawn_pawn":
            self.hostiles.append(
                {"id": f"pawn-{len(self.hostiles)}",
                 "kind": params.get("kind"),
                 "faction": params.get("faction"),
                 "pos": [20 + len(self.hostiles), 20],
                 "dist_home": 40})
            return {"ok": True,
                    "result": [{"id": self.hostiles[-1]["id"]}]}
        if method == "state.factions":
            return {"ok": True, "result": [
                {"name": "Hostiles", "hostile": True, "defeated": False}]}
        if method == "dev.heal":
            return {"ok": True, "result": {"healed": params.get("pawn")}}
        if method == "ui.draft":
            (self.drafted.add if params.get("drafted")
             else self.drafted.discard)(params.get("pawn"))
            return {"ok": True, "result": {"drafted": params["drafted"]}}
        if method == "ui.attack":
            self._pending.append("attack")
            return {"ok": True, "result": {"engaged": params.get("target")}}
        if method == "ui.job":
            pawn, job = params.get("pawn"), params.get("job")
            if not isinstance(pawn, str) or not isinstance(job, str):
                return err("sim.params_invalid", "ui.job needs {pawn, job}")
            self._state["jobs"].append({"pawn": pawn, "job": job,
                                        "target": params.get("target")})
            prow = next((p for p in self.pawns if p["id"] == pawn), None)
            if job == "Equip" and prow is not None:
                target = params.get("target")
                # the equipped thing leaves the loose pool and becomes
                # the pawn's equipment — Equip auto-drops the old weapon
                old = (prow.get("equipment") or [None])[0]
                if old:
                    self.weapons.append(old)
                thing = next((w for w in self.weapons
                              if w["id"] == target),
                             {"id": target})
                prow["weapon"] = target
                prow["equipment"] = [thing]
                self.weapons = [w for w in self.weapons
                                if w["id"] != target]
            elif job == "Wear" and prow is not None:
                target = params.get("target")
                thing = next((a for a in self.armor
                              if a["id"] == target),
                             {"id": target})
                prow.setdefault("apparel", []).append(thing)
                self.armor = [a for a in self.armor
                              if a["id"] != target]
            elif prow is not None:
                prow["job"] = job
            return {"ok": True, "result": {"applied": True,
                                           "job": self._state["jobs"][-1]}}
        if method == "state.research":
            return {"ok": True, "result": dict(self.research)}
        if method == "ui.set_research":
            self.research["current"] = params.get("def")
            return {"ok": True,
                    "result": {"current": params.get("def")}}
        if method == "steward.research":
            q = [p for p in (params.get("queue") or [])
                 if p in self.research["available"]]
            if params.get("append"):
                self.research.setdefault("queue", [])
                self.research["queue"] += q
            else:
                self.research["queue"] = q
            if not self.research.get("current"):
                self.research["current"] = next(
                    iter(self.research.get("queue") or []), None)
            return {"ok": True, "result": {
                "queue": self.research.get("queue"),
                "current": self.research.get("current")}}
        if method == "game.pause":
            self._state["paused"] = bool(params.get("paused"))
            return {"ok": True, "result": {"paused":
                                           self._state["paused"]}}
        if method == "game.speed":
            self._state["speed"] = int(params.get("speed") or 0)
            self._state["paused"] = self._state["speed"] == 0
            return {"ok": True, "result": {"speed": self._state["speed"]}}
        if method == "state.letters":
            return {"ok": True, "result": list(self.letters)}
        if method == "ui.letter":
            self.letters = [l for l in self.letters
                            if l.get("id") != params.get("id")]
            return {"ok": True, "result": {"answered": params.get("id")}}
        return err("sim.unknown_method", f"method '{method}' not simulated")

    def _snapshot(self) -> dict:
        return deepcopy({
            "items": self.items, "forbidden": self.forbidden,
            "zones": self.zones, "rooms": self.rooms,
            "blueprints": self.blueprints, "roofed": self.roofed,
            "beds": self.beds, "food_source": self.food_source,
            "recreation": self.recreation, "traps": self.traps,
            "turbines": self.turbines,
            "cookstations": self.cookstations, "bills": self.bills,
            "meals": self.meals, "anchors": self.anchors,
            "stock_jobs": self.stock_jobs,
            "hostiles": [], "drafted": set()})

    def sim_autosave(self, name: str) -> None:
        """Test hook (feature 021): register a loadable autosave row —
        snapshots the colony surface and bumps the deterministic
        `modified` clock so 'nearest day start' ordering is testable."""
        self.saves[name] = self._snapshot()
        self._save_seq += 1
        self._save_meta[name] = f"sim-t{self._save_seq:06d}"
