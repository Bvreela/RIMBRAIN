"""Canonical per-poll observation (feature 017; FR-1406).

One observation per poll consumed by every stage — reflexes, rules,
action-list compilation, planner digests, vitals, and views. Merges the
three historical producers: ``planloop.observe`` (status + enrich),
the former ``startmode.observe_start`` measured fields, and the caller's
latest ``vitals.sample`` output under ``obs["vitals"]``.

The dict keeps every legacy flat key stable — ``@obs:`` resolvers in
packs read ``colonists``, ``items``, ``blueprints``, ``stocks``,
``rooms``, ``open_rects``, measured fields — while ``sections(obs)``
projects the digest-friendly view ``{tick, colony, pawns, map, stocks,
threats}`` for planner/select inputs.
"""

from __future__ import annotations

from .planloop import observe as _base_observe


def _things(res) -> list:
    t = res.get("things") if isinstance(res, dict) else None
    return t if isinstance(t, list) else []


def observe(game, cfg: dict | None = None, *,
            vitals: dict | None = None,
            combat: dict | None = None) -> dict:
    """Canonical obs dict: enriched state + storage/rooms/stocks/base +
    loose+forbidden items + blueprints (+frames) + footprint-aware open
    rects + measured fields whose def lists come from pack cfg. Missing
    rpcs degrade to empty — predicates read as not-held (fail-closed).
    `vitals` attaches the caller's latest health sample."""
    obs = _base_observe(game)
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
    # feature 019: project the delegate standing-order's state into obs
    # so pack rules/options gate on the order's own lifecycle. Only when
    # the pack declares combat.delegate_order — read-only surface.
    ocfg = combat if isinstance(combat, dict) \
        else ((cfg or {}).get("combat") or {})
    oid = ocfg.get("delegate_order") if isinstance(ocfg, dict) else None
    if oid:
        st = game.rpc("steward.status")
        st = st.get("result") if st.get("ok") else {}
        row = next((o for o in ((st or {}).get("orders") or [])
                    if isinstance(o, dict)
                    and str(o.get("id")) == str(oid)), None)
        ex = game.rpc("steward.orders.explain", {"id": oid})
        ex = ex.get("result") if ex.get("ok") else {}
        obs["orders"] = {str(oid): {**(row or {}),
                                   "explain": ex if isinstance(ex, dict)
                                   else {}}}
    if vitals:
        obs["vitals"] = vitals
    return obs


def observe_combat(game, combat: dict | None = None) -> dict:
    """Lean per-poll obs for combat engage loops: status + enriched
    roster/fires (base), live areas, home anchor, and the delegate-order
    projection. Skips storage/rooms/stocks/items/blueprints/site/beds/
    cooking sections the engage rules never read — polls stay cheap so
    ticks go to dispatching actions, not watching (feature 019)."""
    obs = _base_observe(game)
    for name, rpc in (("areas", "state.areas"),
                      ("base", "state.base")):
        r = game.rpc(rpc)
        obs[name] = r.get("result") if r.get("ok") else {}
    base = obs.get("base")
    if isinstance(base, dict) and base.get("home_center"):
        obs["home_center"] = base["home_center"]
    oid = (combat or {}).get("delegate_order")
    if oid:
        st = game.rpc("steward.status")
        st = st.get("result") if st.get("ok") else {}
        row = next((o for o in ((st or {}).get("orders") or [])
                    if isinstance(o, dict)
                    and str(o.get("id")) == str(oid)), None)
        ex = game.rpc("steward.orders.explain", {"id": oid})
        ex = ex.get("result") if ex.get("ok") else {}
        obs["orders"] = {str(oid): {**(row or {}),
                                   "explain": ex if isinstance(ex, dict)
                                   else {}}}
    return obs


# Back-compat name during the startmode -> PhaseEngine migration.
observe_start = observe


def sections(obs: dict) -> dict:
    """Digest-friendly projection for planner/select inputs — stable
    compact sections derived from the same canonical obs (no new RPCs)."""
    colonists = obs.get("colonists") if isinstance(
        obs.get("colonists"), dict) else {"count": obs.get("colonists")}
    roster = obs.get("colonist_list") or obs.get("pawns") or []
    fires = ((obs.get("map") or {}).get("fires")
             if isinstance(obs.get("map"), dict) else None)
    return {
        "tick": obs.get("tick"),
        "colony": {
            "colonists": colonists.get("count"),
            "downed": colonists.get("downed"),
            "mood_avg": obs.get("mood_avg")
                        or (obs.get("summary") or {}).get("mood_avg"),
            "beds_total": obs.get("beds_total"),
            "zone_count": obs.get("zone_count"),
            "food_source_present": obs.get("food_source_present"),
            "meals_present": obs.get("meals_present"),
            "paused": obs.get("paused"),
            "speed": obs.get("speed"),
        },
        "pawns": roster,
        "map": {
            "open_rects": obs.get("open_rects") or [],
            "blueprint_count": (obs.get("blueprints") or {}).get("count")
                if isinstance(obs.get("blueprints"), dict) else None,
            "home_center": obs.get("home_center"),
            "anchors": obs.get("anchors"),
        },
        "stocks": obs.get("stocks") or {},
        "threats": {
            "fires": fires,
            "fire_cell": (obs.get("map") or {}).get("fire_cell")
                if isinstance(obs.get("map"), dict) else None,
            "downed_id": colonists.get("downed_id"),
            "hostiles": obs.get("hostiles") or obs.get("threats"),
        },
        "vitals": obs.get("vitals") or {},
    }
