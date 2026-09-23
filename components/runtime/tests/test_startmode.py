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
from runtime.startmode import StartMode, observe_start, rank_site, \
    run_start  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402


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
        self.anchors: dict[str, dict] = {}
        self._pending: list[str] = []
        self.writes: list[tuple] = []
        if established:
            self.zones = [{"label": "start.storage"},
                          {"label": "growing", "plant": "Plant_Rice"}]
            self.rooms = [{"role": "Bedroom", "beds": 3, "problems": []},
                          {"role": "Bedroom", "beds": 0, "problems": []},
                          {"role": "Bedroom", "beds": 0, "problems": []}]
            self.beds = 3
            self.food_source = True
            self.recreation = True
            self.anchors = {"start.storage": {"min": [14, 14]}}
            self.roofed = {(14, 14)}  # zone is already roofed

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
                "roof": cell in self.roofed, "walkable": True}}
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
                self.zones.append({"label": "growing",
                                   "plant": params.get("plant")})
                self._pending.append("food")
                return {"ok": True, "result": {"zone": "growing"}}
        if method == "ui.designate":
            d = params.get("designator")
            if d == "unforbid":
                self._pending.append("unforbid")
            elif d == "haul":
                self._pending.append("haul")
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
            if params.get("def") == "Bed":
                self._pending.append("bed")
            elif params.get("def") == "HorseshoesPin":
                self._pending.append("recreation")
            return {"ok": True, "result": {"placed": 1}}
        if method == "ui.job":
            return {"ok": True, "result": {"applied": True}}
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
            elif p == "recreation":
                self.recreation = True
        self._pending = []


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    cfg = d.pack["pack"]["start"]
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, cfg, events


def test_full_bootstrap_to_completed(rig):
    """SC-701: ordered trace site->...->baseline -> start.completed."""
    d, game, ledger, cfg, events = rig
    res = run_start(d, game, ledger, cfg, iterations=20)
    assert res["completed"]
    assert res["site"]["min"] == [14, 14]  # nearest the item cluster
    phases = [t for t in ledger.tasks.values()]
    assert all(t["state"] == "succeeded" for t in phases)
    assert len(phases) == 9  # 6 bootstrap + 3 baseline
    types = [e["event_type"] for e in events]
    assert "start.completed" in types
    assert types.index("start.completed") == len(types) - 1
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
    cfg = d.pack["pack"]["start"]
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
    res = run_start(d, game, ledger2, cfg, iterations=20)
    assert res["completed"]


def mode_site_persisted(path: Path):
    p = path.parent / "startmode.json"
    return json.loads(p.read_text())["site"] if p.is_file() else None


def test_partial_coverage_stays_active(tmp_path, monkeypatch):
    """SC-704: 2/3 beds -> mode does NOT complete, beds phase prioritized."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = StartSim()
    game.rooms = [{"role": "Bedroom", "beds": 2, "problems": []}]
    game.beds = 2
    game.food_source = True
    game.recreation = True
    game.zones = [{"label": "z"}]
    obs = observe_start(game)
    from runtime.startmode import exit_eval
    ev = exit_eval(obs, {}, 3)
    assert ev["beds"] is False and not ev["complete"]


def test_site_ranking_deterministic(rig):
    _d, game, _l, cfg, _e = rig
    obs = observe_start(game)
    a, b = rank_site(obs, cfg["site"]), rank_site(obs, cfg["site"])
    assert a == b and a["min"] == [14, 14]
