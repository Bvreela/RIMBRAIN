"""Start-mode tests (feature 008; FR-701..709, SC-701..705).

StartSim models a fresh-map rpc surface: drop-pile items, open rects,
no zones/rooms/stocks. Writes mutate it deterministically on advance()
so phase effects verify only when the world actually changes.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.startmode import StartMode, observe_start, \
    run_start  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402
from runtime import policy  # noqa: E402


class StartSim:
    """Fresh map: 3 colonists, drop pile at [20,20], no structures.

    Mutation lag models colony labor: unforbid/haul/blueprint effects land
    on the NEXT advance() — verify must observe, never assume.
    """

    def __init__(self, established: bool = False):
        self.tick = 0
        self.colonists = 3
        self.items = [{"id": f"item-{i}", "pos": [25 + i % 3, 20 + i // 3]}
                      for i in range(6)] if not established else []
        self.forbidden = list(self.items)
        self.zones: list[dict] = []
        self.storage_full = False  # stockpile can't sink items
        self.rooms: list[dict] = []
        self.blueprints: list[dict] = []
        self.roofed: set[tuple] = set()
        self.beds = 0
        self.food_source = False
        self.recreation = False
        self.traps = 0                 # spike traps built
        self.turbines = 0              # generators built
        self.cookstations = 0          # built cooking stations
        self.bills: dict[str, list] = {}   # station id -> recipes
        self.meals = 0                 # MealSimple count on the map
        self.anchors: dict[str, dict] = {}
        self.saves: dict[str, dict] = {}   # name -> state snapshot
        self.hostiles: list[dict] = []     # live hostile pawns
        self.drafted: set[str] = set()
        # colonists with jobs/skills (universal idle rule + arming)
        self.pawns = [{"id": f"c{i}", "name": f"P{i}", "faction": "Player",
                       "job": "Construct", "weapon": None}
                      for i in range(3)]
        self.skills = {"c0": {"Shooting": "8", "Melee": "1"},
                       "c1": {"Shooting": "1", "Melee": "7"},
                       "c2": {"Shooting": "3", "Melee": "3"}}
        self.weapons = [{"id": "w-gun", "def": "Gun_Revolver"},
                        {"id": "w-melee", "def": "MeleeWeapon_Gladius"}]
        self.armor = [{"id": "a-1", "def": "Apparel_FlakVest"}]
        self.fertility = {}              # (x,z) -> float; default 1.0
        self.stripped: list[str] = []
        self.zone_filters: dict[str, dict] = {}
        self.zone_plants: dict[str, str] = {}
        self.zone_rects: list[dict] = []   # {label, rect} for map.cell zone
        self.terrain: dict[tuple, str] = {}  # cell -> terrain def
        self.flora = [                     # trees blocking the power strip
            {"id": "tree-1", "pos": [7, 4], "def": "TreeOak",
             "kind": "tree"},
            {"id": "tree-2", "pos": [9, 4], "def": "TreeOak",
             "kind": "tree"},
            {"id": "rock-1", "pos": [30, 30], "def": "ChunkGranite",
             "kind": "resource_rock"}]
        self.gens: list[dict] = []         # built generators {id,pos,def}
        self.built: list[dict] = []        # furnished buildings {id,def,pos}
        self.benches = 0               # research benches built
        self.research = {"current": None,
                         "available": ["Battery", "SolarPanels"],
                         "finished": 0}
        self.letters: list[dict] = []  # pending letters {id, choices}
        self.stocks_nutrition = 0.0    # state.stocks nutrition runway
        self.stock_jobs = [            # steward.status stock rows
            {"id": 3, "kind": "hunting", "target": 375, "current": 0,
             "suspended": False, "managed": True},
            {"id": 4, "kind": "hunting_leather", "target": 100,
             "current": 0, "suspended": False, "managed": True},
            {"id": 5, "kind": "mining", "target": 300, "current": 0,
             "suspended": False, "managed": True}]
        self.stock_runs: list[str] = []  # steward.stock.run kinds
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
            self.roofed = {(14, 14)}  # zone is already roofed
            for p in self.pawns:      # established colony is already armed
                p["weapon"] = "w-gun"
            self.weapons = []         # no loose weapons left to equip
            self.armor = []

    def rpc(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        if method == "game.status":
            return {"ok": True, "result": {
                "tick": self.tick, "colonists": {"count": self.colonists},
                "paused": False, "map": {"fires": 0}}}
        if method == "state.summary":
            return {"ok": True, "result": {
                "colonist_list": [{"id": f"c{i}", "name": f"P{i}"}
                                  for i in range(self.colonists)],
                "downed": 0}}
        if method == "map.find" and (params or {}).get("def") == "Fire":
            return {"ok": True, "result": {"count": 0, "things": []}}
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
                    # pos inside the compound trap-hallway rect so
                    # find_defs_in(trap_defs, hall) verifies
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
            # sim world only has ~9x9 open patches — footprint-size
            # searches come back empty and the runtime falls back
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
                return {"ok": False, "error": {"code": "sim.no_stock"}}
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
            return {"ok": True, "result": [
                {"name": n} for n in self.saves]}
        if method == "game.save":
            import copy
            self.saves[params["name"]] = copy.deepcopy({
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
            return {"ok": True, "result": {"name": params["name"]}}
        if method == "game.load":
            snap = self.saves.get(params["name"])
            if snap is None:
                return {"ok": False, "error": {"code": "sim.no_save"}}
            import copy
            s = copy.deepcopy(snap)
            for k, v in s.items():
                setattr(self, k, v)
            return {"ok": True, "result": {"name": params["name"]}}
        # ---- writes ----
        if method == "anchor.set":
            self.anchors[params["name"]] = {"min": params.get("cell"),
                                            "rect": params.get("rect")}
            return {"ok": True, "result": {"name": params["name"]}}
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
        if method == "ui.storage":
            self.zone_filters[params.get("zone")] = dict(params)
            return {"ok": True, "result": {"zone": params.get("zone")}}
        if method == "ui.designate":
            d = params.get("designator")
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
            if params.get("dry_run"):  # feasibility probe — no designation
                return {"ok": True, "result": {"placed": [params.get("at")],
                                               "failed": []}}
            if params.get("rect") and params.get("fill"):
                r = params["rect"]
                self._pending.append(
                    f"floor:{params.get('def')}:{','.join(str(v) for v in r)}")
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
            for i in range(2):
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
            job = params.get("job")
            pawn = next((p for p in self.pawns
                         if p["id"] == params.get("pawn")), None)
            if job == "Equip" and pawn is not None:
                pawn["weapon"] = params.get("target")
                self.weapons = [w for w in self.weapons
                                if w["id"] != params.get("target")]
            elif job == "Wear" and pawn is not None:
                pawn.setdefault("apparel", []).append(
                    params.get("target"))
                self.armor = [a for a in self.armor
                              if a["id"] != params.get("target")]
            elif pawn is not None:
                pawn["job"] = job  # fallback idle-correction jobs land here
            return {"ok": True, "result": {"applied": True}}
        if method == "state.pawns":
            return {"ok": True, "result": [
                {**p, "drafted": p["id"] in self.drafted}
                for p in self.pawns]}
        if method == "state.pawn":
            pid = params.get("pawn")
            return {"ok": True, "result": {
                "id": pid,
                "skills": self.skills.get(pid, {}),
                "drafted": pid in self.drafted,
                "downed": any(h.get("id") == pid and h.get("downed")
                              for h in self.hostiles)}}
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
        if method == "state.letters":
            return {"ok": True, "result": list(self.letters)}
        if method == "ui.letter":
            self.letters = [l for l in self.letters
                            if l.get("id") != params.get("id")]
            return {"ok": True, "result": {"answered": params.get("id")}}
        return {"ok": False, "error": {"code": "sim.unknown",
                                       "message": method}}

    def advance(self, iteration: int = 0) -> None:
        self.tick += 25
        for p in self._pending:
            if p == "unforbid":
                self.forbidden = []
            elif p == "haul":
                # a full stockpile stalls hauling until a second zone
                # exists (the haul escalate creates start.overflow)
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
                # pawns cook once station+bill exist and food is afoot
                if self.cookstations and self.bills and self.food_source:
                    self.meals += 1
            elif p == "attack":
                if self.hostiles:
                    self.hostiles.pop()  # drafted colonists win
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


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    cfg = d.pack["pack"]
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, cfg, events


def test_full_bootstrap_to_completed(rig):
    """SC-701: ordered trace site->...->baseline -> start.completed."""
    d, game, ledger, cfg, events = rig
    res = run_start(d, game, ledger, cfg, iterations=30)
    assert res["completed"]
    assert res["site"]["min"] == [14, 14]  # nearest the item cluster
    phases = [t for t in ledger.tasks.values()]
    assert all(t["state"] == "succeeded" for t in phases)
    assert len(phases) == 13  # 6 bootstrap + 7 baseline (arm..overflow)
    types = [e["event_type"] for e in events]
    assert "start.completed" in types
    assert types.index("start.completed") == len(types) - 1


def test_hold_governs_after_completed(rig):
    """UR-RUN-009: hold=True keeps polling past start.completed —
    standing goals dispatch/verify, and a lapsed effect re-arms."""
    d, game, ledger, cfg, events = rig
    game.letters = [{"id": "l-quest", "choices": ["Accept", "Reject"]}]
    res = run_start(d, game, ledger, cfg, iterations=60, hold=True)
    assert res["completed"]
    types = [e["event_type"] for e in events]
    assert "start.completed" in types
    # the run kept going — evidence continues after completion
    assert types.index("start.completed") < len(types) - 1
    gov = {t: s["state"] for t, s in ledger.tasks.items()
           if t.startswith("govern.")}
    assert gov.get("govern.arm-every-colonist") == "succeeded"
    assert gov.get("govern.build-chokepoint-defense") == "succeeded"
    assert gov.get("govern.stockpile-medicine") == "succeeded"
    assert gov.get("govern.maintain-mood-stability") == "succeeded"
    assert gov.get("govern.establish-power-grid") == "succeeded"
    assert gov.get("govern.research-bench") == "succeeded"
    assert gov.get("govern.research-progress") == "succeeded"
    assert gov.get("govern.mission-offers") == "succeeded"
    assert game.traps >= 1
    assert game.turbines >= 1
    assert game.benches >= 1
    assert game.research["current"] == "Battery"
    assert game.letters == []  # the offer was accepted via ui.letter
    # a fresh offer re-arms the terminal goal on the next held run
    game.letters.append({"id": "l2", "choices": ["Accept"]})
    res2 = run_start(d, game, ledger, cfg, iterations=10, hold=True)
    assert res2["completed"]
    assert game.letters == []
    # every write has evidence: issued + terminal
    for env in events:
        if env["event_type"] == "action.issued":
            tid = env["payload"]["template_id"]
            assert any(e["event_type"] in ("action.completed",
                                           "action.failed")
                       and e["payload"]["template_id"] == tid
                       for e in events)


def test_haul_stall_escalates_to_storage(rig):
    """UR-RUN-006: a full stockpile stalls haul — after `after_attempts`
    requeues the escalate steps create the overflow zone and hauling
    completes; retrying the same write forever is not the fix."""
    d, game, ledger, cfg, events = rig
    game.storage_full = True  # first stockpile can't sink the items
    pack = copy.deepcopy(cfg)
    haul = next(p for p in pack["start"]["phases"]
                if p["id"] == "haul")
    haul["lease_ticks"] = 60   # sim ticks +25 per advance
    res = run_start(d, game, ledger, pack, iterations=120)
    assert res["completed"]
    assert ledger.tasks["start.haul"]["state"] == "succeeded"
    assert ledger.tasks["start.haul"]["attempts"] >= 2
    assert "start.overflow" in [z.get("label") for z in game.zones]
    issued = [e["payload"].get("params", {}).get("label")
              for e in events
              if e["event_type"] == "action.issued"
              and e["payload"].get("template_id") == "create-stockpile"]
    assert "start.overflow" in issued


def test_deleted_zones_rebuild_under_hold(rig):
    """Zones destroyed by construction re-arm the maintain-storage
    goals — stockpiles come back instead of haul jobs spamming into
    nothing (UR-RUN-006, UR-RUN-009)."""
    d, game, ledger, cfg, events = rig
    res = run_start(d, game, ledger, cfg, iterations=60, hold=True)
    assert res["completed"]
    game.zones.clear()   # construction deleted every zone
    run_start(d, game, ledger, cfg, iterations=30, hold=True)
    labels = [z.get("label") for z in game.zones]
    assert "start.storage" in labels
    assert "start.overflow" in labels


def test_hunting_suspends_when_fed(rig):
    """stocks.nutrition >= full -> steward hunting suspended (wildlife
    is farmed slowly, not drained); below scarce -> resumed at the
    low slow-farm target."""
    d, game, ledger, cfg, events = rig
    res = run_start(d, game, ledger, cfg, iterations=60, hold=True)
    assert res["completed"]
    game.stocks_nutrition = 20.0
    run_start(d, game, ledger, cfg, iterations=20, hold=True)
    jobs = {j["kind"]: j for j in game.stock_jobs}
    assert jobs["hunting"]["suspended"] is True
    assert jobs["hunting_leather"]["suspended"] is True
    game.stocks_nutrition = 0.0   # runway gone -> resume slow farming
    run_start(d, game, ledger, cfg, iterations=20, hold=True)
    assert jobs["hunting"]["suspended"] is False
    assert jobs["hunting"]["target"] == 200


def test_turbine_sited_cleared_and_windpath_suppressed(rig):
    """UR-BRN-026: turbine siting validates an unobstructed wind corridor
    (pack-declared axis/width/depth/kinds — the engine only scans);
    blocked sites get cut-designated before the blueprint lands, and
    the corridor is floored so trees can't regrow into it."""
    d, game, ledger, cfg, events = rig
    res = run_start(d, game, ledger, cfg, iterations=80, hold=True)
    assert res["completed"]
    assert ledger.tasks["govern.establish-power-grid"]["state"] \
        == "succeeded"
    assert game.gens                       # turbine actually built
    gen = game.gens[0]
    x, z = gen["pos"]
    pw = cfg["govern"]["power"]
    site_min = res["site"]["min"]
    rx, rz = site_min[0] + pw["rect_dx"], site_min[1] + pw["rect_dy"]
    assert rx <= x < rx + pw["rect_w"] \
        and rz <= z < rz + pw["rect_h"]   # inside the pack's site rect
    # clearing was designated by thing id with the pack's designator
    cut = [e["payload"]["params"] for e in events
           if e["event_type"] == "action.issued"
           and e["payload"]["template_id"] == "clear-vegetation"]
    assert cut and cut[0]["designator"] == "cut"
    assert all(isinstance(t, str) for t in cut[0]["things"])
    # the built turbine's corridors carry no surviving obstruction
    w = cfg["govern"]["power"]["wind"]
    paths = policy._fn_wind_path(
        None, gen["pos"], w["axis"], w["half_width"], w["depth"],
        w["gap"], w.get("foot", 1))
    assert not any(
        f for f in game.flora
        if any(policy._in_rect(f["pos"], r) for r in paths))
    # suppress=floor: both corridors are wood-floored
    floors = [e["payload"]["params"] for e in events
              if e["event_type"] == "action.issued"
              and e["payload"]["template_id"] == "lay-floor"]
    assert len(floors) >= 2 and all(f["def"] == "WoodFloor"
                                    for f in floors)
    for r in paths:
        assert all(game.terrain.get((cx, cz)) == "WoodFloor"
                   for cx in range(r[0], r[0] + r[2])
                   for cz in range(r[1], r[1] + r[3]))
    assert ledger.tasks["govern.maintain-turbine-windpath"]["state"] \
        == "succeeded"


