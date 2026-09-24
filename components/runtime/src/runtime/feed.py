"""Thought feed (feature 009; FR-805, SC-803).

Every canonical decision event gets a plain-language feed entry in
`state/feed.md` — what the agent saw, planned, decided, and learned.
Deterministic templates; an optional narrator binding may rephrase but
the structured echo is the guaranteed floor (fail-closed: feed write
failure is recorded, never fatal to gameplay).
"""

from __future__ import annotations

from pathlib import Path

from .store import write_atomic


def render_event(env: dict) -> str:
    """One-line narrative for a canonical envelope (deterministic)."""
    t = env.get("event_type", "?")
    p = env.get("payload") or {}
    if t == "action.issued":
        return (f"Acting: `{p.get('template_id')}` dispatched"
                f"{_params(p.get('params'))}.")
    if t == "action.completed":
        return f"Done: `{p.get('template_id')}` took effect."
    if t == "action.failed":
        return (f"Failed: `{p.get('template_id')}` — "
                f"{_err(p)}.")
    if t == "action.refused":
        return f"Refused: `{p.get('template_id')}` — {_err(p)}."
    if t == "action.emergency":
        return (f"Emergency: `{p.get('rule_id')}` fired — "
                f"`{p.get('template_id')}` dispatched immediately.")
    if t == "plan.proposed":
        return (f"Planning: proposal `{p.get('plan_id', '?')}` — "
                f"{len(p.get('actions') or [])} action(s) "
                f"via {p.get('endpoint_id') or 'rules'}.")
    if t == "plan.reviewed":
        return (f"Reviewed: verdict `{p.get('verdict', '?')}`"
                + (f" — {len(p.get('violations') or [])} violation(s)."
                   if p.get("violations") else "."))
    if t == "plan.accepted":
        return f"Accepted: plan `{p.get('plan_id', '?')}` approved by gate."
    if t == "plan.rejected":
        return f"Rejected: plan refused — {_err(p)}."
    if t == "task.transition":
        return (f"Task `{p.get('task_id')}`: "
                f"{p.get('from_state') or 'new'} -> {p.get('to_state')}"
                + (f" ({p.get('reason')})" if p.get("reason") else "."))
    if t == "start.completed":
        c = p.get("conditions") or {}
        ok = ", ".join(k for k, v in c.items() if v)
        return (f"Start mode complete: {p.get('colonists', '?')} colonist(s) "
                f"— {ok}. Handing back to normal policy.")
    if t == "selfcheck.diagnosed":
        if p.get("noop"):
            return "Self-check: nothing wrong — no work invented."
        return (f"Self-check: found `{p.get('defect_class')}` "
                f"affecting {', '.join(p.get('affected') or [])} — "
                f"remedy: {p.get('remediation')}.")
    if t == "audit.verdict":
        return (f"Audit [{p.get('domain')}]: `{p.get('check_id')}` "
                f"-> {p.get('verdict', '?').upper()}"
                + (f" — {'; '.join(p.get('reasons') or [])}"
                   if p.get("reasons") else "."))
    if t == "improvement.promoted":
        return (f"Learned: candidate `{p.get('candidate_id')}` promoted — "
                f"pack {str(p.get('pack_hash'))[:12]}.")
    if t == "improvement.rejected":
        return (f"Not adopted: candidate `{p.get('candidate_id')}` "
                f"refused at {p.get('gate')} — "
                f"{'; '.join(p.get('reasons') or [])}.")
    if t == "episode.metrics":
        return (f"Episode `{p.get('episode_id')}`: refusal "
                f"{p.get('refusal_rate', 0):.0%}, verify-fail "
                f"{p.get('verify_failure_rate', 0):.0%}, tasks done "
                f"{p.get('task_completion_rate', 0):.0%}.")
    if t == "mutation.triggered":
        return (f"Reflecting: `{p.get('reason')}` trigger at poll "
                f"{p.get('poll')} — {p.get('evidence')}.")
    if t == "mutation.proposed":
        return (f"Mutation `{p.get('mutation_id')}` proposed by "
                f"{p.get('model', '?')} — {p.get('op_count')} op(s)"
                + (" [degraded]" if p.get("degraded") else "."))
    if t == "mutation.candidate":
        return (f"Mutation candidate `{p.get('candidate_id')}` written "
                f"for `{p.get('target_pack')}` — promotes next run.")
    if t == "mutation.rejected":
        return (f"Mutation refused at gate `{p.get('gate')}` — "
                f"{'; '.join(p.get('violations') or [])}.")
    if t == "mutation.promoted":
        return (f"Mutation `{p.get('candidate_id')}` promoted — pack "
                f"{str(p.get('pack_hash'))[:12]} (parent "
                f"{str(p.get('parent_hash'))[:12]}).")
    if t == "mutation.reverted":
        return (f"Mutation reverted: episode {p.get('episode_score')} vs "
                f"baseline {p.get('baseline_score')} — restored parent "
                f"{str(p.get('pack_hash'))[:12]}.")
    if t == "mutation.degraded":
        return (f"Mutation degraded: {p.get('detail')} "
                f"(trigger `{p.get('reason')}`).")
    if t == "mutation.noop":
        return (f"Mutation pass: no change — {p.get('rationale') or ''}"
                .rstrip())
    return f"{t}: {p}"  # structured echo — never blank


def _params(params) -> str:
    if isinstance(params, dict) and params:
        kv = ", ".join(f"{k}={v}" for k, v in
                       list(params.items())[:4])
        return f" ({kv})"
    return ""


def _err(p: dict) -> str:
    e = p.get("error") or {}
    return e.get("message") or e.get("code") or "unknown"


class FeedWriter:
    """Appends narrated entries to `state/feed.md` (atomic rewrite)."""

    def __init__(self, path: Path):
        self._path = Path(path)

    def write(self, env: dict) -> None:
        try:
            existing = self._path.read_text(encoding="utf-8") \
                if self._path.is_file() else "# Agent thought feed\n"
            tick = env.get("game_tick")
            line = (f"\n## tick {tick if isinstance(tick, int) else '?'} — "
                    f"`{env.get('event_type')}` ({env.get('event_id')})\n\n"
                    f"{render_event(env)}\n")
            write_atomic(self._path,
                         (existing + line).encode("utf-8"))
        except OSError:
            pass  # recorded by callers if needed; never fatal


def feed_sink(inner):
    """Wrap an event sink so every emitted event is also narrated.

    `inner` receives the envelope; the returned callable takes (env,
    feed_writer) — used as `sink = feed_sink(events.append)` then
    `sink(env, feed)`.
    """
    def emit(env, feed: FeedWriter | None = None):
        if inner is not None:
            inner(env)
        if feed is not None:
            feed.write(env)
    return emit
