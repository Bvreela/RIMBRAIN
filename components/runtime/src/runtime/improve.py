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
            key = str(_dotted(e, pat.get("group_by", "")))
            hits.setdefault(key, []).append(e)
        for key, group in hits.items():
            if len(group) >= pat.get("min_count", 2):
                seqs = [g.get("sequence", 0) for g in group]
                findings.append({
                    "defect_class": pat["id"],
                    "affected": [key],
                    "remediation": pat.get("remediation"),
                    "count": len(group),
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


def propose(findings: list[dict], active_pack: dict,
            candidates_dir: Path) -> Path | None:
    """Rules-only remediation -> candidate pack file.

    Supported remediation: `fix_template_params`/`quarantine` for a
    chronically-refused template -> drop the template so the writer
    stops dispatching an always-failing action. Anything else -> None
    (recorded, not invented).
    """
    for f in findings:
        if f["remediation"] in ("fix_template_params",
                                "retune_lease_or_effect"):
            bad = set(f["affected"])
            cand = copy.deepcopy(active_pack)
            cand["templates"] = [t for t in cand.get("templates", [])
                                 if t.get("id") not in bad]
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
        # metrics validation: candidate must beat incumbent
        weights = cfg.get("metrics") or {}
        inc = score(episode_metrics(evs), weights)
        quarantined = {a for f in findings for a in f["affected"]}
        cand = score(predict_metrics(evs, quarantined), weights)
        if cand < inc:
            promoted = Path(packs_dir) / cand_path.name
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
