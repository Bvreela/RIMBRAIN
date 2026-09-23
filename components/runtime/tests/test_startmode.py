"""Start-mode tests (feature 008; FR-701..709, SC-701..705).

StartSim models a fresh-map rpc surface: drop-pile items, open rects,
no zones/rooms/stocks. Writes mutate it deterministically on advance()
so phase effects verify only when the world actually changes.
"""

from __future__ import annotations

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
        self.rooms: list[dict] = []
        self.blueprints: list[dict] = []
        self.roofed: set[tuple] = set()
        self.beds = 0
        self.food_source = False
        self.recreation = False
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
        self.benches = 0               # research benches built
        self.research = {"current": None,
                         "available": ["Battery", "SolarPanels"],
                         "finished": 0}
        self.letters: list[dict] = []  # pending letters {id, choices}
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
            wdef = params.get("def")
            wpool = ([t for t in self.weapons if t["def"] == wdef]
                     or [t for t in self.armor if t["def"] == wdef])
            if wpool:
                return {"ok": True, "result": {
                    "count": len(wpool), "things": list(wpool)}}
            if params.get("kind") == "blueprint":
                return {"ok": True, "result": {
                    "count": len(self.blueprints),
                    "things": list(self.blueprints)}}
            src = self.forbidden if params.get("forbidden") else self.items
            return {"ok": True, "result": {
                "count": len(src), "things": list(src)}}
        if method == "map.open_rects":
            return {"ok": True, "result": [
                {"min": [60, 60]}, {"min": [14, 14]}, {"min": [30, 40]}]}
        if method == "map.cell":
            cell = tuple((params.get("cell") or [0, 0])[:2])
            return {"ok": True, "result": {
                "roof": cell in self.roofed, "walkable": True,
                "fertility": self.fertility.get(cell, 1.0)}}
        if method == "state.storage":
            return {"ok": True, "result": list(self.zones)}
        if method == "state.rooms":
            return {"ok": True, "result": list(self.rooms)}
        if method == "state.stocks":
            return {"ok": True, "result": {"total": len(self.items)}}
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
                "recreation": self.recreation,
                "cookstations": self.cookstations, "bills": self.bills,
                "meals": self.meals, "anchors": self.anchors,
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
            return {"ok": True, "result": {"placed": 1}}
        if method == "ui.add_bill":
            self.bills.setdefault(params["thing"], []).append(
                params["recipe"])
            self._pending.append("meal")
            return {"ok": True, "result": {"bill": params["recipe"]}}
        if method == "dev.incident":
            for i in range(2):
                self.hostiles.append(
                    {"id": f"raider-{len(self.hostiles)}", "kind": "Pirate"})
            return {"ok": True, "result": {"fired": params.get("def")}}
        if method == "dev.spawn_pawn":
            self.hostiles.append(
                {"id": f"pawn-{len(self.hostiles)}",
                 "kind": params.get("kind"),
                 "faction": params.get("faction")})
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
            elif job == "Wear" and pawn is not None:
                pawn.setdefault("apparel", []).append(
                    params.get("target"))
            elif pawn is not None:
                pawn["job"] = job  # fallback idle-correction jobs land here
            return {"ok": True, "result": {"applied": True}}
        if method == "state.pawns":
            return {"ok": True, "result": list(self.pawns)}
        if method == "state.pawn":
            pid = params.get("pawn")
            return {"ok": True, "result": {
                "id": pid,
                "skills": self.skills.get(pid, {}),
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
    assert gov.get("govern.research-bench") == "succeeded"
    assert gov.get("govern.research-progress") == "succeeded"
    assert gov.get("govern.mission-offers") == "succeeded"
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
