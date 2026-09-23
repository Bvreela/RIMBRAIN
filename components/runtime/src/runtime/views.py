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


def _goal_rows(mode, ledger) -> list[dict]:
    """Ordered goals straight from the pack — the pack IS the plan."""
    rows = []
    for ph in (mode.cfg.get("phases") or []):
        pid = ph.get("id")
        if not pid:
            continue
        task = ledger.tasks.get(mode._tid(pid)) or {}
        state = task.get("state", "pending")
        blocker = None
        if state in ("failed", "cancelled"):
            blocker = task.get("reason") or state
        elif state in ("dispatched", "verifying"):
            blocker = "awaiting effect"
        rows.append({"id": pid, "state": state, "blocker": blocker,
                     "attempts": task.get("attempts", 0)})
    return rows


def planning_snapshot(mode, ledger, obs, latest_plan=None) -> dict:
    """Build the canonical planning snapshot for this poll."""
    ev = mode.last_eval or {}
    return {
        "mode": "start",
        "tick": obs.get("tick"),
        "poll": mode._poll,
        "pack_revision": mode.pack.get("pack_revision")
                         or mode.pack.get("revision"),
        "goals": _goal_rows(mode, ledger),
        "exit_conditions": ev.get("conditions") or {},
        "complete": bool(ev.get("complete")) or mode.completed,
        "long_horizon": latest_plan,
    }


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
             "| goal | state | attempts | blocker |",
             "|---|---|---|---|"]
    for g in snapshot["goals"]:
        lines.append(f"| {g['id']} | {g['state']} | {g['attempts']} "
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


def start_snapshot(mode, ledger, obs, events_path=None) -> dict:
    """Planning snapshot for start mode (goals = pack phases)."""
    return planning_snapshot(
        mode, ledger, obs,
        latest_plan=latest_plan_summary(events_path) if events_path
        else None)


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
                      "attempts": r.get("hostiles", 0)})
    return {"mode": "combat", "tick": obs.get("tick"), "poll": poll,
            "pack_revision": pack.get("pack_revision")
            or pack.get("revision"),
            "goals": goals, "exit_conditions": {},
            "complete": all(g["state"] == "cleared" for g in goals[1:])
            if len(goals) > 1 else False,
            "long_horizon": None}
