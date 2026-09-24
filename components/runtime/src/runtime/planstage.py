"""Plan stage (feature 017, US3; contracts/plan-output.md).

The ``rimbrain.plan`` endpoint fires on pack ``decide.plan`` triggers —
``cadence_s`` (default 150 wall seconds), ``on_phase_boundary``, and
``on_events`` matched against emitted event types. An accepted plan is
*in force until superseded*: ``goal_order`` re-scores the select
stage's colony candidates, ``activate``/``deactivate`` toggle standing
goals, and ``promote`` materializes pack ``options`` entries into
runtime goals/phases (pack-file mutation still goes through evolve).

The deterministic gate is decisive — unknown ids, bad params, or
fair-class violations reject the plan and the prior plan stays. An
endpoint outage degrades the same way; no poll ever blocks on the
planner (the caller is injectable and failure-tolerant, mirroring
``select.decide``).
"""

from __future__ import annotations

import json
import time

from . import templates

SOURCE = "rimbrainagent.runtime.planstage"


# -- triggers (T029) --------------------------------------------------

def _sched(state: dict) -> dict:
    return state.setdefault("planstage",
                            {"last_s": None, "done_count": 0})


def triggers_due(cfg: dict, sched: dict, *, now_s: float,
                 done_count: int, events: list) -> tuple[bool, str]:
    """First firing is immediate (no prior plan exists to fall back on);
    afterwards cadence/boundary/event triggers apply."""
    if sched.get("last_s") is None:
        return True, "first"
    if now_s - sched["last_s"] >= float(cfg.get("cadence_s") or 150):
        return True, "cadence"
    if cfg.get("on_phase_boundary") and done_count > sched["done_count"]:
        return True, "phase_boundary"
    want = set(cfg.get("on_events") or [])
    hit = want.intersection(events)
    if hit:
        return True, f"event:{sorted(hit)[0]}"
    return False, ""


# -- digest (T030) ----------------------------------------------------

def digest(obs: dict, ledger, engine, plan: dict | None) -> dict:
    """Compact obs+ledger projection — the same shape evolve's
    reflection digest extends."""
    holds, fails = [], []
    for tid, t in (getattr(ledger, "tasks", {}) or {}).items():
        if "." not in tid:
            continue
        state = t.get("state")
        if state == "succeeded":
            holds.append(tid)
        elif state in ("failed", "expired"):
            fails.append(tid)
    return {
        "tick": obs.get("tick"),
        "colonists": obs.get("colonists"),
        "stocks": {"nutrition": (obs.get("stocks") or {})
                   .get("nutrition")},
        "meals_present": obs.get("meals_present"),
        "fires": (obs.get("map") or {}).get("fires"),
        "phase": {"done": [pid for pid, p in
                           (engine.rs.phase or {}).items()
                           if p.get("done")]},
        "goal_holds": holds[-20:], "goal_fails": fails[-20:],
        "plan_id": (plan or {}).get("id"),
    }


# -- gate + application (T031) ----------------------------------------

def _known_goal_ids(pack: dict, engine) -> set:
    ids = {g.get("id") for g in templates.standing_goals_of(pack)}
    for ph in templates.phases_of(pack):
        ids.update(g.get("id") for g in ph.get("goals") or [])
    ids.update(g.get("id") for g in
               (engine.rs.plan or {}).get("promoted", []))
    return {i for i in ids if i}


def _dev_templates(pack: dict) -> set:
    """Template ids whose bridge method is dev-class or save/load —
    fair-class plans may never materialize these."""
    out = set()
    for t in pack.get("templates") or []:
        m = str(t.get("method") or "")
        if m.startswith("dev.") or m in ("game.save", "game.load"):
            if t.get("id"):
                out.add(t["id"])
    return out