def test_failed_goal_backs_off_not_starves(rig):
    """A permanently-blocked standing goal must yield the poll to
    lower-priority goals after it fails — otherwise it starves every
    goal declared below it."""
    d, game, ledger, cfg, events = rig
    pack = copy.deepcopy(cfg)
    pack["govern"]["goals"].insert(0, {
        "id": "never",
        "lease_ticks": 60,   # sim ticks +25/advance -> fast retries
        "effect": {"field": "@fn:zone_named(no.such.zone)",
                   "op": "truthy"},
        "steps": []})
    res = run_start(d, game, ledger, pack, iterations=60, hold=True)
    assert res["completed"]
    assert ledger.tasks["govern.never"]["state"] == "failed"
    # despite 'never' failing at the top of the order, a later goal
    # still gets evaluated and fires
    game.stocks_nutrition = 20.0
    run_start(d, game, ledger, pack, iterations=40, hold=True)
    jobs = {j["kind"]: j for j in game.stock_jobs}
    assert jobs["hunting"]["suspended"] is True


def test_brain_reset_unload_reload_loop(rig):
    """UR-BRN-019/020/023: the brain refreshes, unloads, reloads, and
    swaps packs through the request channel — tombstoned namespaces,
    zero writes while unloaded, clean resume, durable replay."""
    d, game, ledger, cfg, events = rig
    state_dir = ledger._path.parent
    res = run_start(d, game, ledger, cfg, iterations=60, hold=True,
                    live_brain=True)
    assert res["completed"]

    def post(body):
        (state_dir / "brain_reset.request").write_text(body)

    # 1) refresh {} — reloads the active pack; every pack task
    #    namespace is tombstoned with durable rows (UR-BRN-020)
    post("{}")
    run_start(d, game, ledger, cfg, iterations=6, hold=True,
              live_brain=True)
    resets = [e for e in events if e["event_type"] == "brain.reset"]
    assert resets[-1]["payload"]["ok"]
    assert resets[-1]["payload"]["dropped_tasks"] > 0
    tombs = [e["payload"]["task_id"] for e in events
             if e["event_type"] == "task.transition"
             and e["payload"].get("to_state") == "reset"]
    assert any(t.startswith("start.") for t in tombs)
    assert any(t.startswith("govern.") for t in tombs)
    # reload means the drift check sees the same hash — zero refusals
    assert not [e for e in events
                if "pack_drift" in json.dumps(e)]
    # the fresh brain already re-derived its goals from observed state
    assert "govern.maintain-storage" in ledger.tasks

    # 2) unload — the brain halts; zero pack-driven writes
    post('{"unload": true}')
    issued = lambda: sum(1 for e in events
                         if e["event_type"] == "action.issued")
    n0 = issued()
    out = run_start(d, game, ledger, cfg, iterations=6, hold=True,
                    live_brain=True)
    assert all(o.get("state") == "unloaded"
               for o in out["outcomes"][-5:])
    assert issued() == n0
    status = json.loads(
        (state_dir / "brain_status.json").read_text())
    assert status["state"] == "unloaded"

    # 3) reload {} — driving resumes; no residual unload state
    post("{}")
    out = run_start(d, game, ledger, cfg, iterations=6, hold=True,
                    live_brain=True)
    assert all(o.get("state") != "unloaded"
               for o in out["outcomes"])

    # 4) swap to a different pack — load by id mid-run
    post('{"pack": "dev-lab-v0"}')
    run_start(d, game, ledger, cfg, iterations=6, hold=True,
              live_brain=True)
    assert d._pack_file == "dev-lab-v0"
    resets = [e for e in events if e["event_type"] == "brain.reset"]
    assert resets[-1]["payload"]["ok"]
    assert resets[-1]["payload"]["pack_id"] == "dev-lab-v0"

    # 5) durable replay — a fresh ledger folded from the same log sees
    #    identical task state; tombstones reset cleanly on restart
    fresh = TaskLedger(state_dir / "tasks.jsonl")
    assert {t: s["state"] for t, s in fresh.tasks.items()} == \
           {t: s["state"] for t, s in ledger.tasks.items()}


