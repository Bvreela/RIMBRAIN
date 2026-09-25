"""Feature 019 combat-capability tests (contracts/combat-capability.md).

T010: engaged/watch classification, draftable predicate, structured
gate rows with reasons. T011: classification truth table — Home/radius/
lord/mental/structure — overrun detection, eligibility bounds.
"""

import sys
from pathlib import Path

import pytest
import yaml

from runtime import policy

REPO = Path(__file__).resolve().parents[3]
for _p in ("components/runtime/src", "components/contracts/src"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

PACK_PATH = REPO / "components" / "rimbrain" / "packs" / \
    "combat-defense-v0" / "pack.yaml"


HOME = [40, 40, 21, 21]          # x,z,w,h -> cells 40..60


class CombatStub:
    """RPC stub shaped like the live bridge + steward order surface."""

    def __init__(self, hostiles=(), pawns=(), pawn_detail=None,
                 areas=None, orders=None, rally=None, defs=None,
                 hands_off=None, cells=None):
        self.hostiles = list(hostiles)
        self.pawns = list(pawns)
        self.pawn_detail = pawn_detail or {}
        self.areas = (areas if areas is not None
                      else [{"id": "Home", "rect": HOME}])
        self.orders = dict(orders or {})
        self.rally = rally or [44, 44, 13, 13]
        self.defs = defs or {}
        self.hands_off = list(hands_off or [])
        self.cells = cells or {}
        self.calls = []

    def rpc(self, method, params=None):
        params = params or {}
        self.calls.append(method)
        r = self._rpc(method, params)
        return {"ok": r is not None, "result": r or {}}

    def _rpc(self, method, params):
        if method == "state.threats":
            return {"hostiles": list(self.hostiles),
                    "home_center": [50, 50]}
        if method == "state.pawns":
            return list(self.pawns)
        if method == "state.pawn":
            pid = params.get("pawn") or params.get("id")
            return dict(self.pawn_detail.get(pid, {}))
        if method == "state.areas":
            return {"areas": list(self.areas)}
        if method == "steward.status":
            if not self.orders:
                return {}          # no steward surface
            return {"orders": [{"id": oid,
                                "enabled": o.get("enabled", False),
                                "summary": o.get("summary", ""),
                                "acting_on": o.get("acting_on"),
                                "last": o.get("last")}
                               for oid, o in self.orders.items()],
                    "rally": self.rally}
        if method == "steward.orders.explain":
            oid = params.get("id")
            o = self.orders.get(oid)
            if o is None:
                return {}
            return {"id": oid, "enabled": o.get("enabled", False),
                    "summary": o.get("summary", ""),
                    "last": o.get("last"),
                    "hands_off": list(self.hands_off)}
        if method == "defs.get":
            return dict(self.defs.get(params.get("def"), {}))
        if method == "map.cell":
            c = params.get("cell") or []
            return {"things": list(self.cells.get(tuple(c), []))}
        return {}


def ctx(hostiles=(), pawns=(), obs=None, cfg=None, **kw):
    game = CombatStub(hostiles=hostiles, pawns=pawns, **kw)
    o = {"colonist_list": list(pawns), "colonists": {"count":
                                                     len(pawns)},
         "map": {"home": [50, 50]}, "rooms": []}
    o.update(obs or {})
    c = policy.Ctx(
        cfg={"combat": {"engage_radius": 40, "overrun_radius": 5,
                        "near_hostile": 30, "min_health": 30,
                        "release_ticks": 600, "release_polls": 5,
                        "prolonged_ticks": 36000,
                        "chase_skill": 6, "engage_odds_floor": 0.4,
                        "relief": {"food": 30, "rest": 25},
                        "option_weights": {},
                        "delegate_order": "combat", **(cfg or {})}},
        obs=o, game=game, state={}, tick=1000, poll=1)
    return c, game


def h(id="h1", pos=(90, 90), **kw):
    return {"id": id, "kind": "PirateGunner", "pos": list(pos), **kw}


def c(id="p1", pos=(50, 50), **kw):
    kw.setdefault("weapon", "Gun_Revolver")
    kw.setdefault("health", 100)
    kw.setdefault("faction", "Player")
    kw.setdefault("job", "Worker")
    return {"id": id, "name": id, "pos": list(pos), **kw}


# -- T010: classification -----------------------------------------------------

def test_in_home_hostile_is_engaged():
    cc, _ = ctx(hostiles=[h(pos=(45, 45))])
    assert [x["id"] for x in
            policy.resolve("@fn:engaged_hostiles()", cc)] == ["h1"]
    assert policy.resolve("@fn:watching_hostiles()", cc) == []


def test_far_hostile_is_watch():
    cc, _ = ctx(hostiles=[h(pos=(120, 120))])
    assert policy.resolve("@fn:engaged_hostiles()", cc) == []
    assert len(policy.resolve("@fn:watching_hostiles()", cc)) == 1


def test_siege_lord_watches():
    cc, _ = ctx(hostiles=[h(pos=(80, 80), lord="LordJob_Siege")])
    assert policy.resolve("@fn:engaged_hostiles()", cc) == []


def test_assault_lord_engages_at_any_range():
    cc, _ = ctx(hostiles=[h(pos=(150, 150), lord="AssaultColony")])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 1


def test_excluded_hostiles_never_engage():
    rows = [h(id="d1", pos=(45, 45), downed=True),
            h(id="f1", pos=(45, 45), fogged=True),
            h(id="p1", pos=(45, 45), faction="Player"),
            h(id="k1", pos=(45, 45), dead=True)]
    cc, _ = ctx(hostiles=rows)
    assert policy.resolve("@fn:engaged_hostiles()", cc) == []
    assert policy.resolve("@fn:watching_hostiles()", cc) == []


def test_manhunter_conditional():
    # colonist outside Home -> engage; all sheltered -> watch
    mh = h(mental="Manhunter", pos=(90, 90))
    cc, _ = ctx(hostiles=[mh], pawns=[c(pos=(70, 70))])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 1
    cc, _ = ctx(hostiles=[h(mental="Manhunter", pos=(90, 90))],
                pawns=[c(pos=(50, 50))])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 0


def test_structure_near_rally_engages():
    cc, _ = ctx(hostiles=[h(pos=(70, 50), kind="Turret_MiniTurret")])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 1
    cc, _ = ctx(hostiles=[h(pos=(140, 140),
                            kind="Turret_MiniTurret")])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 0


def test_combat_mode_watch_engage_hold_overrun():
    cc, _ = ctx()
    assert policy.resolve("@fn:combat_mode()", cc) == "watch"
    cc, _ = ctx(hostiles=[h(pos=(70, 70), lord="AssaultColony")],
                pawns=[c()])
    assert policy.resolve("@fn:combat_mode()", cc) == "engage"
    cc, _ = ctx(hostiles=[h(pos=(70, 70), lord="AssaultColony")],
                pawns=[c(drafted=True)],
                orders={"combat": {"enabled": True}})
    assert policy.resolve("@fn:combat_mode()", cc) == "hold"
    cc, _ = ctx(hostiles=[h(pos=(50, 49), lord="AssaultColony")],
                pawns=[c(drafted=True)],
                orders={"combat": {"enabled": True}})
    assert policy.resolve("@fn:combat_mode()", cc) == "overrun"


# -- T010/T011: eligibility ---------------------------------------------------

def test_draftable_basics():
    cc, _ = ctx(pawns=[c(id="a"), c(id="b", weapon=None),
                       c(id="kid", life_stage="Child"),
                       c(id="hurt", health=20),
                       c(id="pr", prisoner=True)])
    assert policy.resolve("@fn:draftable()", cc) == ["a"]
    cc2, _ = ctx(pawns=[c(id="b", weapon=None)],
                 cfg={"allow_unarmed": True})
    assert policy.resolve("@fn:draftable()", cc2) == ["b"]


def test_draftable_single_id_and_list():
    cc, _ = ctx(pawns=[c(id="a"), c(id="b", weapon=None)])
    assert policy.resolve("@fn:draftable('a')", cc) is True
    assert policy.resolve("@fn:draftable('b')", cc) is False
    assert policy.resolve(
        "@fn:draftable(@fn:colonist_ids())", cc) == ["a"]


def test_draftable_touch_interlock():
    # hands_off row names p1 -> excluded; steward absent -> no writer,
    # nothing excluded; steward present but explain unreachable ->
    # conservative exclusion
    cc, _ = ctx(pawns=[c(id="p1"), c(id="p2")],
                orders={"combat": {"enabled": True}},
                hands_off=[{"thing": "p1", "reason": "manual"}])
    assert policy.resolve("@fn:draftable()", cc) == ["p2"]

    class NoSteward(CombatStub):
        def rpc(self, m, p=None):
            return {} if m.startswith("steward.") \
                else super().rpc(m, p)

    g = NoSteward(pawns=[c(id="p1")])
    cc = policy.Ctx(cfg=ctx()[0].cfg, obs={"colonists": [c(id="p1")]},
                    game=g, state={})
    assert policy.resolve("@fn:draftable()", cc) == ["p1"]

    class DeafSteward(CombatStub):
        def rpc(self, m, p=None):
            if m == "steward.orders.explain":
                return {}
            return super().rpc(m, p)

    g = DeafSteward(pawns=[c(id="p1")],
                    orders={"combat": {"enabled": True}})
    cc = policy.Ctx(cfg=ctx()[0].cfg, obs={"colonists": [c(id="p1")]},
                    game=g, state={})
    assert policy.resolve("@fn:draftable()", cc) == []


def test_draftable_no_home_surface_still_works():
    cc, _ = ctx(pawns=[c(id="a")], areas=[])
    assert policy.resolve("@fn:draftable()", cc) == ["a"]
    # classification without a Home surface: radius still applies
    cc, _ = ctx(hostiles=[h(pos=(70, 70), lord="AssaultColony")],
                areas=[])
    assert len(policy.resolve("@fn:engaged_hostiles()", cc)) == 1


# -- T010: structured gate rows ------------------------------------------------

def test_gate_rows_carry_clause_reasons():
    """Evidence-marked rules record {field, op, resolved, result,
    reason} clause rows on gate pass<->fail transitions (FR-1908)."""
    decisions = []

    class Sink:
        def dispatch(self, t, p):
            return {"ok": True}

    rules = [{"id": "combat-arm", "evidence": True,
              "when": {"field": "@fn:engaged_hostiles()",
                       "op": "not_empty"},
              "try": [{"template": "order-set",
                       "params": {"id": "combat", "enabled": True}}]}]

    cc, _ = ctx(hostiles=[h(pos=(45, 45))])    # pass -> fires
    cc.decisions = decisions
    state = cc.state
    fired = policy.run_rules(rules, Sink(), cc, source="rule")
    assert fired and not [d for d in decisions if d.get("gate")]

    cc2, _ = ctx(hostiles=[h(pos=(120, 120))])  # fail -> transition row
    cc2.state = state
    cc2.decisions = decisions
    assert policy.run_rules(rules, Sink(), cc2, source="rule") == []
    gate_rows = [d for d in decisions if d.get("gate")]
    assert len(gate_rows) == 1
    assert gate_rows[0]["result"] is False
    clause = gate_rows[0]["clauses"][0]
    assert clause["field"] == "@fn:engaged_hostiles()"
    assert clause["op"] == "not_empty"
    assert clause["result"] is False
    assert clause["reason"] == "mismatch"


def test_combat_evidence_rule_records_snapshot():
    decisions = []
    cc, _ = ctx(hostiles=[h(pos=(45, 45))], pawns=[c(id="a")],
                orders={"combat": {"enabled": True,
                                   "summary": "engaged 1 hostiles",
                                   "acting_on": "h1"}})
    cc.decisions = decisions
    rules = [{"id": "combat-evidence", "kind": "combat-evidence",
              "when": {"field": "@fn:combat_mode()",
                       "op": "ne", "value": "watch"}}]

    class Sink:
        def dispatch(self, t, p):
            raise AssertionError("evidence rules must not dispatch")

    fired = policy.run_rules(rules, Sink(), cc, source="rule")
    assert fired == [{"rule": "combat-evidence",
                      "kind": "combat-evidence"}]
    row = decisions[-1]
    assert row["kind"] == "combat-evidence"
    assert row["mode"] == "overrun"        # in-Home hostile
    assert row["engaged"] == ["h1"]
    assert row["fighters"] == ["a"]
    assert row["order"]["enabled"] is True
    assert any(m["marker"] == "combat.overrun"
               for m in row["markers"])
    # second poll in the same engagement does not re-mark
    cc2, _ = ctx(hostiles=[h(pos=(45, 45))], pawns=[c(id="a")],
                 orders={"combat": {"enabled": True,
                                    "summary": "engaged",
                                    "acting_on": "h1"}})
    cc2.state = cc.state
    cc2.tick = 2000
    cc2.decisions = decisions
    policy.run_rules(rules, Sink(), cc2, source="rule")
    assert decisions[-1]["markers"] == []


def test_order_state_gap_is_fail_closed():
    cc, _ = ctx()                    # no steward -> all fields None
    st = policy.resolve("@fn:order_state()", cc)
    assert st["enabled"] is None and st["engaged"] is None
    # gates on unknown order state evaluate false, never truthy
    assert policy.check({"field": "@fn:order_state().enabled",
                         "op": "truthy"}, cc) is False


# -- T016: sim delegate lifecycle ----------------------------------------------

def test_sim_delegate_combat_lifecycle(tmp_path, monkeypatch):
    """combat-defense-v0 over SimGame: the pack arms the steward order
    on hostile contact; the order drafts, wins, and releases after the
    hostile-free window — evidence rows record the posture."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for p in ("components/runtime/src", "components/contracts/src"):
        if str(root / p) not in sys.path:
            sys.path.insert(0, str(root / p))
    from runtime.dispatch import Dispatcher
    from runtime.loop import run
    from runtime.simgame import SimGame
    from runtime.tasks import TaskLedger

    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = SimGame(established=True)
    game.rpc("dev.incident", {"def": "Raid"})     # 2 hostiles spawn
    records: list[dict] = []
    d = Dispatcher(game, sink=records.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("combat-defense-v0")
    # delegated mode: combat.direct_command=false keeps the steward
    # order lifecycle (the pack's default is Laya-driven direct command);
    # short release window so the quiet-then-release fires in 45 iters
    d.pack["pack"]["combat"]["direct_command"] = False
    d.pack["pack"]["combat"]["release_ticks"] = 100
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=records.append)
    run(d, game, ledger, d.pack["pack"], iterations=45)

    order = game.orders.get("combat")
    assert order is not None, "pack never armed the delegate order"
    assert order["last"] == "combat_released"
    assert not game.drafted                    # colonists stood down
    assert not [h for h in game.hostiles
                if not h.get("downed") and not h.get("dead")]
    issued = [e.get("payload", {}).get("template_id") for e in records
              if e.get("event_type") == "action.issued"]
    assert "order-set" in issued


# -- T017/T018: pawn_scope compile + fallback ----------------------------------

def _engine():
    class E:
        phase_id = "govern"
        decisions: list = []

        def goal_sources(self):
            return []
    e = E()
    e.decisions = []
    return e


def test_rally_cells_are_distinct_per_fighter():
    cc, _ = ctx(pawns=[c(id="a"), c(id="b")],
                orders={"combat": {"enabled": True}})
    a = policy.resolve("@fn:rally_cell('a')", cc)
    b = policy.resolve("@fn:rally_cell('b')", cc)
    assert a and b and a != b
    # stable across re-resolve within the poll
    assert policy.resolve("@fn:rally_cell('a')", cc) == a


def test_pawn_scope_compiles_bounded_candidates():
    from runtime import select
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    hostiles = [h(pos=(70, 70), lord="AssaultColony")]
    cc, _ = ctx(hostiles=hostiles,
                pawns=[c(id="a", pos=(52, 52)), c(id="b", pos=(54, 54))],
                orders={"combat": {"enabled": True}},
                defs={"Gun_Revolver": {"stats": {"range": 26,
                                                 "is_melee": False}}})
    cands = select.compile_actions(pack, _engine(), cc, cc.obs)
    assert 0 < len(cands) <= select.HARD_MAX
    assert all(cd["scope"] == "pawn" for cd in cands)
    ids = {cd["id"] for cd in cands}
    assert "pawn.a.combat-focus" in ids or \
        "pawn.a.combat-move" in ids


def test_pawn_scope_fallback_is_priority_head(tmp_path):
    """caller=None (sim) -> shadow rung -> the applied pick is the
    highest-priority offered option for each pawn (SC-1903)."""
    from runtime import select
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    hostiles = [h(pos=(70, 70), lord="AssaultColony")]
    cc, _ = ctx(hostiles=hostiles,
                pawns=[c(id="a", pos=(52, 52))],
                orders={"combat": {"enabled": True}},
                defs={"Gun_Revolver": {"stats": {"range": 26,
                                                 "is_melee": False}}})
    sent = []

    class Sink:
        def dispatch(self, t, p):
            sent.append((t, p))
            return {"ok": True, "result": {}}

    engine = _engine()
    out = select.decide(Sink(), pack, engine, cc, cc.obs,
                        tick=1000, poll=5, state_dir=tmp_path,
                        caller=None)
    assert out is not None
    rows = [d for d in engine.decisions if d.get("source",
                                                 "").startswith("select:")]
    assert rows, "no select decision rows"
    row = rows[0]
    assert row["fallback"] and row["shadow"]
    assert sent and sent[0][0] == "attack-target"
    # combat-strike (distance-weighted ~74 at dist 25) outranks
    # combat-focus (60) — nearest-hostile strike is the priority head
    assert row["applied"] == "pawn.a.combat-strike.h1"
    assert sent[0][1] == {"pawn": "a", "target": "h1"}


def test_pawn_scope_retreat_suppression_and_offer():
    """A hurt fighter gets combat-retreat; when safe_cell can't clear
    the near_hostile bound the option is suppressed entirely
    (FR-1910 — never a bad move)."""
    from runtime import select
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    # hostile rings the home center -> every candidate cell < 30 of it
    ring = [h(id=f"r{i}", pos=(50 + dx, 50 + dz),
              lord="AssaultColony")
            for i, (dx, dz) in
            enumerate([(8, 0), (-8, 0), (0, 8), (0, -8), (8, 8)])]
    cc, _ = ctx(hostiles=ring,
                pawns=[c(id="a", pos=(52, 52), health=10)],
                orders={"combat": {"enabled": True}})
    cands = select.compile_actions(pack, _engine(), cc, cc.obs)
    assert "pawn.a.combat-retreat" not in {cd["id"] for cd in cands}
    # healthy fighter far away -> retreat offered + applied by fallback
    cc2, _ = ctx(hostiles=[h(pos=(90, 90), lord="AssaultColony")],
                 pawns=[c(id="a", pos=(52, 52), health=10)],
                 orders={"combat": {"enabled": True}})
    cands = select.compile_actions(pack, _engine(), cc2, cc2.obs)
    assert "pawn.a.combat-retreat" in {cd["id"] for cd in cands}


# -- T024: composition-aware tactics -------------------------------------------

def test_enemy_mix_and_power():
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}},
            "MeleeWeapon_Gladius": {"stats": {"range": 2,
                                              "is_melee": True}}}
    rows = [h(id="r1", pos=(70, 70), weapon="Gun_Revolver",
              kind="PirateGunner", lord="AssaultColony"),
            h(id="m1", pos=(70, 70), weapon="MeleeWeapon_Gladius",
              kind="TribalWarrior", lord="AssaultColony"),
            h(id="t1", pos=(70, 70), kind="Turret_MiniTurret"),
            h(id="w1", pos=(70, 70), kind="Drifter",
              lord="AssaultColony")]          # unarmed -> melee
    cc, _ = ctx(hostiles=rows, defs=defs)
    mix = policy.resolve("@fn:enemy_mix()", cc)
    assert mix == {"melee": 2, "ranged": 1, "structure": 1, "total": 4}
    power = policy.resolve("@fn:threat_power()", cc)
    # 65 Pirate + 50 Tribal + 50 turret-default + 35 Drifter
    assert power == 200


def test_in_range_and_max_range():
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}},
            "Gun_Sniper": {"stats": {"range": 45, "is_melee": False}}}
    p = c(id="a", pos=(50, 50), weapon="Gun_Revolver")
    near = h(id="n1", pos=(60, 50), weapon="Gun_Sniper",
             lord="AssaultColony")
    far = h(id="f1", pos=(90, 50), weapon="Gun_Sniper",
            lord="AssaultColony")
    cc, _ = ctx(hostiles=[near, far], pawns=[p], defs=defs)
    assert policy.resolve("@fn:in_range('a', 'n1')", cc) is True
    assert policy.resolve("@fn:in_range('a', 'f1')", cc) is False
    assert policy.resolve("@fn:enemy_max_range()", cc) == 45
    assert policy.resolve("@fn:outranged_by('a')", cc) is True


def test_kite_suppressed_when_outranged(tmp_path):
    """FR-1910: kite is never offered when the enemy outranges the pawn
    — suppression, not a bad move."""
    from runtime import select
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}},
            "Gun_Sniper": {"stats": {"range": 45, "is_melee": False}}}
    cc, _ = ctx(hostiles=[h(pos=(70, 70), weapon="Gun_Sniper",
                            lord="AssaultColony")],
                pawns=[c(id="a", pos=(52, 52))],
                orders={"combat": {"enabled": True}}, defs=defs)
    cands = select.compile_actions(pack, _engine(), cc, cc.obs)
    assert "pawn.a.combat-kite" not in {cd["id"] for cd in cands}


def test_block_offered_to_melee_fighter_in_overrun():
    from runtime import select
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    defs = {"MeleeWeapon_Gladius": {"stats": {"range": 2,
                                              "is_melee": True}}}
    bruiser = c(id="a", pos=(52, 52), weapon="MeleeWeapon_Gladius")
    cc, _ = ctx(hostiles=[h(pos=(48, 48), weapon="MeleeWeapon_Gladius",
                            kind="TribalWarrior", lord="AssaultColony")],
                pawns=[bruiser],
                pawn_detail={"a": {"skills": {"Melee": "10"}}},
                orders={"combat": {"enabled": True}}, defs=defs)
    cands = select.compile_actions(pack, _engine(), cc, cc.obs)
    assert "pawn.a.combat-block" in {cd["id"] for cd in cands}


def test_shelter_rule_fires_on_overmatch():
    """threat_power beyond fighters/floor -> set-area shelter, not
    engagement."""
    decisions = []
    big = [h(id=f"r{i}", pos=(45 + i, 45), kind="Centipede",
             lord="AssaultColony") for i in range(10)]
    cc, _ = ctx(hostiles=big, pawns=[c(id="a")],
                orders={"combat": {"enabled": True}})
    cc.decisions = decisions
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    from runtime import templates
    rules = [r for r in templates.rules_of(pack)
             if r.get("id") == "combat-shelter-overmatch"]

    class Sink:
        def dispatch(self, t, p):
            decisions.append({"t": t, "p": p})
            return {"ok": True}

    fired = policy.run_rules(rules, Sink(), cc, source="rule")
    assert fired and fired[0]["template"] == "set-area"


# -- T028: post-combat recovery -------------------------------------------------

def _pack_rules(rid):
    import yaml
    from runtime import templates
    pack = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))
    return [r for r in templates.rules_of(pack) if r.get("id") == rid]


class _Sink:
    def __init__(self):
        self.calls = []

    def dispatch(self, t, p):
        self.calls.append((t, p))
        return {"ok": True}


def test_rescue_fires_for_casualty():
    downed = c(id="d1", downed=True, weapon=None)
    medic = c(id="m1")
    cc, _ = ctx(pawns=[downed, medic],
                pawn_detail={"m1": {"skills": {"Medicine": "9"}},
                             "d1": {"downed": True}},
                orders={"combat": {"enabled": True}})
    sink = _Sink()
    fired = policy.run_rules(_pack_rules("combat-rescue-downed"),
                             sink, cc, source="rule")
    assert fired and sink.calls[0][0] == "rescue"
    assert sink.calls[0][1]["target"] == "d1"


def test_capture_requires_free_prison_bed():
    hostile = h(id="h1", pos=(45, 45), downed=True)
    # no rooms at all -> free_beds 0 -> capture stays silent
    cc, _ = ctx(hostiles=[hostile], pawns=[c(id="a")],
                orders={"combat": {"enabled": True}})
    sink = _Sink()
    assert policy.run_rules(_pack_rules("combat-capture"),
                            sink, cc, source="rule") == []
    # a prison room with a free bed -> capture dispatches
    rooms = [{"role": "PrisonCell", "beds": 2, "occupied": 1}]
    cc2, _ = ctx(hostiles=[h(id="h1", pos=(45, 45), downed=True)],
                 pawns=[c(id="a")],
                 orders={"combat": {"enabled": True}},
                 obs={"rooms": rooms})
    sink2 = _Sink()
    fired = policy.run_rules(_pack_rules("combat-capture"),
                             sink2, cc2, source="rule")
    assert fired and sink2.calls[0][0] == "capture"
    assert sink2.calls[0][1]["target"] == "h1"


def test_strip_suppressed_while_hostiles_in_home():
    cc, _ = ctx(hostiles=[h(id="d1", pos=(45, 45), downed=True),
                          h(id="l1", pos=(46, 46))],
                pawns=[c(id="a")],
                orders={"combat": {"enabled": True}})
    sink = _Sink()
    assert policy.run_rules(_pack_rules("combat-strip-field"),
                            sink, cc, source="rule") == []
    # hostile cleared from Home -> strip dispatches on the downed row
    cc2, _ = ctx(hostiles=[h(id="d1", pos=(45, 45), downed=True),
                           h(id="l1", pos=(120, 120))],
                 pawns=[c(id="a")],
                 orders={"combat": {"enabled": True}})
    sink2 = _Sink()
    fired = policy.run_rules(_pack_rules("combat-strip-field"),
                             sink2, cc2, source="rule")
    assert fired and sink2.calls[0][1]["things"] == ["d1"]


# -- squad doctrine ------------------------------------------------------------

def test_squad_doctrine_majority_class():
    """Doctrine gates melee engagement only: ranged doctrine when
    shooters field >= half the living squad, melee swarm otherwise —
    but ranged fighters ALWAYS engage (support from range; benching a
    shooter while melee dies is losing). Melee benches only under
    ranged doctrine (screening a firing line = friendly fire)."""
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}}}
    # 1 ranged + 3 unarmed -> melee doctrine: melee swarm AND the
    # shooter supports — ranged never sits out a fight
    cc, _ = ctx(hostiles=[h(pos=(45, 45))],
                pawns=[c(id="gun", weapon="Gun_Revolver"),
                       c(id="m1", weapon=None), c(id="m2", weapon=None),
                       c(id="m3", weapon=None)],
                defs=defs,
                orders={"combat": {"enabled": True}})
    assert policy.resolve("@fn:squad_class()", cc) == "melee"
    assert policy.resolve("@fn:fighter_engages('m1')", cc) is True
    assert policy.resolve("@fn:fighter_engages('gun')", cc) is True
    # 2 ranged + 1 melee -> ranged doctrine: melee screens nothing
    cc2, _ = ctx(hostiles=[h(pos=(45, 45))],
                 pawns=[c(id="g1", weapon="Gun_Revolver"),
                        c(id="g2", weapon="Gun_Revolver"),
                        c(id="m1", weapon=None)],
                 defs=defs,
                 orders={"combat": {"enabled": True}})
    assert policy.resolve("@fn:squad_class()", cc2) == "ranged"
    assert policy.resolve("@fn:fighter_engages('m1')", cc2) is False
    assert policy.resolve("@fn:fighter_engages('g1')", cc2) is True
    # downed shooter can't hold the line -> melee doctrine
    cc3, _ = ctx(hostiles=[h(pos=(45, 45))],
                 pawns=[c(id="gun", weapon="Gun_Revolver", downed=True),
                        c(id="m1", weapon=None), c(id="m2", weapon=None)],
                 defs=defs,
                 orders={"combat": {"enabled": True}})
    assert policy.resolve("@fn:squad_class()", cc3) == "melee"


# -- decision matrix (Laya select path) -----------------------------------------

def test_option_for_each_target_matrix():
    """Pawn-scope options with for_each expand per living hostile —
    one candidate per (pawn, target), distance-weighted nearest-first,
    and the label carries the target name."""
    from runtime import select as sel_mod, templates
    p = templates.load_pack("combat-defense-v0")["pack"]
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}}}
    pawns = [c(id="p1", pos=(50, 50), weapon="Gun_Revolver")]
    hostiles = [h(id="h1", pos=(58, 52)), h(id="h2", pos=(90, 90))]
    cc, game = ctx(hostiles=hostiles, pawns=pawns, defs=defs,
                   pawn_detail={"p1": {"drafted": True}},
                   orders={"combat": {"enabled": True}})
    cc.cfg = {"combat": dict(p.get("combat") or {})}

    class _E:
        def goal_sources(self):
            return []

    cands = sel_mod.compile_actions(p, _E(), cc, cc.obs)
    ids = [x["id"] for x in cands if x["scope"] == "pawn"]
    assert "pawn.p1.combat-strike.h1" in ids
    assert "pawn.p1.combat-close.h2" in ids          # h2 out of range
    # h1 in range -> strike offered; h2 out of range -> close offered
    assert "pawn.p1.combat-strike.h2" not in ids
    assert "pawn.p1.combat-close.h1" not in ids
    strike = next(x for x in cands if x["id"].endswith("strike.h1"))
    assert strike["dispatch"] == {"template": "attack-target",
                                  "params": {"pawn": "p1", "target": "h1"}}
    # nearest-first: strike on h1 (dist ~8) outranks close on h2 (~56)
    near = next(x for x in cands if "h1" in x["id"])
    far = next(x for x in cands if "h2" in x["id"])
    assert near["priority"] > far["priority"]


def test_pawn_context_resolves_per_pawn():
    """pawn_scope.context resolvers produce the combat card + the
    nearest-first enemy board per pawn question."""
    from runtime import select as sel_mod, templates
    p = templates.load_pack("combat-defense-v0")["pack"]
    sel = templates.decide_of(p).get("select")
    assert sel["pawn_scope"]["context"]["me"].startswith("@fn:combat_card")
    defs = {"Gun_Revolver": {"stats": {"range": 26, "is_melee": False}}}
    pawns = [c(id="p1", pos=(50, 50), weapon="Gun_Revolver")]
    hostiles = [h(id="h1", pos=(58, 52)), h(id="h2", pos=(90, 90))]
    cc, game = ctx(hostiles=hostiles, pawns=pawns, defs=defs,
                   pawn_detail={"p1": {"drafted": True}},
                   orders={"combat": {"enabled": True}})
    cc.cfg = {"combat": dict(p.get("combat") or {})}

    class _E:
        def goal_sources(self):
            return []

    cands = sel_mod.compile_actions(p, _E(), cc, cc.obs)
    qs = sel_mod.build_questions(cands, cc.obs, sel, None, ctx=cc)
    q = qs["q.pawn.p1"]["context"]
    assert q["me"]["weapon"] == "Gun_Revolver"
    assert q["me"]["range_class"] == "medium"        # 26 > short 12
    assert q["me"]["engages"] is True
    assert [e["id"] for e in q["enemies"]] == ["h1", "h2"]  # nearest-first
    assert q["enemies"][0]["dist"] < q["enemies"][1]["dist"]
    assert q["squad"]["class"] == "ranged"
    assert q["squad"]["focus_target"] == "h1"


def test_range_class_bands():
    """range_class maps weapon range to melee/short/medium/long via
    combat.range_bands (pack-owned thresholds)."""
    defs = {"Gun_Short": {"stats": {"range": 10, "is_melee": False}},
            "Gun_Med": {"stats": {"range": 26, "is_melee": False}},
            "Gun_Long": {"stats": {"range": 45, "is_melee": False}},
            "MeleeKnife": {"stats": {"is_melee": True, "range": 0}}}
    cc, _ = ctx(pawns=[c(id="s", weapon="Gun_Short"),
                       c(id="m", weapon="Gun_Med"),
                       c(id="l", weapon="Gun_Long"),
                       c(id="k", weapon="MeleeKnife"),
                       c(id="u", weapon=None)],
                defs=defs)
    rc = lambda pid: policy.resolve(f"@fn:range_class('{pid}')", cc)
    assert rc("s") == "short"
    assert rc("m") == "medium"
    assert rc("l") == "long"
    assert rc("k") == "melee"
    assert rc("u") == "melee"


def test_direct_command_lifecycle(tmp_path, monkeypatch):
    """direct_command=true: no order-set/force-run; rules draft the
    squad, per-pawn options (fallback head) fight, stand-down after the
    quiet window (Laya-driven path, caller=None -> shadow+fallback)."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for p in ("components/runtime/src", "components/contracts/src"):
        if str(root / p) not in sys.path:
            sys.path.insert(0, str(root / p))
    from runtime.dispatch import Dispatcher
    from runtime.loop import run
    from runtime.simgame import SimGame
    from runtime.tasks import TaskLedger

    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    game = SimGame(established=True)
    game.rpc("dev.incident", {"def": "Raid"})
    records: list[dict] = []
    d = Dispatcher(game, sink=records.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("combat-defense-v0")
    assert d.pack["pack"]["combat"]["direct_command"] is True
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=records.append)
    run(d, game, ledger, d.pack["pack"], iterations=45)

    issued = [e.get("payload", {}).get("template_id") for e in records
              if e.get("event_type") == "action.issued"]
    assert "order-set" not in issued          # delegate order never armed
    assert "order-run" not in issued
    assert "draft-pawn" in issued             # rules draft the squad
    assert not [h for h in game.hostiles
                if not h.get("downed") and not h.get("dead")]
    assert not game.drafted                   # stood down after release


def test_stand_down_flicker_hysteresis():
    """A flickered or failed threats read must not stand pawns down:
    hostile_free_polls counts only consecutive CONFIRMED-empty reads —
    a bad RPC holds the streak, a living hostile resets it."""
    from runtime import templates
    rules = [r for r in (templates.load_pack("combat-defense-v0")["pack"]
                       .get("rules") or [])
             if r["id"] == "combat-stand-down"]
    assert rules
    cc, game = ctx(hostiles=[h(id="h1")], pawns=[c(id="p1")],
                   cfg={"direct_command": True})
    shared = cc.state
    fail = {"on": False}
    orig = game._rpc
    def flaky(m, p):
        return None if fail["on"] and m == "state.threats" \
            else orig(m, p)
    game._rpc = flaky

    def poll(n, tick):
        c2 = policy.Ctx(cfg=cc.cfg, obs=cc.obs, game=game,
                        state=shared, tick=tick, poll=n)
        sink = _Sink()
        fired = policy.run_rules(rules, sink, c2, source="rule")
        return fired, sink

    out, _ = poll(0, 1000)              # h1 alive: streak 0, last=1000
    assert not out
    game.hostiles = []
    for n in range(1, 5):               # clean reads 1..4 — below streak
        out, sink = poll(n, 1000 + n * 200)
        assert not out, f"stand-down fired at streak {n}"
    fail["on"] = True                   # bad read: holds, doesn't count
    out, _ = poll(5, 2000)
    assert not out
    assert policy.resolve("@fn:hostile_free_polls()",
                          cc) == 4      # still 4 — didn't increment
    fail["on"] = False
    out, sink = poll(6, 2200)           # streak 5 -> stand-down fires
    assert out
    assert sink.calls == [("draft-pawn", {"pawn": "p1",
                                          "drafted": False})]
    # flicker: hostile pops back mid-window -> streak resets
    game.hostiles = [h(id="h1")]
    out, _ = poll(7, 2400)
    assert not out
    assert shared["hostile_free_polls"] == 0
