"""Improvement evidence (feature 009; FR-801/802/803/808) — reduced to
evidence functions in feature 017 (US4): ``diagnose`` (defect patterns
over canonical events), ``score``/``predict_metrics`` (episode metrics),
``diagnosed_event``/``_env`` (evidence envelopes). The proposal/gate/
promotion machinery lives in ``evolve.py`` — one reflection pipeline.

The cycle makes no game writes and never mutates the ACTIVE pack — a
promotion copies a validated candidate into the packs directory only
at an episode boundary.
"""

from __future__ import annotations

from .metrics import episode_metrics


def _dotted(d, path):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


_CMP = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "in": lambda a, b: a in (b or []),
    "contains": lambda a, b: a is not None and b in a,
    "present": lambda a, b: a is not None,
    "absent": lambda a, b: a is None,
}


def _match_where(pred: dict, event: dict) -> bool:
    """FR-812: predicate over an event's fields ({field, op, value})."""
    val = _dotted(event, pred.get("field", ""))
    return _CMP.get(pred.get("op", "eq"), lambda a, b: False)(
        val, pred.get("value"))


def _windowed_max(group: list[dict], window: int) -> int:
    """Max events of a group inside any `window`-tick span (game year etc.)."""
    ticks = sorted(e.get("game_tick") or 0 for e in group)
    best = j = 0
    for i, t in enumerate(ticks):
        while ticks[j] < t - window:
            j += 1
        best = max(best, i - j + 1)
    return best


def diagnose(events: list[dict], cfg: dict) -> list[dict]:
    """Group events by pack-declared defect patterns -> findings."""
    findings = []
    for pat in (cfg.get("defect_patterns") or []):
        hits: dict[str, list[dict]] = {}
        for e in events:
            if e.get("event_type") != pat.get("event_type"):
                continue
            p = e.get("payload") or {}
            if pat.get("match_value") and \
                    _dotted(e, pat["group_by"]) != pat["match_value"]:
                continue
            if pat.get("match_to_state") and \
                    p.get("to_state") not in pat["match_to_state"]:
                continue
            if pat.get("where") and not _match_where(pat["where"], e):
                continue
            key = str(_dotted(e, pat.get("group_by", "")) or "")
            if not key:  # no groupable identity -> not a template defect
                continue
            hits.setdefault(key, []).append(e)
        window = pat.get("window_ticks")
        for key, group in hits.items():
            count = _windowed_max(group, window) if window else len(group)
            if count >= pat.get("min_count", 2):
                seqs = [g.get("sequence", 0) for g in group]
                findings.append({
                    "defect_class": pat["id"],
                    "affected": [key],
                    "remediation": pat.get("remediation"),
                    "count": count,
                    "span": {"first_seq": min(seqs),
                             "last_seq": max(seqs)},
                })
    return findings


def diagnosed_event(cycle_id: str, findings: list[dict], seq: int,
                    clock=None) -> dict:
    payload = {"cycle_id": cycle_id,
               "finding_count": len(findings), "noop": not findings}
    if findings:
        f = findings[0]  # one event per cycle head; details in affected
        payload.update({"defect_class": f["defect_class"],
                        "span": f["span"],
                        "remediation": f["remediation"],
                        "affected": f["affected"]})
    return _env("selfcheck.diagnosed", payload, seq, clock)


def score(metrics: dict, weights: dict) -> float:
    """Lower is better: weighted badness (completion inverted)."""
    return (weights.get("refusal_rate", 0) *
            metrics.get("refusal_rate", 0)
            + weights.get("verify_failure_rate", 0) *
            metrics.get("verify_failure_rate", 0)
            + weights.get("task_completion_rate", 0) *
            (1 - metrics.get("task_completion_rate", 0)))


def predict_metrics(events: list[dict], quarantined: set[str]) -> dict:
    """Candidate metrics = evidence replayed minus the quarantined
    template's refused/issued events (counterfactual floor)."""
    kept = [e for e in events
            if not (e.get("event_type") in ("action.refused",
                                           "action.issued")
                    and (e.get("payload") or {}).get("template_id")
                    in quarantined)]
    return episode_metrics(kept)


def _env(t: str, payload: dict, seq: int, clock=None) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.improve-{seq:06d}",
        "sequence": seq,
        "event_type": t,
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": "rimbrainagent.runtime.improve",
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": payload,
        "privacy": {"classification": "internal", "redactions": []},
    }
