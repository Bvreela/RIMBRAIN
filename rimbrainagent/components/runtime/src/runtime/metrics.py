"""Episode learning metrics (feature 009; FR-807, SC-805).

Pure fold over a canonical event list — same events, same output.
Metrics: refusal_rate, verify_failure_rate, task_completion_rate,
ticks_to_baseline, event_span, raw counts.
"""

from __future__ import annotations

_TERMINAL = {"succeeded", "failed", "expired"}
_FAIL = {"failed", "expired"}


def episode_metrics(events: list[dict], episode_id: str = "ep-0000"
                    ) -> dict:
    """Fold canonical envelopes into the episode.metrics payload."""
    counts: dict[str, int] = {}
    issued = refused = 0
    terminal = succeeded = failed = 0
    seqs: list[int] = []
    ticks: list[int] = []
    for e in events:
        t = e.get("event_type", "?")
        counts[t] = counts.get(t, 0) + 1
        if isinstance(e.get("sequence"), int):
            seqs.append(e["sequence"])
        if isinstance(e.get("game_tick"), int):
            ticks.append(e["game_tick"])
        if t == "action.issued":
            issued += 1
        elif t == "action.refused":
            refused += 1
        elif t == "task.transition":
            to = (e.get("payload") or {}).get("to_state")
            if to in _TERMINAL:
                terminal += 1
                if to == "succeeded":
                    succeeded += 1
                else:
                    failed += 1
    return {
        "episode_id": episode_id,
        "refusal_rate": (refused / issued) if issued else 0.0,
        "verify_failure_rate": (failed / terminal) if terminal else 0.0,
        "task_completion_rate": (succeeded / terminal) if terminal else 0.0,
        "ticks_to_baseline": (max(ticks) - min(ticks)) if ticks else None,
        "event_span": {
            "count": len(events),
            "first_seq": min(seqs) if seqs else 0,
            "last_seq": max(seqs) if seqs else 0,
        },
        "counts": counts,
    }


def metrics_event(events: list[dict], episode_id: str, seq: int,
                  clock=None) -> dict:
    """Wrap the fold in a canonical envelope (payload schema FR-807)."""
    return {
        "schema_version": 0,
        "event_id": f"evt.metrics-{seq:06d}",
        "sequence": seq,
        "event_type": "episode.metrics",
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": "rimbrainagent.runtime.metrics",
        "correlation": {"episode": episode_id},
        "revisions": {"schema_version": 0},
        "payload": episode_metrics(events, episode_id),
        "privacy": {"classification": "internal", "redactions": []},
    }
