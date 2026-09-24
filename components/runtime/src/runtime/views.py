"""Agent transparency views (feature 013; UR-VIEW-001..004).

Two synchronized per-poll renders derived from canonical state:

- ``state/planning.json`` + ``state/planning.md`` — Planning & Goals:
  active mode, ordered goal list (pack phase order = priority order),
  per-goal ledger state + live effect truth, exit-condition eval,
  blockers, and the latest planner proposal summary when present.
- ``state/actions.md`` — Quick-Action Matrix: the trailing window of
  ``state/decisions.jsonl`` rows {tick, poll, source, template, params,
  ok} recorded by ``policy.run_steps``/``run_rules``.

Canonical records (decisions.jsonl, planning.json, events.jsonl,
tasks.jsonl) are authoritative; the markdown renders are disposable
(UR-DAT-007). Rendering is fail-open — a view error must never
interrupt control (FR-1103). Views expose decision surfaces only:
which pack element acted, with what resolved params — never model
chain-of-thought (UR-VIEW-004).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import policy
from .store import write_atomic

ACTIONS_WINDOW = 25  # trailing rows rendered in actions.md


def record_decisions(path: str | Path, rows: list[dict]) -> None:
    """Append canonical decision rows to ``state/decisions.jsonl``."""
    if not rows:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _brief(spec, limit: int = 72) -> str | None:
    """One-line render of a pack spec (effect/steps) for display."""
    if spec is None:
        return None
    s = json.dumps(spec, separators=(",", ":"), default=str)
    return s if len(s) <= limit else s[:limit - 3] + "..."


def _goal_rows(mode, ledger, ctx=None) -> list[dict]:
    """Ordered goals straight from the pack — the pack IS the plan.
    Start phases first, then the pack's post-start govern goals.
    `holds` is the effect's live truth so a terminal-but-lapsed goal
    doesn't sit green."""
    rows = []
    sections = [("start", mode.cfg.get("phases") or [], ""),
                ("govern", ((mode.pack.get("govern") or {})
                            .get("goals") or []), "govern.")]
    for ns, entries, prefix in sections:
        for g in entries:
            gid = g.get("id")
            if not gid:
                continue
            task = ledger.tasks.get(mode._tid(gid, ns=ns)) or {}
            state = task.get("state", "pending")
            holds = None
            if ctx is not None and g.get("effect") is not None:
                try:
                    holds = bool(policy.check(g["effect"], ctx))
                except Exception:
                    holds = None
            if state == "succeeded" and holds is False:
                state = "lapsed"
            elif state == "pending" and holds is True:
                state = "satisfied"
            blocker = None
            if state in ("failed", "cancelled"):
                blocker = task.get("reason") or state
            elif state in ("dispatched", "verifying"):
                blocker = "awaiting effect"
            elif state == "lapsed":
                blocker = "effect lost — will re-arm"
            rows.append({"id": f"{prefix}{gid}", "state": state,
                         "holds": holds,
                         "blocker": blocker,
                         "attempts": task.get("attempts", 0),
                         "effect": _brief(g.get("effect"))})
    return rows


def _view_ctx(mode, obs):
    """Ctx for live effect evaluation; modes without _ctx -> None."""
    try:
        return mode._ctx(obs) if hasattr(mode, "_ctx") else None
    except Exception:
        return None


def planning_snapshot(mode, ledger, obs, latest_plan=None,
                      mutate_view=None) -> dict:
    """Build the canonical planning snapshot for this poll."""
    ev = mode.last_eval or {}
    snap = {
        "mode": "start",
        "tick": obs.get("tick"),
        "poll": mode._poll,
        "pack_revision": mode.pack.get("pack_revision")
                         or mode.pack.get("revision"),
        "goals": _goal_rows(mode, ledger, ctx=_view_ctx(mode, obs)),
        "exit_conditions": ev.get("conditions") or {},
        "complete": bool(ev.get("complete")) or mode.completed,
        "long_horizon": latest_plan,
    }
    if mutate_view is not None:
        snap["mutation"] = mutate_view
    return snap


