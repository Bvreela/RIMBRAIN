"""Select stage (feature 017; FR-1407..1411, FR-1424, FR-1430).

Per decide-poll: compile a <=20-candidate action list (colony scope =
eligible goal ops from the active phase / standing goals; pawn scope =
pack ``decide.select.pawn_options`` evaluated per pawn) -> one batched
systemone call -> validated picks applied through the single writer
(colony picks drive the engine's own goal machinery; pawn picks are
direct dispatches). Invalid/absent picks resolve to the pack-declared
fallback (``priority_head`` = first candidate by priority); an
unreachable endpoint degrades the whole batch to fallback.

Selector authority is staged (shadow -> trial -> authority) per
(model, context) tuple and persisted to ``state/select_authority.json``
— the pack may *request* a rung; persisted evidence governs the
effective one. ``cadence_polls`` throttles decide frequency: off-polls
skip, never queue.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import policy, templates

HARD_MAX = 20                    # FR-1407 — engine bound, not pack data
RUNGS = ("shadow", "trial", "authority")
_REGISTRY = "select_authority.json"


# -- candidates (T019) -------------------------------------------------------

def _priority(spec, ctx, default: float) -> float:
    if spec is None:
        return default
    try:
        v = policy.resolve(spec, ctx)
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def compile_actions(pack: dict, engine, ctx, obs: dict, *,
                    plan: dict | None = None) -> list[dict]:
    """Enumerate this poll's satisfiable actions, score, truncate.

    Colony candidates reference their goal spec (applied via the
    engine's goal drive — ledger/effect bookkeeping intact); pawn
    candidates carry a resolved ``dispatch`` (template+params). Plan
    ``goal_order`` (FR-1413) boosts matching colony candidates.
    """
    sel = (templates.decide_of(pack).get("select") or {})
    boost = {gid: i for i, gid in
             enumerate((plan or {}).get("goal_order") or [])}
    n_boost = len(boost)
    cands: list[dict] = []

    # colony scope — eligible goals in declared (pack) order
    order = 0
    for ns, goals in engine.goal_sources():
        for g in goals:
            if not engine._goal_eligible(g, ctx, obs, ns):
                continue
            gid = g["id"]
            prio = _priority(g.get("priority"), ctx,
                             float(n_boost - boost[gid])
                             if gid in boost else 0.0)
            cands.append({
                "id": f"{ns}.{gid}", "scope": "colony", "label": gid,
                "priority": prio, "_order": order,
                "source": f"{ns}:{gid}", "goal": g, "ns": ns})
            order += 1

    # pawn scope — pack-declared per-pawn options
    pcfg = sel.get("pawn_scope") or {}
    pawns = policy.select(pcfg.get("for_each"), ctx) \
        if pcfg.get("for_each") is not None else []
    for cand_pawn in pawns:
        pid = (cand_pawn.get("id") if isinstance(cand_pawn, dict)
               else cand_pawn)
        if pid is None:
            continue
        ctx.vars["it"] = cand_pawn
        for opt in pcfg.get("options") or []:
            if not isinstance(opt, dict) or not opt.get("template"):
                continue
            oid = opt.get("id") or opt["template"]
            # option-level for_each expands one candidate per bound
            # target (pawn x target decision matrix); `bind` names the
            # var (default "target"), and the bound row's name/id is
            # suffixed onto the candidate id and label
            bind = opt.get("bind") or "target"
            targets = policy.select(opt["for_each"], ctx) \
                if opt.get("for_each") is not None else [None]
            for tgt in targets:
                if tgt is not None:
                    ctx.vars[bind] = tgt
                tid = tgt.get("id") if isinstance(tgt, dict) else tgt
                if opt.get("when") \
                        and not policy.check(opt["when"], ctx):
                    continue
                if "needs" in opt \
                        and not policy.resolve(opt["needs"], ctx):
                    continue
                params = {k: v for k, v in
                          policy.resolve(opt.get("params") or {},
                                         ctx).items() if v is not None}
                tname = policy._fn_label_of(ctx, tgt) \
                    if tgt is not None else None
                cands.append({
                    "id": (f"pawn.{pid}.{oid}.{tid}" if tid is not None
                           else f"pawn.{pid}.{oid}"),
                    "scope": "pawn", "pawn": pid,
                    "label": (f"{opt.get('label') or oid} {tname}"
                              if tname else opt.get("label") or oid),
                    "priority": _priority(opt.get("priority"), ctx, 0.0),
                    "_order": order, "source": f"pawn:{pid}",
                    "_row": cand_pawn,
                    "dispatch": {"template": opt["template"],
                                 "params": params}})
                order += 1
            ctx.vars.pop(bind, None)
    ctx.vars.pop("it", None)

    cands.sort(key=lambda c: (-c["priority"], c["_order"]))
    bound = min(int(sel.get("max_items") or
                (pack.get("action_list") or {}).get("max_items")
                or HARD_MAX), HARD_MAX)  # hard bound, not pack-editable
    # per-pool cap: the bound limits each question's candidate list —
    # a pawn x target x option matrix overflows a global cap fast
    pools: dict = {}
    out = []
    for c in cands:
        k = c.get("pawn") if c.get("scope") == "pawn" else "colony"
        pool = pools.setdefault(k, [])
        if len(pool) < bound:
            pool.append(c)
            out.append(c)
    return out


def _fallback_of(cands: list[dict], scope_pawn: str | None):
    """``priority_head`` fallback: highest-priority candidate in scope."""
    for c in cands:
        if scope_pawn is None and c["scope"] == "colony":
            return c
        if scope_pawn is not None and c["scope"] == "pawn" \
                and c["pawn"] == scope_pawn:
            return c
    return None


def build_questions(cands: list[dict], obs: dict,
                    sel_cfg: dict, plan: dict | None,
                    ctx=None) -> dict:
    """One batched systemone payload: ``q.colony`` + ``q.pawn.<id>``
    (contracts/select-batch.md). Criteria keys are candidate ids only —
    the model can name nothing outside the offered set."""
    colony = [c for c in cands if c["scope"] == "colony"]
    ctx_stats = {"colony": {
                     "colonists": (obs.get("colonists") or {})
                     .get("count"),
                     "nutrition": (obs.get("stocks") or {})
                     .get("nutrition"),
                     "meals": obs.get("meals_present")},
                 "plan": (plan or {}).get("id")}
    questions = {}
    if colony:
        questions["q.colony"] = {
            "type": "choice",
            "instructions": sel_cfg.get(
                "instructions", "pick the best colony action"),
            "criteria": {c["id"]: c["label"] for c in colony},
            "context": ctx_stats}
    if sel_cfg.get("batch_pawns", True):
        by_pawn: dict[str, list] = {}
        for c in cands:
            if c["scope"] == "pawn":
                by_pawn.setdefault(c["pawn"], []).append(c)
        # pack-declared per-pawn context (pawn_scope.context resolvers
        # evaluated with `it` bound to the pawn row) — positions, weapon
        # range class, per-target distances — so a fast selector can
        # reason over the map, not just option names
        cmap = ((sel_cfg.get("pawn_scope") or {}).get("context") or {}) \
            if ctx is not None else {}
        for pid, pcs in by_pawn.items():
            pctx = {"pawn": {"id": pid}}
            if cmap:
                row = next((c.get("_row") for c in pcs
                            if c.get("_row") is not None), {"id": pid})
                ctx.vars["it"] = row
                pctx.update({k: policy.resolve(v, ctx)
                             for k, v in cmap.items()})
                ctx.vars.pop("it", None)
            questions[f"q.pawn.{pid}"] = {
                "type": "choice",
                "instructions": sel_cfg.get("pawn_instructions",
                                            "pick this pawn's job"),
                "criteria": {c["id"]: c["label"] for c in pcs},
                "context": pctx}
    return questions


# -- authority registry (T047; FR-1424) ---------------------------------------

def _reg_path(state_dir) -> Path:
    return Path(state_dir) / _REGISTRY


def _load_reg(state_dir) -> dict:
    try:
        return json.loads(_reg_path(state_dir).read_text())
    except Exception:
        return {"tuples": {}}


def _save_reg(state_dir, reg: dict) -> None:
    p = _reg_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, sort_keys=True) + "\n")
    tmp.replace(p)


def _qualified_rung(rec: dict, qual: dict) -> str:
    """Highest rung the tuple's evidence supports."""
    picks = int(rec.get("picks") or 0)
    div = float(rec.get("divergent") or 0) / picks if picks else 1.0
    min_picks = int(qual["min_picks"]) if "min_picks" in qual else 10
    max_div = float(qual["max_divergence"]) \
        if "max_divergence" in qual else 0.15
    if picks < min_picks or div > max_div:
        return "shadow"
    if picks < min_picks * 3 or div > max_div / 2:
        return "trial"
    return "authority"


def authority_rung(state_dir, sel_cfg: dict, model: str | None,
                   ctx_key: str, emit=None) -> tuple[str, dict]:
    """Effective rung = min(requested, evidence-qualified). A rung
    *change* emits ``select.authority`` and persists the registry."""
    reg = _load_reg(state_dir)
    key = f"{model or 'default'}|{ctx_key}"
    rec = reg["tuples"].get(key) or {"rung": "shadow", "picks": 0,
                                   "divergent": 0}
    requested = sel_cfg.get("rung") or \
        ("shadow" if sel_cfg.get("shadow") else "authority")
    qual = sel_cfg.get("qualify") or {}
    qualified = _qualified_rung(rec, qual)
    effective = RUNGS[min(RUNGS.index(requested),
                          RUNGS.index(qualified))]
    if effective != rec.get("rung"):
        rec["rung"] = effective
        reg["tuples"][key] = rec
        _save_reg(state_dir, reg)
        if emit is not None:
            emit({"event_type": "select.authority",
                  "payload": {"tuple": key, "rung": effective,
                              "picks": rec["picks"],
                              "divergent": rec["divergent"]}})
    else:
        reg["tuples"][key] = rec
        _save_reg(state_dir, reg)
    return effective, rec


def _note_pick(state_dir, key: str, rec: dict, divergent: bool) -> None:
    reg = _load_reg(state_dir)
    r = dict(rec)
    r["picks"] = int(r.get("picks") or 0) + 1
    if divergent:
        r["divergent"] = int(r.get("divergent") or 0) + 1
    reg["tuples"][key] = r
    _save_reg(state_dir, reg)


# -- endpoint call (T020) -----------------------------------------------------

def _default_caller(sel_cfg: dict, state: str,
                    questions: dict) -> dict:
    """Resolve ``rimbrain.select`` and issue the batched decide call."""
    from .bindings import resolve_role
    from . import client as _client
    res = resolve_role(sel_cfg.get("role") or "rimbrain.select",
                       probe_live=True)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or {}}
    ep = res["resolved"]["endpoint_id"]
    return _client.systemone_decide(
        ep, state=state, questions=questions,
        model=res["resolved"].get("model"))


