"""Self-improvement cycle (feature 009; FR-801/802/803/808).

Deterministic loop over canonical evidence:

    load events -> diagnose (defect patterns) -> propose candidate
    pack (rules-only remediation) -> audit -> validate metrics ->
    promote at episode boundary / reject / defer.

The cycle makes no game writes and never mutates the ACTIVE pack — a
promotion copies a validated candidate into the packs directory only
at an episode boundary (the improve mode itself is the boundary).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml

from .audit import audit_policy, audit_ux, verdict_event
from .metrics import episode_metrics, metrics_event

_PACKS = Path(__file__).resolve().parents[3] / "rimbrain" / "packs"


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


def _apply_ops(doc: dict, ops: list[dict] | None) -> bool:
    """FR-813: declarative pack mutations. Returns True if doc changed.

    Legacy op names compile to the packmut vocabulary (feature 016):
    `set_cfg` -> `set`, `append` -> `append`, `drop_template` ->
    `remove` on `templates.<id>`, `drop_rule` -> `remove` on every rule
    list (`universal.rules`, `emergency`, `combat.*.rules`)."""
    from . import packmut
    changed, _misses = packmut.apply_ops(
        doc, packmut.compile_legacy(ops, doc))
    return changed


def propose(findings: list[dict], active_pack: dict,
            candidates_dir: Path) -> Path | None:
    """Remediation -> candidate pack file.

    Dict remediation (`{ops: [...]}`) applies declarative mutations —
    set_cfg/append/drop_template/drop_rule — to a candidate copy.
    Legacy string remediations (`fix_template_params`,
    `retune_lease_or_effect`) quarantine the affected template.
    Anything else -> None (recorded, not invented).
    """
    for f in findings:
        rem = f.get("remediation")
        if isinstance(rem, dict) and rem.get("ops"):
            cand = copy.deepcopy(active_pack)
            if not _apply_ops(cand, rem["ops"]):
                continue  # ops changed nothing -> vacuous candidate
            cand["revision"] = str(cand.get("revision", "v0")) + \
                f"+mut.{f['defect_class']}"
            candidates_dir = Path(candidates_dir)
            candidates_dir.mkdir(parents=True, exist_ok=True)
            out = candidates_dir / f"cand-{f['defect_class']}.yaml"
            out.write_text(yaml.safe_dump(cand, sort_keys=False),
                           encoding="utf-8")
            return out
        if rem in ("fix_template_params", "retune_lease_or_effect"):
            bad = set(f["affected"])
            cand = copy.deepcopy(active_pack)
            remaining = [t for t in cand.get("templates", [])
                         if t.get("id") not in bad]
            if len(remaining) == len(cand.get("templates", [])):
                continue  # quarantine removes nothing -> vacuous candidate
            cand["templates"] = remaining
            cand["revision"] = str(cand.get("revision", "v0")) + \
                f"+quarantine.{f['defect_class']}"
            candidates_dir = Path(candidates_dir)
            candidates_dir.mkdir(parents=True, exist_ok=True)
            out = candidates_dir / (
                f"cand-{f['defect_class']}-"
                f"{'-'.join(sorted(bad))[:24]}.yaml")
            out.write_text(yaml.safe_dump(cand, sort_keys=False),
                           encoding="utf-8")
            return out
    return None


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


def run_improve(store, cfg: dict, *, active_pack: dict,
                packs_dir: Path = _PACKS, sink=None, clock=None,
                iterations: int | None = None, events=None,
                feed=None) -> dict:
    """Bounded improvement cycles. `events` may be injected for tests;
    otherwise loaded from the canonical store each iteration."""
    # `sink` is the canonical-events path; when the caller composes feed
    # narration into the sink (CLI does), `feed` is unused — never narrate
    # twice.
    if sink is not None:
        emit = sink
    elif feed is not None:
        emit = feed.write
    else:
        emit = lambda env: None
    max_iter = iterations or (cfg.get("cadence") or {}
                              ).get("max_iterations", 20)
    min_events = (cfg.get("metrics") or {}).get("min_events", 5)
    outcomes, seq = [], 0
    for i in range(max_iter):
        evs = events if events is not None else \
            store.load()["events"]
        cycle_id = f"cycle-{i:06d}"
        findings = diagnose(evs, cfg)
        seq += 1
        emit(diagnosed_event(cycle_id, findings, seq, clock))
        if not findings:
            outcomes.append({"cycle": cycle_id, "verdict": "noop"})
            continue
        cand_path = propose(findings, active_pack,
                            Path(packs_dir) / "candidates")
        cand_id = cand_path.stem if cand_path else f"cand-{cycle_id}"
        if cand_path is None:
            seq += 1
            emit(_env("improvement.rejected", {
                "candidate_id": cand_id, "gate": "defer",
                "reasons": ["no rules-only remediation for findings"],
                "source_cycle": cycle_id}, seq, clock))
            outcomes.append({"cycle": cycle_id, "verdict": "defer"})
            continue
        # audit gate (policy invariants; ux coverage over the cycle)
        v = audit_policy(cand_path)
        seq += 1
        emit(verdict_event(v, seq, clock))
        if v["verdict"] != "pass":
            seq += 1
            emit(_env("improvement.rejected", {
                "candidate_id": cand_id, "gate": "audit",
                "reasons": v["reasons"],
                "source_cycle": cycle_id}, seq, clock))
            outcomes.append({"cycle": cycle_id, "verdict": "audit_fail"})
            continue
        # evidence floor -> defer
        if len(evs) < min_events:
            seq += 1
            emit(_env("improvement.rejected", {
                "candidate_id": cand_id, "gate": "defer",
                "reasons": [f"evidence thin: {len(evs)} events "
                            f"< {min_events}"],
                "source_cycle": cycle_id}, seq, clock))
            outcomes.append({"cycle": cycle_id, "verdict": "defer"})
            continue
        # metrics validation: candidate must beat incumbent; ops-mutation
        # candidates (colony-health defects) can't move dispatch metrics —
        # a tie is enough for them (FR-813; promotion gate still applies)
        weights = cfg.get("metrics") or {}
        inc = score(episode_metrics(evs), weights)
        quarantined = {a for f in findings for a in f["affected"]}
        cand = score(predict_metrics(evs, quarantined), weights)
        cls = cand_path.stem[len("cand-"):].split("-")[0]
        ops_rem = next((isinstance(f.get("remediation"), dict)
                        for f in findings if f["defect_class"] == cls),
                       False)
        if cand < inc or (ops_rem and cand <= inc):
            promoted = Path(packs_dir) / cand_path.stem / "pack.yaml"
            promoted.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cand_path, promoted)
            seq += 1
            emit(_env("improvement.promoted", {
                "candidate_id": cand_id,
                "pack_hash": _hash_pack(promoted),
                "episode_boundary": True,
                "metrics": {"incumbent_score": inc,
                            "candidate_score": cand},
                "source_cycle": cycle_id}, seq, clock))
            outcomes.append({"cycle": cycle_id, "verdict": "promoted",
                             "pack": str(promoted)})
            break  # one promotion per run; next cycle re-diagnoses
        seq += 1
        emit(_env("improvement.rejected", {
            "candidate_id": cand_id, "gate": "metrics",
            "reasons": [f"candidate score {cand:.3f} not better "
                        f"than incumbent {inc:.3f}"],
            "metrics": {"incumbent_score": inc,
                        "candidate_score": cand},
            "source_cycle": cycle_id}, seq, clock))
        outcomes.append({"cycle": cycle_id, "verdict": "metrics_fail"})
    seq += 1
    emit(metrics_event(evs if events is not None else
                       store.load()["events"],
                       f"improve-{i}", seq, clock))
    return {"ok": True, "cycles": outcomes}


def _hash_pack(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


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
