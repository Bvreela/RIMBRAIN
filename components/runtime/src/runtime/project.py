"""Bus projection (feature 006; FR-504).

``project(events)`` deterministically folds canonical envelopes into a small
"where are we" view — counts per event_type, last action outcome, last plan
verdict, sequence span. ``rebuild(store)`` replays the log and writes
``projection.json`` via ``write_atomic``. The projection is a disposable
index: the log alone is authoritative.
"""

from __future__ import annotations

import json
from pathlib import Path

from .store import EventStore, write_atomic

__all__ = ["project", "rebuild"]


def project(events: list[dict]) -> dict:
    """Pure deterministic fold over canonical envelopes (SC-504)."""
    counts: dict[str, int] = {}
    last_action: dict | None = None
    last_plan: dict | None = None
    seqs: list[int] = []
    for env in events:
        et = env.get("event_type", "")
        counts[et] = counts.get(et, 0) + 1
        if isinstance(env.get("sequence"), int):
            seqs.append(env["sequence"])
        payload = env.get("payload") or {}
        if et.startswith("action."):
            last_action = {"event_type": et,
                           "template_id": payload.get("template_id"),
                           "outcome": payload.get("outcome"),
                           "error": (payload.get("error") or {}).get("code")}
        elif et.startswith("plan."):
            last_plan = dict(last_plan or {})
            last_plan.update({"event_type": et,
                              "plan_id": payload.get("plan_id")})
            for k in ("verdict", "code"):
                if payload.get(k) is not None:
                    last_plan[k] = payload[k]
    return {
        "counts_by_type": dict(sorted(counts.items())),
        "last_action": last_action,
        "last_plan": last_plan,
        "first_seq": seqs[0] if seqs else None,
        "last_seq": seqs[-1] if seqs else None,
        "total": len(events),
    }


def rebuild(store: EventStore, out: str | Path | None = None) -> dict:
    """Replay the log and atomically write ``projection.json``."""
    data = store.load()
    view = project(data["events"])
    view["corrupt_lines"] = data["corrupt_lines"]
    view["sequence_gaps"] = data["sequence_gaps"]
    target = Path(out) if out else store.dir / "projection.json"
    write_atomic(target, json.dumps(view, indent=2,
                                    sort_keys=True).encode() + b"\n")
    return view
