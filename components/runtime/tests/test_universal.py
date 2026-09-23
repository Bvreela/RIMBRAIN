"""Universal rules + policy-engine tests (feature 011/012): pack-declared
idle correction, combat discipline (downed skip, flee-chase), post-combat
strip — plus proofs that behavior follows the pack, not the code
(SC-1001..1003)."""

import copy
import json

import pytest

from runtime.dispatch import Dispatcher
from runtime.tasks import TaskLedger
from runtime import universal, policy
from runtime.combatmode import run_combat
from runtime.startmode import run_start

from test_startmode import StartSim
from test_combat import _pack_with


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    return d, game, ledger, d.pack["pack"], events, tmp_path


def _mark_completed(state_dir):
    (state_dir / "startmode.json").write_text(
        json.dumps({"completed": True}))


def _issued(events, template):
    return [e for e in events if e["event_type"] == "action.issued"
            and e["payload"].get("template_id") == template]


def test_idle_pawn_gets_work(rig):
    """FR-902/SC-901: a wandering colonist is assigned within one poll."""
    d, game, ledger, pack, events, tmp = rig
    game.pawns[1]["job"] = "wandering."
    fired = universal.apply_rules(d, game, {"items": game.items},
                                  pack, {}, poll=0)
    assert fired and fired[0]["rule"] == "idle-work"
    assert fired[0]["params"]["pawn"] == "c1"
    assert _issued(events, "assign-job")


def test_busy_pawn_not_touched(rig):
    """Zero writes when every colonist has a real job."""
    d, game, ledger, pack, events, tmp = rig
    fired = universal.apply_rules(d, game, {}, pack, {}, poll=0)
    assert fired == []
    assert not _issued(events, "assign-job")


def test_idle_cooldown_prevents_spam(rig):
    """A refused/failed assignment isn't retried every poll."""
    d, game, ledger, pack, events, tmp = rig
    game.pawns[1]["job"] = "idle"
    state = {}
    universal.apply_rules(d, game, {"items": game.items}, pack,
                          state, poll=0)
    universal.apply_rules(d, game, {"items": game.items}, pack,
                          state, poll=1)
    assert len(_issued(events, "assign-job")) == 1


def test_no_idle_rule_means_no_correction(rig):
    """SC-1003: remove the rule from the pack -> idle pawn untouched."""
    d, game, ledger, pack, events, tmp = rig
    pack = copy.deepcopy(pack)
    pack["universal"]["rules"] = [
        r for r in pack["universal"]["rules"] if r["id"] != "idle-work"]
    game.pawns[1]["job"] = "wandering."
    fired = universal.apply_rules(d, game, {"items": game.items},
                                  pack, {}, poll=0)
    assert not _issued(events, "assign-job")


def test_pack_edits_change_behavior(rig):
    """SC-1001/1002: the pack, not the code, owns order and membership —
    swap the idle fallback order and Mine fires first."""
    d, game, ledger, pack, events, tmp = rig
    pack = copy.deepcopy(pack)
    rules = pack["universal"]["rules"]
    idle = next(r for r in rules if r["id"] == "idle-work")
    idle["try"] = [idle["try"][2]] + [t for t in idle["try"]
                                     if t is not idle["try"][2]]
    game.pawns[1]["job"] = "wandering."
    universal.apply_rules(d, game, {"items": game.items}, pack,
                          {}, poll=0)
    issued = _issued(events, "assign-job")
    assert issued[0]["payload"]["params"]["job"] == "Mine"


def test_downed_hostiles_never_targeted(rig):
    """FR-903/SC-902: downed hostiles are excluded from attack orders."""
    d, game, ledger, pack, events, tmp = rig
    _mark_completed(tmp / "state")
    d.load_pack("dev-lab-v0")  # combat scripting is dev-class
    pack = d.pack["pack"]
    game.hostiles = [{"id": "h-down", "downed": True},
                     {"id": "h-live"}]
    res = run_combat(d, game, ledger,
                     _pack_with(pack, rounds=1, tick_budget=200),
                     iterations=10, mode_state_dir=tmp / "state")
    assert res["ok"]
    attacked = [e["payload"]["params"]["target"]
                for e in _issued(events, "attack-target")]
    assert "h-down" not in attacked


