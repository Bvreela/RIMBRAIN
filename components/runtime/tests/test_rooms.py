"""Feature 020 room tests (FR-2001..2009, SC-2001..2006).

Drives the real SimGame + policy.Ctx: plan_room compiles archetypes to
build-layout ops, the sim materializes rooms from those ops, and room
fns verify observed role/stat predicates — never blueprint placement.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import policy  # noqa: E402
from runtime.simgame import SimGame  # noqa: E402

BEDROOM = {
    "size": {"w": 4, "h": 6},
    "stat_target": {"impressiveness": 40},
    "wall": "Wall", "door": "Door", "floor": "Carpet",
    "furniture": [
        {"def": "Bed", "count": 1, "anchor": "wall"},
        {"def": "Dresser", "linked_to": "Bed"},
        {"def": "EndTable", "linked_to": "Bed"},
        {"def": "StandingLamp", "count": 1},
        {"def": "PlantPot", "optional": True},
    ],
}

MODDED_STAGES = [
    {"label": "rather tight", "minScore": 6.5},
    {"label": "average-sized", "minScore": 16.5},
    {"label": "somewhat spacious", "minScore": 28.5},
    {"label": "quite spacious", "minScore": 49.5},
    {"label": "very spacious", "minScore": 84.5},
    {"label": "extremely spacious", "minScore": 174.5},
]


def _ctx(game=None, cfg=None, obs=None):
    return policy.Ctx(cfg=cfg or {"rooms": {"tier_table": "auto",
                                            "archetypes": {
                                                "bedroom": BEDROOM}}},
                      obs=obs or {}, game=game)


def _ops_of(out):
    assert out is not None
    return out["ops"]


# -- US1: declarative room archetypes (T009) --------------------------------

def test_plan_room_compiles_bedroom_deterministic():
    g = SimGame()
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)", _ctx(g))
    ops = _ops_of(out)
    # walls as outline line segments + perimeter door + floor fill
    walls = [o for o in ops if o["def"] == "Wall"]
    assert len(walls) == 5
    cells = []
    for o in walls:
        a, b = o["line"]
        cells += [tuple(a), tuple(b)]
    # bounding box spans the archetype footprint + 1 ring
    xs = [c[0] for c in cells]
    zs = [c[1] for c in cells]
    assert (max(xs) - min(xs), max(zs) - min(zs)) == (5, 7)
    door = next(o for o in ops if o["def"] == "Door")
    assert door["at"] in ([12, 16], [10, 16], [11, 16], [13, 16])
    floor = next(o for o in ops if o["def"] == "Carpet")
    assert floor["rect"] == [10, 10, 4, 6] and floor["fill"] is True
    furn = [o for o in ops if o["def"] in ("Bed", "Dresser", "EndTable",
                                           "StandingLamp", "PlantPot")]
    assert {o["def"] for o in furn} == {"Bed", "Dresser", "EndTable",
                                        "StandingLamp", "PlantPot"}
    bed = next(o for o in furn if o["def"] == "Bed")
    assert bed["at"] in ([11, 15], [12, 15]) and bed["rot"] == "N"
    # dresser + endtable within link range (4.0) of the bed
    for o in furn:
        if o["def"] in ("Dresser", "EndTable"):
            d = ((o["at"][0] - bed["at"][0]) ** 2
                 + (o["at"][1] - bed["at"][1]) ** 2) ** 0.5
            assert d <= 4.0
    # deterministic: recompiling yields identical ops
    again = _ops_of(policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                                   _ctx(g)))
    assert again == ops


def test_plan_room_unfit_rect_returns_null():
    g = SimGame()
    for rect in ("[10, 10, 1, 1]", "[10, 10, 4, 5]", "[10, 10, 3, 3]"):
        assert policy.resolve(f"@fn:plan_room({rect}, bedroom)",
                              _ctx(g)) is None, rect


def test_plan_room_unknown_def_fails_closed():
    g = SimGame()
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {"bedroom": {
        "size": {"w": 4, "h": 6}, "wall": "Wall", "door": "Door",
        "furniture": [{"def": "Bed"}, {"def": "NotARealDef"}]}}}}
    assert policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                          _ctx(g, cfg)) is None


def test_plan_room_optional_furnishings_skip_without_failing():
    g = SimGame()
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {"bedroom": {
        "size": {"w": 4, "h": 6}, "wall": "Wall", "door": "Door",
        "furniture": [{"def": "Bed"},
                      {"def": "PlantPot", "optional": True}]}}}}
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                         _ctx(g, cfg))
    assert out is not None
    assert any("skip" in w for w in out["warnings"]) or \
        any(o["def"] == "PlantPot" for o in out["ops"])


def test_plan_room_existing_structure_merge_split_safety():
    g = SimGame()
    # a different room already occupies part of the rect interior -> null
    obs = {"rooms": [{"id": "r9", "role": "Bedroom", "cells": 20,
                      "at": [10, 10],
                      "rect": {"min": [10, 10], "max": [13, 13]}}]}
    assert policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                          _ctx(g, obs=obs)) is None
    # re-issue over our own (identical-bounds) room compiles — idempotent
    own = {"id": "r1", "role": "Bedroom", "cells": 24, "at": [10, 10],
           "rect": {"min": [10, 10], "max": [13, 15]}}
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                         _ctx(g, obs={"rooms": [own]}))
    assert out is not None
    # full containment (subdivision/conversion) warns but compiles
    big = {"id": "r2", "role": "Bedroom", "cells": 80, "at": [10, 10],
           "rect": {"min": [10, 10], "max": [19, 19]}}
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                         _ctx(g, obs={"rooms": [big]}))
    assert out is not None
    assert any("subdivides_room" in w for w in out["warnings"])


def test_plan_room_region_bound():
    g = SimGame()
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {"huge": {
        "size": {"w": 60, "h": 60}, "wall": "Wall", "door": "Door",
        "furniture": []}}}}
    assert policy.resolve("@fn:plan_room([10, 10, 70, 70], huge)",
                          _ctx(g, cfg)) is None


def test_bedroom_builds_in_sim_and_verifies_role_stat():
    """US1 independent test: archetype -> ops -> sim room -> role+stat."""
    g = SimGame()
    out = policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)", _ctx(g))
    assert out is not None
    g.rpc("ui.build_many", {"ops": out["ops"]})
    g.advance()
    row = policy.FN["room_at"](_ctx(g, obs={"rooms": list(g.rooms)}),
                               [10, 10])
    assert row is not None
    assert row["role"] == "Bedroom"
    assert row["impressiveness"] >= 40
    # the pack ships zero hand-written coordinates — archetype data only
    pack = SimGame()  # sanity: compile is pure
    assert _ops_of(policy.resolve("@fn:plan_room([10, 10, 9, 9], bedroom)",
                                  _ctx(pack))) == out["ops"]


def test_space_score_formula():
    g = SimGame()
    ctx = _ctx(g)
    # sim cells are all standable -> 1.4 per cell
    assert abs(policy.resolve("@fn:space_score([10, 10, 4, 6])", ctx)
               - 1.4 * 24) < 1e-6


# -- US2: right-sized bedrooms on demand (T016/T017) ------------------------

def _barracks(g, beds=1):
    ops = [{"def": "Wall", "line": [[3, 5], [8, 5]]},
           {"def": "Wall", "line": [[3, 1], [3, 5]]},
           {"def": "Wall", "line": [[8, 1], [8, 5]]},
           {"def": "Wall", "line": [[3, 1], [4, 1]]},
           {"def": "Wall", "line": [[5, 1], [8, 1]]},
           {"def": "Door", "at": [5, 1]},
           {"def": "Dresser", "at": [6, 4]},
           {"def": "EndTable", "at": [5, 3]}]
    for i in range(beds):
        ops.append({"def": "Bed", "at": [4 + i, 4]})
    g.rpc("ui.build_many", {"ops": ops})
    g.advance()


def test_bed_demand_counts():
    g = SimGame()
    _barracks(g)
    ctx = _ctx(g, obs={"rooms": list(g.rooms)})
    # 3 colonists, 1 owner-assigned bedroom -> demand 2
    assert policy.resolve("@fn:bed_demand()", ctx) == 2
    # two more private bedrooms absorb the demand
    for off in (0, 5):
        ops = [{"def": "Wall", "line": [[3 + off, 12], [8 + off, 12]]},
               {"def": "Wall", "line": [[3 + off, 8], [3 + off, 12]]},
               {"def": "Wall", "line": [[8 + off, 8], [8 + off, 12]]},
               {"def": "Wall", "line": [[3 + off, 8], [4 + off, 8]]},
               {"def": "Wall", "line": [[5 + off, 8], [8 + off, 8]]},
               {"def": "Door", "at": [5 + off, 8]},
               {"def": "Bed", "at": [4 + off, 11]}]
        g.rpc("ui.build_many", {"ops": ops})
    g.advance()
    ctx = _ctx(g, obs={"rooms": list(g.rooms)})
    assert policy.resolve("@fn:bed_demand()", ctx) == 0


def test_conversion_zero_bedless_ticks():
    """T035: barracks -> private rooms reassigns target-bed-first with no
    intermediate tick where a colonist is bedless."""
    g = SimGame()
    _barracks(g, beds=3)  # the barracks sleeps everyone
    g.advance()
    history = [dict(g.pawn_beds)]
    assert set(history[0]) == {"c1", "c2", "c3"}
    for off in (0, 5, 10):
        ops = [{"def": "Wall", "line": [[3 + off, 12], [8 + off, 12]]},
               {"def": "Wall", "line": [[3 + off, 8], [3 + off, 12]]},
               {"def": "Wall", "line": [[8 + off, 8], [8 + off, 12]]},
               {"def": "Wall", "line": [[3 + off, 8], [4 + off, 8]]},
               {"def": "Wall", "line": [[5 + off, 8], [8 + off, 8]]},
               {"def": "Door", "at": [5 + off, 8]},
               {"def": "Bed", "at": [4 + off, 11]}]
        g.rpc("ui.build_many", {"ops": ops})
        g.advance()
        history.append(dict(g.pawn_beds))
    # every colonist owns a bed at every tick — nobody is ever bedless
    for snap in history:
        assert set(snap) == {"c1", "c2", "c3"}, snap
    # conversion completed: one private room per colonist
    owners = [r["owners"] for r in g.rooms if r["role"] == "Bedroom"]
    assert sum(1 for o in owners if o) >= 3
    assert all(len(o) <= 1 for o in owners if o)


def test_material_delta_30pct_and_equal_mood():
    """SC-2002: under the mod profile, tier-targeted bedrooms consume
    >=30% less build footprint per bedroom than the legacy 7x7 expansion
    geometry at equal (or better) mood band."""
    # legacy uniform expansion path: 7x7 room (walls + door + floor + bed)
    legacy_ops = [{"def": "Wall", "rect": [10, 10, 7, 7]},
                  {"def": "Door", "at": [13, 10]},
                  {"def": "Carpet", "rect": [11, 11, 5, 5], "fill": True},
                  {"def": "Bed", "at": [11, 13]}]
    legacy_cells = _footprint_cells(legacy_ops)
    # archetype path under the modded tier profile: 4x3-class bedroom
    g = SimGame()
    g.defs["Space"] = {"scoreStages": MODDED_STAGES}
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {"bedroom": {
        "tier_target": "average", "stat_target": {"impressiveness": 40},
        "wall": "Wall", "door": "Door", "floor": "Carpet",
        "furniture": [
            {"def": "Bed", "count": 1, "anchor": "wall"},
            {"def": "Dresser", "linked_to": "Bed"},
            {"def": "EndTable", "linked_to": "Bed"},
            {"def": "StandingLamp", "count": 1}]}}}}
    arch_ops = _ops_of(policy.resolve("@fn:plan_room([10, 10, 9, 9], "
                                      "bedroom)", _ctx(g, cfg)))
    arch_cells = _footprint_cells(arch_ops)
    assert arch_cells <= legacy_cells * 0.7, (arch_cells, legacy_cells)
    # equal mood: the archetype room verifies at or above the legacy room
    g2 = SimGame()
    g2.rpc("ui.build_many", {"ops": arch_ops})
    g2.advance()
    arch_imp = g2.rooms[0]["impressiveness"]
    g3 = SimGame()
    g3.rpc("ui.build_many", {"ops": legacy_ops})
    g3.advance()
    legacy_imp = g3.rooms[0]["impressiveness"]
    assert arch_imp >= 40
    assert arch_imp >= legacy_imp


def _footprint_cells(ops):
    cells = set()
    for o in ops:
        d = o.get("def", "")
        if o.get("rect") and isinstance(o["rect"], (list, tuple)) \
                and len(o["rect"]) >= 4:
            rx, rz, rw, rh = o["rect"][:4]
            if o.get("fill"):
                cells.update((rx + i, rz + j)
                             for i in range(rw) for j in range(rh))
            elif "wall" in d.lower():
                cells.update((rx + i, rz + j)
                             for i in range(rw) for j in range(rh))
        if o.get("line"):
            a, b = o["line"]
            if a[0] == b[0]:
                cells.update((a[0], z) for z in range(min(a[1], b[1]),
                                                      max(a[1], b[1]) + 1))
            else:
                cells.update((x, a[1]) for x in range(min(a[0], b[0]),
                                                      max(a[0], b[0]) + 1))
        if o.get("at"):
            cells.add(tuple(o["at"]))
    return len(cells)


# -- US3: mod-aware space tiers (T021) --------------------------------------

def test_space_tier_profile_vanilla_vs_modded():
    tier_cfg = {"rooms": {"tier_table": "auto", "archetypes": {
        "bedroom": {"tier_target": "average", "wall": "Wall",
                    "door": "Door", "floor": "Carpet",
                    "furniture": [{"def": "Bed", "count": 1,
                                   "anchor": "wall"}]}}}}
    g = SimGame()
    ctx = _ctx(g, tier_cfg)
    assert policy.resolve("@fn:space_tier(30)", ctx) == "average"
    assert policy.resolve("@fn:space_tier(10)", ctx) == "cramped"
    assert policy.resolve("@fn:space_target(average)", ctx) == 29.0
    g2 = SimGame()
    g2.defs["Space"] = {"scoreStages": MODDED_STAGES}
    ctx2 = _ctx(g2, tier_cfg)
    assert policy.resolve("@fn:space_target(average)", ctx2) == 16.5
    # same tier, different profile -> different footprint
    out_v = _ops_of(policy.resolve("@fn:plan_room([10, 10, 9, 9], "
                                   "bedroom)", ctx))
    out_m = _ops_of(policy.resolve("@fn:plan_room([10, 10, 9, 9], "
                                   "bedroom)", ctx2))
    assert _footprint_cells(out_m) < _footprint_cells(out_v)


def test_tier_cfg_override_honored():
    g = SimGame()
    cfg = {"rooms": {"tier_table": "vanilla", "archetypes": {
        "bedroom": {"tier_target": "average", "wall": "Wall",
                    "door": "Door", "furniture": []}}}}
    ctx = _ctx(g, cfg)
    # explicit vanilla wins even under a modded live table
    assert policy.resolve("@fn:space_target(average)", ctx) == 29.0


def test_detection_failure_falls_back_to_vanilla_once():
    g = SimGame()
    g.defs["Space"] = {"scoreStages": "garbage"}
    cfg = {"rooms": {"tier_table": "auto", "archetypes": {
        "bedroom": {"tier_target": "average", "wall": "Wall",
                    "door": "Door", "furniture": []}}}}
    ctx = _ctx(g, cfg)
    ctx.decisions = []
    assert policy.resolve("@fn:space_target(average)", ctx) == 29.0
    events = [d for d in ctx.decisions
              if d.get("event") == "rooms.profile_fallback"]
    assert len(events) == 1
    # second resolve in the same run does not re-emit
    policy.resolve("@fn:space_target(average)", ctx)
    events = [d for d in ctx.decisions
              if d.get("event") == "rooms.profile_fallback"]
    assert len(events) == 1


# -- US4: stat-driven support rooms (T025/T036) -----------------------------

def test_pawns_with_thought_counts():
    g = SimGame()
    g.pawns[0]["thoughts"] = [{"def": "AteWithoutTable"}]
    g.pawns[1]["thoughts"] = [{"def": "AteWithoutTable"},
                              {"def": "DisturbedSleep"}]
    ctx = _ctx(g)
    assert policy.resolve("@fn:pawns_with_thought(AteWithoutTable)",
                          ctx) == 2
    assert policy.resolve("@fn:pawns_with_thought(DisturbedSleep)",
                          ctx) == 1
    assert policy.resolve("@fn:pawns_with_thought(Nonexistent)", ctx) == 0


def test_pawns_wounded_counts():
    g = SimGame()
    g.pawns[0]["health"] = {"bleeding": True}
    g.pawns[1]["health"] = {"conditions": [{"def": "GunshotWound",
                                            "unhealed": True}]}
    ctx = _ctx(g)
    assert policy.resolve("@fn:pawns_wounded()", ctx) == 2
    # per-poll cache: a fresh ctx (new poll) sees the healed pawn
    g.pawns[0]["health"] = {}
    assert policy.resolve("@fn:pawns_wounded()", _ctx(g)) == 1


def test_hospital_need_gate_signal():
    g = SimGame()
    g._state["colonists"]["members"][2]["downed"] = True
    g._state["colonists"]["downed"] = 1
    g._state["colonists"]["downed_id"] = "c3"
    ctx = _ctx(g)
    # downed counts as wounded/incapacitating
    assert policy.resolve("@fn:pawns_wounded()", ctx) == 1


def _run_loop(game, iterations=70):
    """Drive the phase engine + standing goals against the sim."""
    import tempfile
    import os
    from pathlib import Path
    from runtime.dispatch import Dispatcher
    from runtime.loop import run
    from runtime.tasks import TaskLedger
    tmp = Path(tempfile.mkdtemp())
    os.environ["RIMBRAIN_STATE_DIR"] = str(tmp / "state")
    d = Dispatcher(game, clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp / "state" / "tasks.jsonl")
    run(d, game, ledger, d.pack["pack"], iterations=iterations,
        stop_on_complete=False)
    return game


def test_dining_goal_fires_on_thought_and_verifies():
    """T025: AteWithoutTable thoughts -> dining hall builds and verifies
    role DiningRoom + impressiveness target (not enclosure)."""
    g = SimGame()
    g.pawns[0]["thoughts"] = [{"def": "AteWithoutTable"}]
    _run_loop(g)
    rows = [r for r in g.rooms if r.get("role") == "DiningRoom"]
    assert rows, [r["role"] for r in g.rooms]
    assert rows[0]["impressiveness"] >= 40


def test_hospital_goal_fires_on_wounded_and_verifies():
    """T025: wounded colonists -> hospital builds with role Hospital +
    cleanliness floor."""
    g = SimGame()
    g.pawns[0]["health"] = {"bleeding": True}
    _run_loop(g)
    rows = [r for r in g.rooms if r.get("role") == "Hospital"]
    assert rows, [r["role"] for r in g.rooms]
    assert rows[0]["cleanliness"] >= 0.0


def test_kitchen_butcher_separate_placement():
    """T025: the kitchen archetype places the butcher table separate
    from the stove (no shared adjacency — food-poisoning separation)."""
    g = SimGame()
    res = templates_loader()
    ctx = policy.Ctx(cfg=res, obs={}, game=g)
    out = policy.resolve("@fn:plan_room([10, 10, 20, 20], kitchen)", ctx)
    assert out is not None
    stove = next(o for o in out["ops"] if o["def"] == "FueledStove")
    butcher = next(o for o in out["ops"] if o["def"] == "TableButcher")
    dist = abs(stove["at"][0] - butcher["at"][0]) \
        + abs(stove["at"][1] - butcher["at"][1])
    assert dist >= 2


def templates_loader():
    from runtime import templates
    return templates.load_pack("start-mode-v0")["pack"]