def _walk_templates(node, out: set) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "template" and isinstance(v, str):
                out.add(v)
            else:
                _walk_templates(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_templates(v, out)


def materialize(option: dict, as_: str, params: dict) -> dict | None:
    """Instantiate an option's declared body with the plan's params.
    ``@param:<name>`` placeholders resolve from params; undeclared or
    missing params leave the placeholder — the gate rejects those."""
    import copy
    body = copy.deepcopy(option.get("phase" if as_ == "phase"
                                    else "goal"))
    if not isinstance(body, dict):
        return None
    missing = []

    def _res(node):
        if isinstance(node, str) and node.startswith("@param:"):
            name = node[len("@param:"):]
            if name in params:
                return params[name]
            missing.append(name)
            return node
        if isinstance(node, dict):
            return {k: _res(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_res(v) for v in node]
        return node

    body = _res(body)
    if missing:
        return None
    body.setdefault("id", f"plan.{option.get('id')}")
    return body


def gate(plan_doc: dict, pack: dict, engine, *, fair: bool) -> list:
    """Decisive violations list — empty means apply. Unknown ids, bad
    promote params, and dev-class materializations all reject."""
    violations = []
    if not isinstance(plan_doc, dict):
        return ["plan is not an object"]
    known = _known_goal_ids(pack, engine)
    for key in ("goal_order", "activate", "deactivate"):
        ids = plan_doc.get(key) or []
        if not isinstance(ids, list):
            violations.append(f"{key} is not a list")
            continue
        for gid in ids:
            if gid not in known:
                violations.append(f"{key}: unknown goal id '{gid}'")
    opts = {o.get("id"): o for o in templates.options_of(pack)}
    dev = _dev_templates(pack) if fair else set()
    for p in plan_doc.get("promote") or []:
        oid = p.get("option")
        opt = opts.get(oid)
        if opt is None:
            violations.append(f"promote: unknown option '{oid}'")
            continue
        as_ = p.get("as") or "goal"
        if as_ not in ("goal", "phase"):
            violations.append(f"promote:{oid}: bad 'as' '{as_}'")
            continue
        schema = opt.get("params") or {}
        params = p.get("params") or {}
        unknown = set(params) - set(schema) if schema else set()
        if unknown:
            violations.append(
                f"promote:{oid}: params not in schema "
                f"{sorted(unknown)}")
        body = materialize(opt, as_, params)
        if body is None:
            violations.append(
                f"promote:{oid}: no materializable {as_} body")
            continue
        if dev:
            used = set()
            _walk_templates(body, used)
            bad = used & dev
            if bad:
                violations.append(
                    f"promote:{oid}: dev-class templates "
                    f"{sorted(bad)} refused under fair")
    return violations


def apply(engine, rs, plan_doc: dict, *, tick: int, issued_at: str,
          plan_id: str) -> dict:
    """Install the gated plan: persisted in runstate, materialized into
    the engine's live goal/phase sets."""
    opts = {o.get("id"): o for o in templates.options_of(engine.pack)}
    promoted = []
    for p in plan_doc.get("promote") or []:
        opt = opts.get(p.get("option")) or {}
        as_ = p.get("as") or "goal"
        body = materialize(opt, as_, p.get("params") or {})
        if body is not None:
            promoted.append({"option": p.get("option"), "as": as_,
                             "body": body})
    plan = {"id": plan_id, "issued_at": issued_at, "tick": tick,
            "goal_order": list(plan_doc.get("goal_order") or []),
            "activate": list(plan_doc.get("activate") or []),
            "deactivate": list(plan_doc.get("deactivate") or []),
            "promoted": promoted,
            "horizon": plan_doc.get("horizon")}
    rs.plan = plan
    engine.apply_plan(plan)
    return plan


# -- stage entry (T029/T032) ------------------------------------------

def _default_caller(cfg: dict, digest_doc: dict) -> dict:
    """Resolve ``rimbrain.plan`` and chat for a JSON plan document."""
    from .bindings import resolve_role
    from .client import openai_compat_chat
    res = resolve_role(cfg.get("role") or "rimbrain.plan",
                       probe_live=True)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or {}}
    r = res["resolved"]
    prompt = json.dumps({
        "digest": digest_doc,
        "respond": {"plan": {
            "goal_order": ["goal_id"],
            "activate": ["goal_id"], "deactivate": ["goal_id"],
            "promote": [{"option": "id", "as": "goal",
                         "params": {}}],
            "horizon": "short text"}}})
    out = openai_compat_chat(r.get("endpoint_id") or r,
                             r.get("model"), [{"role": "user",
                                               "content": prompt}])
    if not out.get("ok"):
        return out
    content = ((out.get("body") or {}).get("choices") or [{}])[0] \
        .get("message", {}).get("content") or ""
    try:
        doc = json.loads(content)
    except Exception:
        return {"ok": False,
                "error": {"code": "plan.bad_json",
                          "message": "planner reply was not JSON"}}
    return {"ok": True, "body": {"plan": doc.get("plan", doc)}}


def tick(dispatcher, pack: dict, engine, ledger, obs: dict, *,
         tick: int, poll: int, state_dir=None, caller=None,
         emit=None, now=None, events: list | None = None,
         force: bool = False) -> dict | None:
    """One poll of the plan stage. Returns the in-force plan (or None
    when the pack declares none and none is in force). Never raises;
    outage/rejection leaves the prior plan standing."""
    cfg = (templates.decide_of(pack).get("plan") or {})
    rs = engine.rs
    if not cfg and rs.plan is None:
        return None
    sched = _sched(rs.rule_state)
    now_s = time.monotonic() if now is None else now
    done_count = sum(1 for p in (rs.phase or {}).values()
                     if p.get("done"))
    due, why = (True, "forced") if force else triggers_due(
        cfg, sched, now_s=now_s, done_count=done_count,
        events=events or [])
    if not due:
        return rs.plan
    sched["last_s"] = now_s
    sched["done_count"] = done_count

    res = caller(cfg, digest(obs, ledger, engine, rs.plan)) \
        if caller is not None else {"ok": False}
    if not res.get("ok"):
        if emit is not None and caller is not None:
            emit({"event_type": "plan.degraded",
                  "payload": {"trigger": why,
                              "error": (res.get("error") or {})
                              .get("code")}})
        return rs.plan                       # last plan stands
    plan_doc = (res.get("body") or {}).get("plan") or {}
    violations = gate(plan_doc, pack, engine,
                      fair=getattr(dispatcher, "_fair", True))
    plan_id = f"plan.{tick}.{poll}"
    if violations:
        if emit is not None:
            emit({"event_type": "plan.rejected",
                  "payload": {"plan_id": plan_id, "trigger": why,
                              "violations": violations}})
        return rs.plan                       # last plan stands
    plan = apply(engine, rs, plan_doc, tick=tick,
                 issued_at=now_s, plan_id=plan_id)
    if emit is not None:
        emit({"event_type": "plan.accepted",
              "payload": {"plan_id": plan_id, "trigger": why,
                          "goal_order": plan["goal_order"],
                          "activate": plan["activate"],
                          "deactivate": plan["deactivate"],
                          "promoted": [p["option"]
                                       for p in plan["promoted"]]}})
    return plan