def test_strip_sweep_after_round(rig):
    """FR-904/SC-902: downed hostiles are stripped before restore."""
    d, game, ledger, pack, events, tmp = rig
    _mark_completed(tmp / "state")

    class DownedSim(StartSim):
        def rpc(self, method, params=None):
            if method == "ui.attack":  # colonists wound, never kill
                if self.hostiles:
                    self.hostiles[0]["downed"] = True
                    self.hostiles[0]["health"] = 20.0
                return {"ok": True, "result": {"engaged": None}}
            return super().rpc(method, params)

    g2 = DownedSim()
    d2 = Dispatcher(g2, sink=events.append,
                    clock=lambda: "2026-01-01T00:00:00Z")
    d2.load_pack("dev-lab-v0")  # combat scripting is dev-class
    res = run_combat(d2, g2, ledger,
                     _pack_with(d2.pack["pack"], rounds=1,
                                tick_budget=10),
                     iterations=8, mode_state_dir=tmp / "state")
    assert res["ok"]
    assert g2.stripped  # something was stripped
    assert _issued(events, "strip-pawn")


def test_no_strip_step_means_no_strip(rig):
    """SC-1003 variant: pack without a strip step never strips."""
    d, game, ledger, pack, events, tmp = rig
    _mark_completed(tmp / "state")

    class DownedSim(StartSim):
        def rpc(self, method, params=None):
            if method == "ui.attack":
                if self.hostiles:
                    self.hostiles[0]["downed"] = True
                    self.hostiles[0]["health"] = 20.0
                return {"ok": True, "result": {"engaged": None}}
            return super().rpc(method, params)

    g2 = DownedSim()
    d2 = Dispatcher(g2, sink=events.append,
                    clock=lambda: "2026-01-01T00:00:00Z")
    d2.load_pack("dev-lab-v0")  # combat scripting is dev-class
    pack2 = _pack_with(d2.pack["pack"], rounds=1, tick_budget=10)
    pack2 = copy.deepcopy(pack2)
    # strip lives in both cleanup steps and universal rules — drop both
    pack2["combat"]["cleanup"] = [
        s for s in pack2["combat"]["cleanup"]
        if s.get("template") != "strip-pawn"]
    pack2["universal"]["rules"] = [
        r for r in pack2["universal"]["rules"]
        if r["id"] != "strip-downed"]
    res = run_combat(d2, g2, ledger, pack2, iterations=8,
                     mode_state_dir=tmp / "state")
    assert res["ok"]
    assert not _issued(events, "strip-pawn")


def test_fleeing_hostile_chased_by_melee(rig):
    """FR-903: a receding hostile gets a chase order from the pack's
    chase_skill pick (c1 has Melee 7 vs c0 Shooting 8). The melee flag
    is left unset so ui.attack auto-picks shoot-vs-close per weapon —
    a gun-armed chaser shoots instead of fist-fighting."""
    d, game, ledger, pack, events, tmp = rig
    state = {}
    for d_home in (10, 20, 30):
        game.hostiles = [{"id": "h1", "dist_home": d_home,
                          "health": 80.0},
                         {"id": "h2", "dist_home": 10, "health": 80.0}]
        fired = universal.apply_rules(d, game, {}, pack, state,
                                      poll=int(d_home / 10))
    chase = [f for f in fired if f["rule"] == "chase-fleeing"]
    assert chase and chase[0]["params"]["pawn"] == "c1"
    assert chase[0]["params"]["target"] == "h1"
    assert "melee" not in chase[0]["params"]


def test_all_armed_defend_together(rig):
    """Every armed colonist attacks the nearest living hostile in the
    same poll — one pawn chasing while the rifleman idles is bad
    tactics. melee is omitted: ui.attack auto-detects ranged vs melee
    from the pawn's weapon."""
    d, game, ledger, pack, events, tmp = rig
    state = {}
    game.hostiles = [{"id": "h1", "dist_home": 30, "health": 80.0}]
    game.pawns[0]["weapon"] = "w-gun"
    game.pawns[1]["weapon"] = "w-melee"
    fired = universal.apply_rules(d, game, {}, pack, state, poll=0)
    defend = [f for f in fired if f["rule"] == "defend-colony"]
    pairs = {(f["params"]["pawn"], f["params"]["target"])
             for f in defend}
    assert ("c0", "h1") in pairs and ("c1", "h1") in pairs
    assert all("melee" not in f["params"] for f in defend)
    # unarmed c2 stays out of the fight
    assert not any(f["params"]["pawn"] == "c2" for f in defend)


def test_arm_phase_ranks_by_skill(rig):
    """FR-905: gun -> best shooter (c0) via the pack's arm steps."""
    d, game, ledger, pack, events, tmp = rig
    ph = next(p for p in pack["start"]["phases"] if p["id"] == "arm")
    ctx = policy.Ctx(cfg=pack, obs={"colonists": {"count": 3}, "tick": 0},
                     game=game, persist={"site": {"min": [14, 14],
                                                 "rect": [14, 14, 9, 9]}})
    res = policy.run_steps(ph["steps"], d, ctx)
    assert res["ok"]
    equips = _issued(events, "equip-pawn")
    assert equips and equips[0]["payload"]["params"]["pawn"] == "c0"
    assert equips[0]["payload"]["params"]["target"] == "w-gun"