def test_established_colony_zero_writes(tmp_path, monkeypatch):
    """SC-703: effects already hold -> skip path, zero designations."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = StartSim(established=True)
    events: list[dict] = []
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    cfg = d.pack["pack"]
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl")
    res = run_start(d, game, ledger, cfg, iterations=15)
    assert res["completed"]
    # no zone/build/designate writes — only skips + verify
    write_types = [e["event_type"] for e in events
                   if e["event_type"].startswith("action.")]
    assert "action.issued" not in write_types or \
        all(e["payload"]["template_id"] == "set-anchor"
            for e in events if e["event_type"] == "action.issued")


def test_forced_restart_resumes(rig):
    """SC-702: crash mid-graph -> fresh ledger+mode resume, no replays."""
    d, game, ledger, cfg, events = rig
    path = ledger._path
    mode = StartMode(cfg, ledger)
    for tick in (0, 25, 50):
        obs = observe_start(game)
        ledger.reconcile(obs, tick)
        mode.step(d, game, obs, tick)
        game.advance(0)
    states = {t: s["state"] for t, s in ledger.tasks.items()}
    del ledger, mode
    ledger2 = TaskLedger(path)
    mode2 = StartMode(cfg, ledger2)
    assert {t: s["state"] for t, s in ledger2.tasks.items()} == states
    assert mode2.site == mode_site_persisted(path)
    # continue from a fresh mode — no phase re-dispatches
    res = run_start(d, game, ledger2, cfg, iterations=40)
    assert res["completed"]


def mode_site_persisted(path: Path):
    p = path.parent / "startmode.json"
    if not p.is_file():
        return None
    saved = json.loads(p.read_text())
    return (saved.get("vars") or {}).get("site", saved.get("site"))


def test_partial_coverage_stays_active(tmp_path, monkeypatch):
    """SC-704: 2/3 beds -> mode does NOT complete, beds phase prioritized."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = StartSim()
    game.rooms = [{"role": "Bedroom", "beds": 2, "problems": []}]
    game.beds = 2
    game.food_source = True
    game.recreation = True
    game.zones = [{"label": "z"}]
    d = Dispatcher(game, clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl")
    mode = StartMode(d.pack["pack"], ledger)
    mode._game = game
    obs = observe_start(game)
    ev = mode._exit_eval(obs, mode._ctx(obs))
    assert ev["conditions"]["beds"] is False and not ev["complete"]


def test_site_ranking_deterministic(rig):
    _d, game, _l, cfg, _e = rig
    obs = observe_start(game)
    ctx = policy.Ctx(cfg=cfg, obs=obs, game=game)
    site_cfg = cfg["start"]["site"]
    a = policy.FN["rank_site"](ctx, site_cfg["zone_w"], site_cfg["zone_h"],
                               site_cfg["weights"]["items_proximity"],
                               site_cfg["weights"]["home_proximity"])
    b = policy.FN["rank_site"](ctx, site_cfg["zone_w"], site_cfg["zone_h"],
                               site_cfg["weights"]["items_proximity"],
                               site_cfg["weights"]["home_proximity"])
    assert a == b and a["min"] == [14, 14]


def test_site_ranking_applies_anchor_offset(rig):
    # footprint search stamps candidates with anchor_off — site.min
    # lands inside the patch so negative-offset plan geometry stays
    # on open ground (the portability contract for blueprints)
    _d, game, _l, cfg, _e = rig
    obs = observe_start(game)
    obs["open_rects"] = [{"min": [25, 20], "anchor_off": [14, 24]}]
    ctx = policy.Ctx(cfg=cfg, obs=obs, game=game)
    s = policy.FN["rank_site"](ctx, 9, 9, 2.0, 1.0)
    assert s["min"] == [39, 44]
