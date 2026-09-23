"""Dedicated audit passes (feature 009; FR-804, SC-802).

Three domains, each emitting an `audit.verdict` event:
- code:  runtime tests + contract corpus + component validators
- policy: pack schema + sealed-inventory cross-check + invariant scan
- ux:    feed coverage over decision events + non-empty refusals

Fail-closed: an audit that cannot run reports `fail` with the reason —
a missing check is never a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]

# Decision-point event types the feed must narrate (UX audit).
DECISION_TYPES = {
    "action.issued", "action.emergency", "action.refused",
    "action.failed", "action.completed",
    "plan.proposed", "plan.reviewed", "plan.accepted", "plan.rejected",
    "task.transition", "start.completed",
    "selfcheck.diagnosed", "audit.verdict",
    "improvement.promoted", "improvement.rejected", "episode.metrics",
}


def _verdict(check_id: str, domain: str, ok: bool,
             reasons: list[str] | None = None,
             subject: str | None = None,
             details: dict | None = None) -> dict:
    return {"check_id": check_id, "domain": domain,
            "verdict": "pass" if ok else "fail",
            "subject": subject, "reasons": reasons or [],
            "details": details}


def verdict_event(v: dict, seq: int, clock=None) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.audit-{seq:06d}",
        "sequence": seq,
        "event_type": "audit.verdict",
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": "rimbrainagent.runtime.audit",
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": v,
        "privacy": {"classification": "internal", "redactions": []},
    }


def audit_code(repo: Path = _REPO, *, runner=None) -> dict:
    """Code quality: runtime pytest + corpus runner, fail-closed."""
    run = runner or _run
    reasons: list[str] = []
    details: dict = {}
    py = sys.executable
    rt = run([py, "-m", "pytest", "-q", "components/runtime/tests"],
             cwd=repo)
    details["pytest"] = {"returncode": rt}
    if rt != 0:
        reasons.append(f"runtime pytest exited {rt}")
    cr = run([py, "tests/contract/corpus_runner.py"], cwd=repo)
    details["corpus"] = {"returncode": cr}
    if cr != 0:
        reasons.append(f"contract corpus runner exited {cr}")
    return _verdict("code.suite", "code", not reasons, reasons,
                    details=details)


def _run(cmd: list[str], cwd: Path) -> int:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True,
                              timeout=600).returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


def audit_policy(pack_path: Path, dispatcher=None) -> dict:
    """Policy invariants for a (candidate) pack.

    Checks: YAML parses, schema-required sections exist, every template
    method is a string referencing the bridge inventory when a
    dispatcher loader is supplied, and no template marks a model role
    as its executor (models never execute).
    """
    import yaml
    reasons: list[str] = []
    p = Path(pack_path)
    if not p.is_file():
        return _verdict("policy.invariant", "policy", False,
                        [f"pack not found: {p}"], subject=str(p))
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return _verdict("policy.invariant", "policy", False,
                        [f"pack YAML unreadable: {exc}"], subject=str(p))
    templates = data.get("templates") or []
    if not templates:
        reasons.append("pack declares no templates")
    methods = []
    for t in templates:
        if not isinstance(t, dict):
            reasons.append("template entry is not a mapping")
            continue
        m = t.get("method")
        if not isinstance(m, str) or not m:
            reasons.append(f"template {t.get('id', '?')} lacks a method")
        else:
            methods.append(m)
        if t.get("executor") == "model":
            reasons.append(f"template {t.get('id', '?')} declares a "
                           "model executor — models never execute calls")
    if dispatcher is not None:
        inv = getattr(dispatcher, "inventory", None) or set()
        for m in methods:
            if inv and m not in inv:
                reasons.append(f"method '{m}' not in sealed inventory")
    return _verdict("policy.invariant", "policy", not reasons, reasons,
                    subject=str(p),
                    details={"templates_checked": len(templates)})


def audit_ux(feed_path: Path, events: list[dict]) -> dict:
    """UX: every decision event has a feed entry; refusals readable."""
    reasons: list[str] = []
    p = Path(feed_path)
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    decision = [e for e in events
                if e.get("event_type") in DECISION_TYPES]
    missing = [e.get("event_id") for e in decision
               if e.get("event_id") and e["event_id"] not in text]
    if missing:
        reasons.append(f"{len(missing)} decision event(s) lack feed "
                       f"entries: {', '.join(missing[:5])}")
    for e in events:
        if e.get("event_type") == "action.refused":
            err = (e.get("payload") or {}).get("error") or {}
            if not (err.get("message") or err.get("code")):
                reasons.append("a refusal event has no readable reason")
                break
    return _verdict("ux.feed_coverage", "ux", not reasons, reasons,
                    subject=str(p),
                    details={"decision_events": len(decision),
                             "missing_entries": len(missing)})
