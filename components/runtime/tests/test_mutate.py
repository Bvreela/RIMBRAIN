"""Live pack-mutation tests (feature 016; FR-1401..1411).

Unit tests drive mutate.py directly; the integration tests run
``run_start(live_mutate=True)`` against StartSim with the packs dir and
state dir redirected to tmp (monkeypatched env), so candidate/lineage
writes never touch the repo or a real pack file.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import mutate, packmut, templates  # noqa: E402
from runtime.dispatch import Dispatcher  # noqa: E402
from runtime.tasks import TaskLedger  # noqa: E402

from test_startmode import StartSim  # noqa: E402
from runtime.startmode import run_start  # noqa: E402


def _env(t, payload, seq=1):
    return {"schema_version": 0, "event_id": f"e-{seq}",
            "sequence": seq, "event_type": t, "payload": payload,
            "game_tick": 1, "wall_time_utc": "t", "source": "test"}


def _transition(tid, to_state, seq=1):
    return _env("task.transition",
                {"task_id": tid, "to_state": to_state}, seq)


MINI = {
    "schema_version": 0, "pack_id": "pack.mini", "revision": "v0",
    "templates": [{"id": "ping", "method": "game.status",
                   "params_schema": {}}],
    "jobs": [], "decision_map": [], "emergency": [],
    "govern": {"goals": [{"id": "keep", "retry_polls": 5,
                          "effect": {"field": "x"}, "steps": []}]},
    "mutate": {"goals_per_pass": 3, "on_failure": True,
               "near_failure": {"requeues": 2, "refusals": 3,
                                "blocked_polls": 2, "escalate": True},
               "cooldown_polls": 5, "max_passes_per_run": 4,
               "max_ops": 5},
}


def _loaded(pack=None):
    pack = pack or MINI
    return {"pack": pack, "hash": templates._hash_of(pack),
            "path": "mini.yaml"}


def _stub_dispatcher(pack=None):
    d = Dispatcher(None, clock=lambda: "2026-01-01T00:00:00Z")
    d._pack = _loaded(pack)
    d._pack_file = "mini"
    return d


class _Ledger:
    def __init__(self):
        self.tasks = {}
        self._events = 0


def _resolver_endpoint(name, **kw):
    return {"ok": True,
            "resolved": {"endpoint_id": "test-ep", "model": "m-test",
                         "api": "openai-compat"},
            "degraded": False, "tried": []}


def _resolver_rules(name, **kw):
    return {"ok": True,
            "resolved": {"kind": "fallback", "name": "rules-only"},
            "degraded": True, "reason": "fallback", "tried": []}


def _resolver_broken(name, **kw):
    return {"ok": False, "error": {"code": "bindings.unresolved",
                                   "message": "no role"}}


def _chat_ok(endpoint_id, model, messages, usage_tracker=None):
    return {"ok": True, "body": {
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "choices": [{"message": {"content": json.dumps({
            "mutation_id": "mut.test-bump",
            "analysis": {"failure_paths": ["govern.keep stalling"],
                         "likely_paths": ["repeat refusals"]},
            "mutations": [{"op": "set",
                           "path": "govern.goals.keep.retry_polls",
                           "value": 9}],
            "rationale": "longer backoff"})}}]}}


def _chat_bad(endpoint_id, model, messages, usage_tracker=None):
    return {"ok": True, "body": {
        "choices": [{"message": {"content": "not json at all"}}]}}


def _chat_broken(*a, **kw):
    return {"ok": False, "error": {"code": "endpoint.down",
                                   "message": "offline"}}


def _maybe(ps, dispatcher=None, ledger=None, pack=None, poll=10,
           state_dir=None, emit=None, **kw):
    pack = pack or MINI
    state_dir = state_dir or Path.cwd()
    return mutate.maybe_trigger(
        ps, dispatcher=dispatcher or _stub_dispatcher(pack),
        ledger=ledger or _Ledger(),
        pack_loaded=_loaded(pack), pack=pack, pack_id="mini",
        state_dir=state_dir, tick=1, poll=poll, fair=False,
        emit=emit or (lambda e: None), **kw)


# -- triggers -----------------------------------------------------------------

def test_cadence_fires_after_n_terminal_goals():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    for i in range(2):
        ps.note(_transition(f"govern.g{i}", "succeeded", i))
    assert mutate.check_triggers(ps, MINI, poll=10) == (None, {})
    ps.note(_transition("govern.g2", "succeeded", 3))
    reason, ev = mutate.check_triggers(ps, MINI, poll=10)
    assert reason == "cadence" and ev["terminal_goals"] == 3


def test_failure_trigger_immediate():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    reason, ev = mutate.check_triggers(ps, MINI, poll=1)
    assert reason == "failure" and ev["tasks"] == ["govern.keep"]


def test_non_goal_transitions_do_not_count():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    for i in range(5):
        ps.note(_transition("misc.x", "failed", i))
    assert mutate.check_triggers(ps, MINI, poll=10) == (None, {})


def test_near_failure_requeue_burst():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = mutate.PassState(cfg)
    ps.note(_transition("govern.keep", "requeued", 1))
    ps.note(_transition("govern.keep", "requeued", 2))
    reason, ev = mutate.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and ev["requeued"]


def test_near_failure_refusal_burst_and_blocked():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = mutate.PassState(cfg)
    for i in range(3):
        ps.note(_env("action.refused",
                     {"template_id": "t", "error": {"code": "x"}}, i))
    reason, ev = mutate.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and len(ev["refusals"]) == 3

    ps2 = mutate.PassState(cfg)
    ps2.note_outcome({"state": "blocked"})
    ps2.note_outcome({"state": "blocked"})
    reason, ev = mutate.check_triggers(ps2, MINI, poll=10)
    assert reason == "near_failure" and ev["blocked_polls"] == 2
    ps2.note_outcome({"state": "ok"})
    assert ps2.blocked_run == 0


def test_cooldown_and_pass_budget():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.last_pass_poll = 9           # cooldown_polls=5 -> poll 10 blocked
    ps.note(_transition("govern.keep", "failed"))
    assert mutate.check_triggers(ps, MINI, poll=10) == (None, {})
    reason, _ = mutate.check_triggers(ps, MINI, poll=15)
    assert reason == "failure"
    ps.passes = 4                   # max_passes_per_run=4 -> hard stop
    ps.last_pass_poll = -10**9
    assert mutate.check_triggers(ps, MINI, poll=30) == (None, {})


def test_no_mutate_section_no_triggers():
    ps = mutate.PassState({})
    ps.note(_transition("govern.keep", "failed"))
    assert mutate.check_triggers(ps, MINI, poll=10) == (None, {})


def test_escalate_counts_decision_rows():
    cfg = copy.deepcopy(MINI["mutate"])
    cfg["on_failure"] = False
    ps = mutate.PassState(cfg)
    ps.note_decisions([{"source": "govern.keep:escalate", "ok": True}])
    reason, ev = mutate.check_triggers(ps, MINI, poll=10)
    assert reason == "near_failure" and ev["escalations"] == 1


# -- digest --------------------------------------------------------------------

def test_digest_bounded_and_grounded():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    ledger = _Ledger()
    ledger.tasks = {"govern.keep": {"state": "failed", "attempts": 2}}
    d = mutate.build_digest(ps, ledger, _loaded(), MINI,
                            "failure", {"tasks": ["govern.keep"]}, 1, 2)
    assert d["pack"]["hash"] == _loaded()["hash"]
    assert d["goals"][0]["id"] == "govern.keep"
    assert d["goals"][0]["spec"]["retry_polls"] == 5
    assert len(json.dumps(d)) < 8000


# -- reflect -------------------------------------------------------------------

def test_reflect_model_proposal_accepted():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    r = mutate.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_ok)
    assert r["ok"] and r["proposal"]["mutation_id"] == "mut.test-bump"
    assert r["proposal"]["base_revision"] == _loaded()["hash"]
    assert r["usage"]["prompt_tokens"] == 10


def test_reflect_malformed_output_rejected():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    r = mutate.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_bad)
    assert not r["ok"] and not r.get("degraded")
    assert r["violations"]


def test_reflect_endpoint_down_is_degraded():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    r = mutate.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_endpoint, chat=_chat_broken)
    assert not r["ok"] and r["degraded"]


def test_reflect_unresolved_role_is_degraded():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    r = mutate.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_broken, chat=_chat_ok)
    assert not r["ok"] and r["degraded"]
    assert r["error"]["code"] == "mutate.unresolved"


def test_reflect_rules_only_applies_declared_remediation():
    """rules-only fallback: the improve pack's defect-pattern remediation
    becomes the proposal — compiled to packmut ops."""
    pack = copy.deepcopy(MINI)
    pack["improve"] = {"defect_patterns": [{
        "id": "refusal-burst", "event_type": "action.refused",
        "group_by": "payload.template_id", "min_count": 1,
        "remediation": {"ops": [{"op": "set_cfg",
                                 "path": "govern.goals.keep.retry_polls",
                                 "value": 7}]}}]}
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_env("action.refused", {"template_id": "ping"}))
    r = mutate.reflect(ps, {}, _loaded(pack), pack, "near_failure",
                       resolver=_resolver_rules, chat=_chat_broken)
    assert r["ok"] and r["degraded"]
    assert r["proposal"]["mutations"] == [
        {"op": "set", "path": "govern.goals.keep.retry_polls",
         "value": 7}]


def test_reflect_rules_only_no_findings_degrades():
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    r = mutate.reflect(ps, {}, _loaded(), MINI, "cadence",
                       resolver=_resolver_rules, chat=_chat_broken)
    assert not r["ok"] and r["degraded"]
    assert r["error"]["code"] == "mutate.rules_only_noop"


# -- gate ------------------------------------------------------------------------

def _proposal(ops, pack=None):
    pack = pack or MINI
    return {"schema_version": 0, "mutation_id": "mut.t",
            "base_revision": templates._hash_of(pack),
            "analysis": {"failure_paths": [], "likely_paths": []},
            "mutations": ops, "rationale": "r"}


def test_gate_full_pack_ops_apply():
    ops = [
        {"op": "set", "path": "govern.goals.keep.retry_polls",
         "value": 9},
        {"op": "upsert", "path": "govern.goals",
         "value": {"id": "new-goal", "retry_polls": 1,
                   "effect": {"field": "y"}, "steps": []}},
        {"op": "append", "path": "emergency",
         "value": {"id": "er", "priority": 1,
                   "condition": {"combinator": "any",
                                 "predicates": [{"field": "x",
                                                 "op": "gte",
                                                 "value": 1}]},
                   "action": {"template_id": "ping", "params": {}}}},
        {"op": "set", "path": "start.cfg.build_shelter", "value": False},
    ]
    g = mutate.gate(_proposal(ops), _loaded(), MINI, MINI["mutate"],
                    fair=False)
    assert g["ok"], g
    doc = g["doc"]
    assert doc["govern"]["goals"][0]["retry_polls"] == 9
    assert any(g2["id"] == "new-goal" for g2 in doc["govern"]["goals"])
    assert doc["emergency"][0]["id"] == "er"
    assert doc["start"]["cfg"]["build_shelter"] is False


def test_gate_remove_ops():
    pack = copy.deepcopy(MINI)
    pack["universal"] = {"rules": [{"id": "bad-rule", "when": {},
                                    "steps": []}]}
    ops = [{"op": "remove", "path": "universal.rules.bad-rule"},
           {"op": "remove", "path": "govern.goals.keep"}]
    g = mutate.gate(_proposal(ops, pack), _loaded(pack), pack,
                    MINI["mutate"], fair=False)
    assert g["ok"]
    assert g["doc"]["universal"]["rules"] == []
    assert g["doc"]["govern"]["goals"] == []


def test_gate_rejects_budget_stale_vacuous_miss():
    ld = _loaded()
    many = [{"op": "set", "path": f"govern.k{i}", "value": i}
            for i in range(6)]   # > max_ops 5
    g = mutate.gate(_proposal(many), ld, MINI, MINI["mutate"], fair=False)
    assert g["gate"] == "budget"

    stale = _proposal([{"op": "set", "path": "govern.x", "value": 1}])
    stale["base_revision"] = "0" * 64
    g = mutate.gate(stale, ld, MINI, MINI["mutate"], fair=False)
    assert g["gate"] == "stale"

    same = _proposal([{"op": "set",
                       "path": "govern.goals.keep.retry_polls",
                       "value": 5}])     # already 5 -> no change
    g = mutate.gate(same, ld, MINI, MINI["mutate"], fair=False)
    assert g["gate"] == "vacuous"

    miss = _proposal([{"op": "remove", "path": "govern.goals.nope"},
                      {"op": "set", "path": "govern.x", "value": 1}])
    g = mutate.gate(miss, ld, MINI, MINI["mutate"], fair=False)
    assert g["gate"] == "validation" and g["violations"]


def test_gate_rejects_unknown_method_and_fair_dev():
    ops = [{"op": "append", "path": "templates",
            "value": {"id": "evil", "method": "no.such.rpc",
                      "params_schema": {}}}]
    g = mutate.gate(_proposal(ops), _loaded(), MINI, MINI["mutate"],
                    fair=False)
    assert not g["ok"] and "sealed inventory" in g["violations"][0]

    dev = [{"op": "append", "path": "templates",
            "value": {"id": "dv", "method": "dev.spawn",
                      "params_schema": {}}}]
    g = mutate.gate(_proposal(dev), _loaded(), MINI, MINI["mutate"],
                    fair=True)
    assert not g["ok"] and "dev-class" in g["violations"][0]


def test_gate_rejects_schema_breaking_mutation():
    ops = [{"op": "set", "path": "templates", "value": []}]  # minItems 1
    g = mutate.gate(_proposal(ops), _loaded(), MINI, MINI["mutate"],
                    fair=False)
    assert not g["ok"] and g["gate"] == "validation"


# -- maybe_trigger + materialize -------------------------------------------------

def test_maybe_trigger_candidate_and_active_pack_untouched(tmp_path):
    emitted: list[dict] = []
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    d = _stub_dispatcher()
    pack_bytes = json.dumps(MINI, sort_keys=True)
    r = _maybe(ps, dispatcher=d, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=_chat_ok)
    assert r["verdict"] == "candidate"
    types = [e["event_type"] for e in emitted]
    assert types[:2] == ["mutation.triggered", "mutation.proposed"]
    assert "mutation.candidate" in types
    # active pack object never mutated by the pass
    assert json.dumps(MINI, sort_keys=True) == pack_bytes
    rows = mutate.lineage_rows(tmp_path)
    assert rows[-1]["state"] == "pending"
    assert Path(rows[-1]["candidate_path"]).is_file()


def test_maybe_trigger_noop_when_no_ops(tmp_path):
    def chat_noop(endpoint_id, model, messages, usage_tracker=None):
        return {"ok": True, "body": {"choices": [{"message": {
            "content": json.dumps({
                "mutation_id": "mut.nope", "analysis": {
                    "failure_paths": [], "likely_paths": []},
                "mutations": [], "rationale": "looks fine"})}}]}}
    emitted: list[dict] = []
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    r = _maybe(ps, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=chat_noop)
    assert r["verdict"] == "noop"
    assert "mutation.noop" in [e["event_type"] for e in emitted]


def test_maybe_trigger_rejection_path(tmp_path):
    emitted: list[dict] = []
    ps = mutate.PassState(copy.deepcopy(MINI["mutate"]))
    ps.note(_transition("govern.keep", "failed"))
    r = _maybe(ps, state_dir=tmp_path, emit=emitted.append,
               resolver=_resolver_endpoint, chat=_chat_bad)
    assert r["verdict"] == "rejected"
    rej = next(e for e in emitted
               if e["event_type"] == "mutation.rejected")
    assert rej["payload"]["gate"] == "schema"


def test_maybe_trigger_disabled_returns_none(tmp_path):
    ps = mutate.PassState({})
    ps.note(_transition("govern.keep", "failed"))
    assert _maybe(ps, state_dir=tmp_path) is None


# -- boundary: promote / revert --------------------------------------------------

@pytest.fixture()
def packs(tmp_path, monkeypatch):
    src = REPO_ROOT / "components" / "rimbrain" / "packs"
    dst = tmp_path / "packs"
    for pid in ("start-mode-v0", "improve-v0"):
        (dst / pid).mkdir(parents=True)
        shutil.copy(src / pid / "pack.yaml", dst / pid / "pack.yaml")
    monkeypatch.setenv("RIMBRAIN_PACKS_DIR", str(dst))
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    return dst


def _mk_candidate(packs_dir, pack_id="start-mode-v0", tweak=None):
    doc = yaml.safe_load((packs_dir / pack_id / "pack.yaml")
                         .read_text(encoding="utf-8"))
    if tweak:
        doc = tweak(doc)
    cdir = packs_dir / "candidates"
    cdir.mkdir(exist_ok=True)
    out = cdir / "cand-mut-test-aaaa.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out, templates._hash_of(doc)


def test_boundary_promotes_pending_candidate(packs, tmp_path):
    state = tmp_path / "state"
    parent_hash = templates.current_hash("start-mode-v0")
    cand, cand_hash = _mk_candidate(
        packs, tweak=lambda d: dict(d, revision="v0+mut.test"))
    mutate._append_lineage(state, {
        "candidate_id": cand.stem, "target_pack": "start-mode-v0",
        "candidate_path": str(cand), "candidate_hash": cand_hash,
        "state": "pending"})
    events: list[dict] = []
    out = mutate.boundary("start-mode-v0", state, emit=events.append)
    assert out["promoted"] == cand.stem
    assert templates.current_hash("start-mode-v0") == cand_hash
    assert templates.current_hash("start-mode-v0") != parent_hash
    assert any(e["event_type"] == "mutation.promoted" for e in events)
    rows = mutate.lineage_rows(state)
    promoted = [r for r in rows if r["state"] == "promoted"]
    assert promoted and promoted[-1]["parent_hash"] == parent_hash
    assert Path(promoted[-1]["parent_path"]).is_file()  # parent backup


def test_boundary_rejects_missing_candidate(packs, tmp_path):
    state = tmp_path / "state"
    mutate._append_lineage(state, {
        "candidate_id": "gone", "target_pack": "start-mode-v0",
        "candidate_path": str(packs / "candidates" / "gone.yaml"),
        "candidate_hash": "x", "state": "pending"})
    events: list[dict] = []
    before = templates.current_hash("start-mode-v0")
    out = mutate.boundary("start-mode-v0", state, emit=events.append)
    assert out["promoted"] is None and out["rejected"] == ["gone"]
    assert templates.current_hash("start-mode-v0") == before


def test_boundary_reverts_regressed_promotion(packs, tmp_path):
    state = tmp_path / "state"
    parent = templates.pack_path("start-mode-v0").read_bytes()
    parent_hash = templates.current_hash("start-mode-v0")
    # a promoted lineage row whose recorded baseline was great; the
    # "episode since" contains only failures -> worse score -> revert
    backup = packs / "candidates" / "parent-backup.yaml"
    backup.parent.mkdir(exist_ok=True)
    backup.write_bytes(parent)
    bad = copy.deepcopy(MINI)
    bad["pack_id"] = "pack.start-mode-v0"
    bad["revision"] = "v0+bad"
    templates.pack_path("start-mode-v0") \
        .write_text(yaml.safe_dump(bad), encoding="utf-8")
    mutate._append_lineage(state, {
        "candidate_id": "cand-bad", "target_pack": "start-mode-v0",
        "candidate_path": str(backup), "candidate_hash": "x",
        "state": "promoted", "parent_hash": parent_hash,
        "parent_path": str(backup), "baseline_score": 0.0,
        "events_offset": 0})
    # episode evidence: all-failed transitions -> score > baseline 0.0
    for i in range(3):
        (state / "events.jsonl").open("a").write(
            json.dumps(_transition(f"govern.g{i}", "failed", i)) + "\n")
    events: list[dict] = []
    out = mutate.boundary("start-mode-v0", state, emit=events.append)
    assert out["reverted"] == "cand-bad"
    assert templates.current_hash("start-mode-v0") == parent_hash
    assert any(e["event_type"] == "mutation.reverted" for e in events)


def test_boundary_keeps_improved_promotion(packs, tmp_path):
    state = tmp_path / "state"
    backup = packs / "candidates" / "p.yaml"
    backup.parent.mkdir(exist_ok=True)
    backup.write_bytes(b"keepme")
    mutate._append_lineage(state, {
        "candidate_id": "cand-ok", "target_pack": "start-mode-v0",
        "candidate_path": str(backup), "candidate_hash": "x",
        "state": "promoted", "parent_hash": "p", "parent_path": str(backup),
        "baseline_score": 0.9, "events_offset": 0})
    for i in range(3):   # clean episode -> score 0 < 0.9 -> keep
        (state / "events.jsonl").open("a").write(
            json.dumps(_transition(f"govern.g{i}", "succeeded", i)) + "\n")
    out = mutate.boundary("start-mode-v0", state)
    assert out["reverted"] is None
    assert mutate.lineage_rows(state)[-1]["state"] == "promoted"


# -- packmut compile_legacy -------------------------------------------------------

def test_compile_legacy_drop_rule_targets_only_the_list_that_has_it():
    doc = {"universal": {"rules": [{"id": "a"}]},
           "emergency": [{"id": "b"}],
           "combat": {"raid": {"rules": [{"id": "c"}]}}}
    ops = packmut.compile_legacy(
        [{"op": "drop_rule", "ids": ["a", "c", "nope"]}], doc)
    assert ops == [{"op": "remove", "path": "universal.rules.a"},
                   {"op": "remove", "path": "combat.raid.rules.c"}]
    changed, misses = packmut.apply_ops(doc, ops)
    assert changed and not misses
    assert doc["universal"]["rules"] == []


# -- integration: run_start --------------------------------------------------------

def test_run_start_live_mutate_off_emits_nothing(packs, tmp_path):
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    res = run_start(d, game, ledger, d.pack["pack"], iterations=30,
                    live_mutate=False)
    assert res["completed"]
    assert not [e for e in events
                if str(e["event_type"]).startswith("mutation.")]


def test_run_start_live_mutate_fires_and_pack_stays_put(packs, tmp_path):
    """A held run under --live-mutate: goals go terminal -> reflection
    passes fire; the loaded pack file hash never changes mid-run."""
    events: list[dict] = []
    game = StartSim()
    d = Dispatcher(game, sink=events.append,
                   clock=lambda: "2026-01-01T00:00:00Z")
    d.load_pack("start-mode-v0")
    pack = copy.deepcopy(d.pack["pack"])
    pack["mutate"] = copy.deepcopy(MINI["mutate"])
    pack["mutate"]["goals_per_pass"] = 5
    ledger = TaskLedger(tmp_path / "state" / "tasks.jsonl",
                        sink=events.append)
    res = run_start(d, game, ledger, pack, iterations=40, hold=True,
                    live_mutate=True,
                    mutate_resolver=_resolver_rules,
                    mutate_chat=_chat_broken)
    assert res["completed"]
    mut_events = [e["event_type"] for e in events
                  if str(e["event_type"]).startswith("mutation.")]
    # passes ran (triggered at least once); each resolved to a verdict
    assert "mutation.triggered" in mut_events
    assert any(t in mut_events for t in
               ("mutation.candidate", "mutation.degraded",
                "mutation.rejected", "mutation.noop"))
    assert d.pack["hash"] == templates.current_hash("start-mode-v0")