def write_planning(state_dir: str | Path, snapshot: dict) -> None:
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    write_atomic(d / "planning.json",
                 json.dumps(snapshot, sort_keys=True).encode() + b"\n")
    lines = ["# Planning & Goals", "",
             f"mode: `{snapshot['mode']}`  tick: {snapshot['tick']}"
             f"  poll: {snapshot['poll']}",
             f"pack: `{snapshot.get('pack_revision') or '?'}`", "",
             "## Goals (pack order = priority)", "",
             "| goal | state | holds | attempts | success condition | blocker |",
             "|---|---|---|---|---|---|"]
    for g in snapshot["goals"]:
        h = g.get("holds")
        mark = "yes" if h is True else ("NO" if h is False else "—")
        lines.append(f"| {g['id']} | {g['state']} | {mark} | {g['attempts']} "
                     f"| {g.get('effect') or g.get('detail') or '—'} "
                     f"| {g.get('blocker') or '—'} |")
    lines += ["", "## Exit conditions", ""]
    conds = snapshot.get("exit_conditions") or {}
    if conds:
        for name, held in conds.items():
            lines.append(f"- {'x' if held else ' '} {name}")
    else:
        lines.append("- (not yet evaluated)")
    if snapshot.get("complete"):
        lines += ["", "**start mode: COMPLETE**"]
    lh = snapshot.get("long_horizon")
    if lh:
        lines += ["", "## Long-horizon plan", ""]
        if isinstance(lh, dict):
            for k in ("goal", "summary", "phases", "horizon"):
                if lh.get(k) is not None:
                    lines.append(f"- **{k}**: {lh[k]}")
        else:
            lines.append(str(lh))
    mv = snapshot.get("mutation")
    if mv:
        lines += ["", "## Pack mutation", "",
                  f"passes: {mv.get('passes', 0)}  "
                  f"terminal goals since last pass: "
                  f"{mv.get('goals_since_pass', 0)}",
                  f"last verdict: `{mv.get('last_verdict') or '—'}`",
                  f"pending candidate: "
                  f"`{mv.get('pending_candidate') or '—'}`",
                  f"active lineage: `{mv.get('active_lineage') or '—'}`"]
    write_atomic(d / "planning.md",
                 "\n".join(lines).encode() + b"\n")


def write_actions(state_dir: str | Path, decisions_path: str | Path,
                  window: int = ACTIONS_WINDOW) -> None:
    """Render the trailing window of decisions.jsonl as a table."""
    p = Path(decisions_path)
    rows = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    tail = rows[-window:]
    lines = ["# Quick-Action Matrix", "",
             f"showing last {len(tail)} of {len(rows)} decisions", "",
             "| tick | poll | source | capability | params | ok |",
             "|---|---|---|---|---|---|"]
    for r in tail:
        params = json.dumps(r.get("params") or {})
        if len(params) > 70:
            params = params[:67] + "..."
        lines.append(f"| {r.get('tick')} | {r.get('poll')} "
                     f"| {r.get('source')} | {r.get('template')} "
                     f"| {params} | {'yes' if r.get('ok') else 'NO'} |")
    write_atomic(Path(state_dir) / "actions.md",
                 "\n".join(lines).encode() + b"\n")


def latest_plan_summary(events_path: str | Path) -> dict | None:
    """Last plan.proposed declared fields — summary only, no CoT."""
    p = Path(events_path)
    if not p.is_file():
        return None
    out = None
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event_type") == "plan.proposed":
            pay = e.get("payload") or {}
            out = {k: pay.get(k) for k in
                   ("goal", "summary", "phases", "horizon")
                   if pay.get(k) is not None}
    return out


def write_views(state_dir, snapshot: dict, decisions,
                events_path=None) -> None:
    """One call per poll: canonical decisions append + both renders.
    Fail-open — view errors never interrupt control (FR-1103)."""
    try:
        d = Path(state_dir)
        dpath = d / "decisions.jsonl"
        record_decisions(dpath, decisions)
        write_planning(d, snapshot)
        write_actions(d, dpath)
    except Exception:
        pass


def start_snapshot(mode, ledger, obs, events_path=None,
                   mutate_view=None) -> dict:
    """Planning snapshot for start mode (goals = pack phases)."""
    return planning_snapshot(
        mode, ledger, obs,
        latest_plan=latest_plan_summary(events_path) if events_path
        else None, mutate_view=mutate_view)


def simple_snapshot(mode, obs, poll, goals=None, pack=None,
                    ledger=None) -> dict:
    """Minimal planning snapshot for modes without a phase list (loop,
    cycle). Goals come from the ledger's non-terminal tasks when given."""
    rows = goals
    if rows is None and ledger is not None:
        rows = [{"id": t.get("task_id") or tid, "state": t.get("state"),
                 "blocker": t.get("reason"),
                 "attempts": t.get("attempts", 0)}
                for tid, t in (ledger.tasks or {}).items()]
    return {"mode": mode, "tick": obs.get("tick"), "poll": poll,
            "pack_revision": (pack or {}).get("pack_revision")
            or (pack or {}).get("revision"),
            "goals": rows or [], "exit_conditions": {},
            "complete": False, "long_horizon": None}


def combat_snapshot(pack, obs, rounds_out, poll) -> dict:
    """Planning snapshot for combat mode (goals = pack combat phases)."""
    goals = [{"id": "setup", "state": "succeeded",
              "blocker": None, "attempts": 0}]
    for r in rounds_out:
        goals.append({"id": f"round-{r['round']}",
                      "state": r["verdict"], "blocker": None,
                      "attempts": r.get("hostiles", 0),
                      "detail": (f"hostiles {r.get('hostiles', 0)} "
                                 f"casualties {r.get('casualties', 0)}")})
    return {"mode": "combat", "tick": obs.get("tick"), "poll": poll,
            "pack_revision": pack.get("pack_revision")
            or pack.get("revision"),
            "goals": goals, "exit_conditions": {},
            "complete": all(g["state"] == "cleared" for g in goals[1:])
            if len(goals) > 1 else False,
            "long_horizon": None}