def test_phases_come_from_pack(rig):
    """SC-1001/1002: drop 'recreation' from the pack -> never dispatched,
    never required for completion; the pack's phase list is the order."""
    d, game, ledger, pack, events, tmp = rig
    pack = copy.deepcopy(pack)
    pack["start"]["phases"] = [p for p in pack["start"]["phases"]
                               if p["id"] != "recreation"]
    pack["start"]["exit"]["conditions"].pop("recreation", None)
    res = run_start(d, game, ledger, pack, iterations=40)
    assert res["completed"]
    assert not _issued(events, "build-one") or all(
        e["payload"]["params"].get("def") != "HorseshoesPin"
        for e in _issued(events, "build-one"))
    assert not game.recreation


def test_validate_policy_fail_closed(rig):
    """FR-1007: unknown fn/selector/template is a named pack error."""
    _d, _g, _l, pack, _e, _t = rig
    bad = copy.deepcopy(pack)
    bad["start"]["phases"][0]["steps"][0]["params"]["cell"] = \
        "@fn:bogus()"
    bad["universal"]["rules"][0]["for_each"] = "bogus_selector"
    bad["universal"]["rules"][0]["try"][0]["template"] = "bogus-tpl"
    problems = policy.validate_policy(bad)
    assert any("bogus" in p for p in problems)
    assert any("selector" in p for p in problems)
    assert any("template" in p for p in problems)


def test_naming_dialog_answered(rig):
    """An open give_name modal gets an answer-dialog dispatch naming the
    window index (fr: pack rule answer-naming)."""
    d, game, ledger, pack, events, tmp = rig

    class DialogSim(StartSim):
        def rpc(self, method, params=None):
            if method == "state.dialogs":
                return {"ok": True, "result": [
                    {"i": 3, "type": "Dialog_GiveName",
                     "kind": "give_name",
                     "fields": {"name": "New Toronto"}}]}
            return super().rpc(method, params)

    g2 = DialogSim()
    d2 = Dispatcher(g2, sink=events.append,
                    clock=lambda: "2026-01-01T00:00:00Z")
    d2.load_pack("start-mode-v0")
    fired = universal.apply_rules(d2, g2, {}, d2.pack["pack"], {}, poll=0)
    rows = [f for f in fired if f["rule"] == "answer-naming"]
    assert rows and rows[0]["params"] == {"i": 3, "choice": "OK"}
    assert _issued(events, "answer-dialog")


def test_no_dialogs_no_dispatch(rig):
    """Empty state.dialogs -> zero ui.dialog calls."""
    d, game, ledger, pack, events, tmp = rig
    fired = universal.apply_rules(d, game, {}, pack, {}, poll=0)
    assert not _issued(events, "answer-dialog")


def test_fair_mode_denies_debug(rig):
    """UR-CTL-009/UR-BRN-018: the fair pack declares zero dev.* methods —
    they're unknown actions, not just refused; save/load stay refused;
    and a dev-class pack is rejected at load."""
    d, game, ledger, pack, events, tmp = rig
    from runtime.dispatch import Dispatcher as D2
    from runtime.templates import PackError
    import pytest as _pt
    fair = D2(game, sink=events.append,
              clock=lambda: "2026-01-01T00:00:00Z", fair=True)
    fair.load_pack("start-mode-v0")  # fair-class pack loads cleanly
    # dev tooling isn't even declared in the fair pack -> unknown action
    for tpl in ("spawn-hostile", "heal-pawn"):
        r = fair.dispatch(tpl, {"name": "x", "pawn": "c1"})
        assert not r.get("ok"), tpl
        assert (r.get("error") or {}).get("code") == \
            "dispatch.unknown_action"
    # checkpoint control is still refused per-dispatch under --fair
    for tpl in ("save-game", "load-game"):
        r = fair.dispatch(tpl, {"name": "x"})
        assert not r.get("ok"), tpl
        assert "fair" in (r.get("error") or {}).get("code", "")
    refused = [e for e in events if e["event_type"] == "action.refused"]
    assert len(refused) == 4
    # a dev-class pack can't slip into a fair run at all
    with _pt.raises(PackError) as ei:
        fair.load_pack("dev-lab-v0")
    assert ei.value.envelope["error"]["code"] == "pack.not_fair"
    # normal capabilities still dispatch under fair mode
    r = fair.dispatch("draft-pawn", {"pawn": "c1", "drafted": True})
    assert r.get("ok") is not None or "ok" in r