# -- decide stage (T020/T021/T022/T046) ---------------------------------------

def decide(dispatcher, pack: dict, engine, ctx, obs: dict, *,
           tick: int, poll: int, state_dir, plan=None,
           caller=None, emit=None) -> dict | None:
    """The decide stage for one poll. Returns the stage outcome to hand
    to ``engine.step(select_out=...)``, or None when cadence skips this
    poll (the engine's default first-fit goal drive resumes).

    Never raises and never blocks the poll: endpoint failure degrades
    every question to fallback with a ``select.degraded`` event.
    """
    sel = templates.decide_of(pack).get("select") or {}
    if not sel:
        return None
    cadence = int(sel.get("cadence_polls") or 1)
    if cadence > 1 and poll % cadence:
        return None                      # skip, never queue (FR-1430)

    cands = compile_actions(pack, engine, ctx, obs, plan=plan)
    t0 = time.monotonic()
    rung = "shadow"
    questions = {}
    answers: dict = {}

    if cands:
        questions = build_questions(cands, obs, sel, plan, ctx=ctx)
        # (model, prompt, context) tuple: question *shape* is stable —
        # per-poll candidate ids would never accumulate evidence
        ctx_key = hashlib.sha1(
            json.dumps({"instr": {k: v.get("instructions")
                                  for k, v in questions.items()},
                        "scopes": sorted(questions)},
                       sort_keys=True).encode()).hexdigest()[:12]
        rung, rec = authority_rung(state_dir, sel,
                                   sel.get("model"), ctx_key, emit=emit)
        # caller=None = no endpoint wired (sim/test/scored) — resolve
        # answers from pack fallback only; no endpoint resolution is
        # ever attempted (T025 determinism contract). A live caller is
        # injected only by the CLI's --game live path.
        res = caller(sel, f"poll:{poll}", questions) \
            if caller is not None else {"ok": False}
        if not res.get("ok"):
            if emit is not None and caller is not None:
                emit({"event_type": "select.degraded",
                      "payload": {"error": (res.get("error") or {})
                                  .get("code")}})
        else:
            answers = ((res.get("body") or {}).get("answers") or {})
    latency_ms = int((time.monotonic() - t0) * 1000)

    # validation + application per contract: membership -> dispatch;
    # invalid/absent -> fallback + select.invalid; shadow records the
    # pick but the fallback executes
    applied_goal_out = None
    for qid, q in questions.items():
        scope_pawn = qid[len("q.pawn."):] \
            if qid.startswith("q.pawn.") else None
        pool = {c["id"]: c for c in cands
                if (c["scope"] == "pawn") == (scope_pawn is not None)
                and (scope_pawn is None or c["pawn"] == scope_pawn)}
        pick = (answers.get(qid) or {}).get("choice")
        valid = pick in pool
        fb = _fallback_of(cands, scope_pawn)
        fb_applied = not valid or rung == "shadow"
        applied = fb if fb_applied else pool.get(pick)
        if pick is not None and not valid and emit is not None:
            emit({"event_type": "select.invalid",
                  "payload": {"question": qid, "pick": pick}})
        divergent = pick is not None and pick != \
            (applied or {}).get("id")
        if rung in ("shadow", "trial"):
            _note_pick(state_dir, f"{sel.get('model') or 'default'}|"
                       f"{ctx_key}", rec, divergent)
        if applied is None:
            continue
        row = {"tick": tick, "poll": poll,
               "source": f"select:{qid}",
               "phase": getattr(engine, "phase_id", None),
               "offered": sorted(pool), "pick": pick,
               "applied": applied["id"],
               "fallback": fb_applied,
               "shadow": rung == "shadow",
               "latency_ms": latency_ms}
        if applied["scope"] == "colony":
            # the pick drives first; if it produces no work this poll
            # the remaining eligible goals fall through in priority
            # order — same coverage as the old first-fit sweep
            ordered = [applied] + [c for c in cands
                                   if c["scope"] == "colony"
                                   and c is not applied]
            for c in ordered:
                gout = engine._goal_entry(
                    c["goal"], dispatcher, ctx, obs, tick, c["ns"])
                if gout is not None:
                    applied_goal_out = gout
                    break
            if applied_goal_out is None:
                applied_goal_out = {"phase": applied["ns"],
                                    "state": "holding"}
            # select rows mark the pick; the goal's own step dispatches
            # record the writes (decisions.jsonl stays 1:1 with
            # action.issued for renderable rows)
            row["select"] = True
            row["template"] = applied["id"]
            row["params"] = {}
            row["ok"] = applied_goal_out.get("state") not in \
                ("failed", "blocked")
        else:
            r = dispatcher.dispatch(applied["dispatch"]["template"],
                                    applied["dispatch"]["params"])
            row["template"] = applied["dispatch"]["template"]
            row["params"] = applied["dispatch"]["params"]
            row["ok"] = bool(r.get("ok"))
        row["inputs_hash"] = hashlib.sha1(
            json.dumps(questions, sort_keys=True,
                       default=str).encode()).hexdigest()[:12]
        if engine.decisions is not None:
            engine.decisions.append(row)

    if applied_goal_out is not None:
        return applied_goal_out
    # select owned the stage but nothing applied — colony rests
    return {"phase": "govern", "state": "holding"}
