"""Reflection pipeline (feature 017, US4; ex-mutate.py feature 016).

One digest -> propose -> compile -> gate -> candidate -> boundary-promote
path covering every mutable pack surface (``phases``, ``action_list``,
``decide``, ``reflexes``, ``rules``, ``options``, ``senses``,
``metrics`` — see :data:`packmut.MUTABLE_ROOTS`):

    triggers (cadence / failure / near-failure, pack ``mutate:`` cfg)
    -> failure digest -> rimbrain.improve proposal (rules-only degrade)
    -> deterministic gate -> packs/candidates/cand-mut-*.yaml
    -> pending lineage row in state/mutations.jsonl

The pass never touches the loaded pack document, the active pack file,
or the bridge — candidates promote only at the NEXT run's boundary
(:func:`boundary`, called before ``load_pack``), where a regressed
promotion auto-reverts to its recorded parent. ``dispatch.pack_drift``
stays absolute.

Also hosts the absorbed feature-009 improve-mode harness
(:func:`run_improve`, :func:`propose`) and the feature-005 planner's
candidate promotion (:func:`materialize_candidate`) — one gate, one
candidate format, one lineage (T037).
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from collections import deque
from pathlib import Path

import yaml

from . import improve, packmut, templates
from ._root import repo_root
from .audit import audit_policy, verdict_event
from .bindings import resolve_role
from .client import openai_compat_chat
from .metrics import episode_metrics, metrics_event
from .planning import extract_json
from .store import write_atomic

SOURCE = "rimbrainagent.runtime.evolve"
MUTATION_SCHEMA = (repo_root() / "components" / "contracts" / "schemas" /
                   "runtime" / "mutation.schema.json")
LINEAGE = "mutations.jsonl"
_GOAL_NS = ("start.", "govern.", "phase.", "combat.")
_TERMINAL = {"succeeded", "failed", "expired"}
_FAIL = {"failed", "expired"}
_PACKS = Path(__file__).resolve().parents[3] / "rimbrain" / "packs"


# -- canonical envelopes ----------------------------------------------------

def mutation_event(event_type: str, payload: dict, seq: int,
                   clock=None) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.mutate-{seq:06d}",
        "sequence": seq,
        "event_type": event_type,
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": SOURCE,
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": payload,
        "privacy": {"classification": "internal", "redactions": []},
    }


# -- per-run pass state ------------------------------------------------------

class PassState:
    """Disposable per-run reflection state (data-model: PassState).

    ``note()`` sees every canonical envelope the run emits (wired onto the
    sink); ``note_outcome()`` sees each poll's step outcome. Both feed the
    trigger scan, which only looks at events since the last pass (``mark``).
    Owned by ``RunState.improve_state`` in the unified loop (T038).
    """

    def __init__(self, cfg: dict | None = None, *, window: int = 600):
        self.cfg = cfg or {}
        self.window: deque[tuple[int, dict]] = deque(maxlen=window)
        self._n = 0                 # total envelopes noted
        self.mark = 0               # _n at the last pass
        self.terminal_since = 0     # terminal goal transitions since mark
        self.blocked_run = 0        # consecutive 'blocked' step outcomes
        self.passes = 0
        self.last_pass_poll = -(10 ** 9)
        self.last_verdict: str | None = None
        self.pending: str | None = None      # candidate awaiting boundary
        self.lineage: str | None = None      # promoted pack hash prefix
        self._decisions: list | None = None  # run's decision rows (ref)
        self._dmark = 0                      # decisions len at last pass

    def note(self, env: dict) -> None:
        self._n += 1
        self.window.append((self._n, env))
        if env.get("event_type") != "task.transition":
            return
        p = env.get("payload") or {}
        tid = str(p.get("task_id") or "")
        if p.get("to_state") in _TERMINAL and \
                tid.startswith(_GOAL_NS):
            self.terminal_since += 1

    def note_outcome(self, out: dict | None) -> None:
        if isinstance(out, dict) and out.get("state") == "blocked":
            self.blocked_run += 1
        else:
            self.blocked_run = 0

    def note_decisions(self, rows: list) -> None:
        """Keep a ref to the run's decisions list; escalation steps emit
        rows with source '<goal>:escalate' rather than canonical events."""
        self._decisions = rows

    def escalations(self) -> int:
        if not self._decisions:
            return 0
        return sum(1 for r in self._decisions[self._dmark:]
                   if ":escalate" in str(r.get("source") or ""))

    def since_mark(self) -> list[dict]:
        return [e for i, e in self.window if i > self.mark]

    def view(self) -> dict:
        """planning.json `mutation` block (US4)."""
        return {"passes": self.passes,
                "goals_since_pass": self.terminal_since,
                "last_verdict": self.last_verdict,
                "pending_candidate": self.pending,
                "active_lineage": self.lineage}


# -- lineage (state/mutations.jsonl) -----------------------------------------

def _lineage_path(state_dir: Path) -> Path:
    return Path(state_dir) / LINEAGE


def lineage_rows(state_dir: Path) -> list[dict]:
    p = _lineage_path(state_dir)
    rows = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return [r for r in rows if isinstance(r, dict)]


def _append_lineage(state_dir: Path, row: dict) -> None:
    p = _lineage_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _mark_lineage(state_dir: Path, candidate_id: str, state: str) -> None:
    """Rewrite rows matching candidate_id with a new state (the file is a
    small append-log; a rewrite keeps the latest state queryable)."""
    p = _lineage_path(state_dir)
    rows = lineage_rows(state_dir)
    for r in rows:
        if r.get("candidate_id") == candidate_id:
            r["state"] = state
    write_atomic(p, ("\n".join(json.dumps(r, sort_keys=True)
                              for r in rows) + "\n").encode())


# -- triggers (FR-1402) -------------------------------------------------------

def _improve_cfg(pack: dict, cfg: dict) -> dict:
    """Defect-pattern config for near_failure detection: the active pack's
    own `improve:` section first, else the pack named by
    `mutate.defect_pack` (default improve-v0) — fail-open to {}."""
    own = pack.get("improve") or {}
    if own.get("defect_patterns"):
        return own
    pid = (cfg.get("defect_pack") or "improve-v0")
    try:
        return (templates.load_pack(pid)["pack"].get("improve") or {})
    except Exception:
        return {}


def check_triggers(ps: PassState, pack: dict, poll: int) -> tuple[str | None, dict]:
    """Evaluate the pack's `mutate:` policy against events since the last
    pass. Returns (reason, evidence) or (None, {})."""
    cfg = ps.cfg
    if not cfg:
        return None, {}
    cooldown = int(cfg.get("cooldown_polls") or 0)
    if poll - ps.last_pass_poll < cooldown:
        return None, {}
    if ps.passes >= int(cfg.get("max_passes_per_run") or 0):
        return None, {}
    recent = ps.since_mark()
    transitions = [(e.get("payload") or {}) for e in recent
                   if e.get("event_type") == "task.transition"
                   and str((e.get("payload") or {}).get("task_id") or "")
                   .startswith(_GOAL_NS)]
    fails = [t for t in transitions if t.get("to_state") in _FAIL]
    if cfg.get("on_failure") and fails:
        return "failure", {"tasks": [t.get("task_id") for t in fails],
                           "reasons": [t.get("reason") for t in fails]}
    nf = cfg.get("near_failure") or {}
    ev: dict = {}
    req = [t for t in transitions if t.get("to_state") == "requeued"]
    if len(req) >= int(nf.get("requeues") or 2):
        ev["requeued"] = [t.get("task_id") for t in req]
    refused = [e for e in recent if e.get("event_type") == "action.refused"]
    if len(refused) >= int(nf.get("refusals") or 3):
        ev["refusals"] = [(e.get("payload") or {}).get("template_id")
                          for e in refused]
    if ps.blocked_run >= int(nf.get("blocked_polls") or 15):
        ev["blocked_polls"] = ps.blocked_run
    if nf.get("escalate"):
        esc = ps.escalations()
        if esc:
            ev["escalations"] = esc
    if nf.get("defect_patterns"):
        findings = improve.diagnose(recent, _improve_cfg(pack, cfg))
        if findings:
            ev["defects"] = [f["defect_class"] for f in findings]
    if ev:
        return "near_failure", ev
    if ps.terminal_since >= int(cfg.get("goals_per_pass") or 10):
        return "cadence", {"terminal_goals": ps.terminal_since}
    return None, {}


# -- digest (FR-1403) ---------------------------------------------------------

def _goal_specs(pack: dict) -> dict:
    """Ledger task id -> goal/step spec, v1 surfaces (feature 017):
    prescriptive phase steps -> ``start.<uid>``, phase goals ->
    ``phase.<pid>.<gid>``, standing goals -> ``govern.<gid>``, combat
    rounds -> ``combat.<rid>``."""
    out = {}
    for ph in templates.phases_of(pack):
        pid = ph.get("id")
        if ph.get("kind") == "combat":
            for name, sec in (ph.get("combat") or {}).items():
                for g in (sec or {}).get("rounds") or []:
                    if isinstance(g, dict) and g.get("id"):
                        out[f"combat.{g['id']}"] = g
            continue
        for g in ph.get("steps") or []:
            if isinstance(g, dict) and g.get("id"):
                out[f"start.{g['id']}"] = g
        for g in ph.get("goals") or []:
            if isinstance(g, dict) and g.get("id"):
                out[f"phase.{pid}.{g['id']}"] = g
    for g in templates.standing_goals_of(pack):
        if g.get("id"):
            out[f"govern.{g['id']}"] = g
    return out


def _spec_brief(spec: dict | None) -> dict | None:
    if not isinstance(spec, dict):
        return None
    return {k: spec.get(k) for k in
            ("id", "when", "requires", "effect", "retry_polls",
             "attempts", "lease_ticks") if spec.get(k) is not None} | {
        "steps": [s.get("template") for s in spec.get("steps") or []
                  if isinstance(s, dict)] or None}


def build_digest(ps: PassState, ledger, pack_loaded: dict, pack: dict,
                 reason: str, evidence: dict, tick: int, poll: int,
                 limit: int = 8000) -> dict:
    """Bounded model input: failing/stuck goals + specs, recent refusals,
    defect findings, pack identity, op vocabulary."""
    specs = _goal_specs(pack)
    recent = ps.since_mark()
    goals = []
    for tid, t in (ledger.tasks or {}).items():
        if not str(tid).startswith(_GOAL_NS):
            continue
        st = t.get("state")
        if st not in _TERMINAL and st not in ("verifying", "dispatched",
                                            "proposed", "locked"):
            continue
        entry = {"id": tid, "state": st, "attempts": t.get("attempts", 0)}
        brief = _spec_brief(specs.get(tid))
        if brief:
            entry["spec"] = brief
        goals.append(entry)
    bad_actions = [{"template_id": (e.get("payload") or {})
                    .get("template_id"),
                    "error": ((e.get("payload") or {}).get("error") or {})
                    .get("code")}
                   for e in recent
                   if e.get("event_type") in ("action.refused",
                                              "action.failed")][:25]
    digest = {
        "pack": {"id": pack.get("pack_id", "?"),
                 "hash": pack_loaded.get("hash")},
        "tick": tick, "poll": poll,
        "trigger": {"reason": reason, "evidence": evidence},
        "goals": goals[:40],
        "action_failures": bad_actions,
        "defects": improve.diagnose(recent, _improve_cfg(pack, ps.cfg))[:10],
        "mutation_contract": {
            "ops": ["set <dotted.path> <value>",
                    "append <dotted.path> <value>",
                    "remove <dotted.path>",
                    "upsert <list.path> <obj-with-id>"],
            "path_rule": "segments walk dict keys; a segment matching a "
                         "list element's 'id' descends into it; v1 "
                         "surfaces only (v0 paths auto-rewrite)",
            "max_ops": int(ps.cfg.get("max_ops") or 5)},
        "pack_sections": sorted(k for k in pack.keys()
                                if k not in ("templates", "goal_options",
                                             "capabilities")),
        "template_ids": [t.get("id") for t in templates.templates_of(pack)],
    }
    while len(json.dumps(digest, default=str)) > limit and digest["goals"]:
        digest["goals"].pop()  # shrink the biggest section first
    return digest


# -- reflect (FR-1404) ---------------------------------------------------------

def _validate_proposal(doc: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return []
    try:
        schema = json.loads(MUTATION_SCHEMA.read_text(encoding="utf-8"))
    except OSError:
        return []
    return [f"{list(e.absolute_path) or '$'}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema)
            .iter_errors(doc)][:25]


def _finalize(doc: dict, pack_loaded: dict) -> dict:
    doc = dict(doc)
    doc.setdefault("schema_version", 0)
    if not doc.get("mutation_id"):
        import hashlib
        tag = hashlib.sha256(json.dumps(
            doc, sort_keys=True, default=str).encode()).hexdigest()[:8]
        doc["mutation_id"] = f"mut.auto-{tag}"
    doc.setdefault("base_revision", pack_loaded["hash"])
    doc.setdefault("analysis", {"failure_paths": [], "likely_paths": []})
    doc.setdefault("mutations", [])
    doc.setdefault("rationale", "")
    return doc


def _prompt(digest: dict) -> list[dict]:
    return [
        {"role": "system", "content":
         "You are rimbrain.improve, the mutation planner for a RimWorld "
         "colony policy pack. Analyze the failure digest: which failure "
         "paths triggered or look likely, and why goals are failing. Then "
         "output ONLY a JSON object matching the MutationProposal contract "
         "- one best change-set, no prose. Never invent template ids or "
         "pack sections that are not in the digest."},
        {"role": "user", "content":
         "Failure digest:\n" + json.dumps(digest, sort_keys=True,
                                          default=str)
         + "\n\nEmit exactly: {\"schema_version\": 0, \"mutation_id\": "
           "\"mut.<slug>\", \"base_revision\": \"<pack hash>\", "
           "\"analysis\": {\"failure_paths\": [...], \"likely_paths\": "
           "[...]}, \"mutations\": [{\"op\": \"set|append|remove|upsert\", "
           "\"path\": \"<dotted.path>\", \"value\": ...}], "
           "\"rationale\": \"<why>\"}"},
    ]


def reflect(ps: PassState, digest: dict, pack_loaded: dict, pack: dict,
            reason: str, *, resolver=resolve_role, chat=openai_compat_chat,
            usage_tracker=None) -> dict:
    """rimbrain.improve call -> {ok, proposal|noop, ...} or degraded.

    Terminal ``rules-only`` resolution applies the defect patterns' own
    declared remediations (feature-009 ops compile to packmut); a pass
    with no applicable remediation returns ``noop``.
    """
    res = resolver("rimbrain.improve", probe_live=False)
    if not res.get("ok"):
        return {"ok": False, "degraded": True,
                "error": {"code": "evolve.unresolved",
                          "message": res["error"]["message"]}}
    resolved = res["resolved"]
    if resolved.get("kind") == "fallback":
        # rules-only: deterministic remediations declared by the pack's
        # defect patterns — the same fixes improve mode would apply,
        # compiled to the packmut vocabulary so the gate can replay them
        findings = improve.diagnose(ps.since_mark(),
                                    _improve_cfg(pack, ps.cfg))
        hit = next((f for f in findings
                    if isinstance(f.get("remediation"), dict)
                    and packmut.compile_legacy(
                        f["remediation"].get("ops"), pack)), None)
        ops = (packmut.compile_legacy(hit["remediation"]["ops"], pack)
               if hit else None)
        if not ops:
            return {"ok": False, "degraded": True,
                    "error": {"code": "evolve.rules_only_noop",
                              "message": "rules-only path found no "
                                         "applicable remediation"}}
        return {"ok": True, "endpoint_id": resolved["name"],
                "model": resolved["name"], "degraded": True,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "proposal": _finalize({
                    "mutation_id": "mut.rules-only",
                    "analysis": {"failure_paths": [f["defect_class"]
                                                 for f in findings],
                                 "likely_paths": []},
                    "mutations": ops,
                    "rationale": "deterministic remediation for "
                                 "pack-declared defect patterns"},
                    pack_loaded)}
    r = chat(resolved["endpoint_id"], resolved["model"], _prompt(digest),
             usage_tracker=usage_tracker)
    if not r.get("ok"):
        return {"ok": False, "degraded": True,
                "error": {"code": "evolve.endpoint_error",
                          "message": r["error"]["message"]}}
    usage = (r.get("body") or {}).get("usage") or {}
    text = ((r.get("body") or {}).get("choices") or [{}])[0] \
        .get("message", {}).get("content")
    doc = extract_json(text or "")
    if doc is None:
        return {"ok": False,
                "error": {"code": "evolve.malformed",
                          "message": "improve output had no parseable JSON"},
                "violations": ["no JSON object in model output"],
                "endpoint_id": resolved["endpoint_id"],
                "model": resolved["model"]}
    doc = _finalize(doc, pack_loaded)
    problems = _validate_proposal(doc)
    if problems:
        return {"ok": False,
                "error": {"code": "evolve.malformed",
                          "message": "proposal fails mutation.schema.json"},
                "violations": problems,
                "endpoint_id": resolved["endpoint_id"],
                "model": resolved["model"]}
    return {"ok": True, "proposal": doc,
            "endpoint_id": resolved["endpoint_id"],
            "model": resolved["model"],
            "degraded": bool(res.get("degraded")),
            "usage": {"prompt_tokens": int(usage.get("prompt_tokens") or 0),
                      "completion_tokens":
                          int(usage.get("completion_tokens") or 0)}}


# -- the one candidate gate (T037) ---------------------------------------------

def validate_candidate(doc: dict, *, fair: bool) -> list[str]:
    """Structural validation every candidate path shares (T037):
    schema (``validate_pack``) + sealed inventory + policy vocabulary +
    fair-class. Returns a violations list — empty means adoptable."""
    violations = templates.validate_pack(doc)
    caps = (doc.get("capabilities") or {}).get("templates")
    tmpls = caps if isinstance(caps, list) else (doc.get("templates") or [])
    if not tmpls:
        violations.append("no action templates")
    unknown = sorted({t.get("method") for t in tmpls}
                     - templates.inventory_methods())
    if unknown:
        violations.append(f"methods not in sealed inventory: {unknown}")
    if doc.get("policy_version") is not None:
        from .policy import validate_policy
        violations += validate_policy(doc)
    if fair:
        bad = sorted({t.get("method") for t in tmpls
                      if str(t.get("method") or "").startswith("dev.")})
        if bad or doc.get("class") == "dev":
            violations.append("fair run cannot adopt dev-class "
                              f"content: {bad or 'class=dev'}")
    return violations


def gate(proposal: dict, pack_loaded: dict, pack: dict, cfg: dict,
         fair: bool) -> dict:
    """Deterministic validation: budget -> stale -> vacuous -> validity."""
    ops = proposal.get("mutations") or []
    max_ops = int(cfg.get("max_ops") or 5)
    if len(ops) > max_ops:
        return {"ok": False, "gate": "budget",
                "violations": [f"{len(ops)} ops > max_ops {max_ops}"]}
    if proposal.get("base_revision") != pack_loaded.get("hash"):
        return {"ok": False, "gate": "stale",
                "violations": ["base_revision != active pack hash"]}
    cand = copy.deepcopy(pack)
    changed, misses = packmut.apply_ops(cand, ops)
    if misses:
        return {"ok": False, "gate": "validation", "violations": misses}
    if not changed or cand == pack:
        return {"ok": False, "gate": "vacuous",
                "violations": ["mutation set changed nothing"]}
    problems = validate_candidate(cand, fair=fair)
    if problems:
        return {"ok": False, "gate": "validation",
                "violations": problems}
    return {"ok": True, "doc": cand}


def materialize(doc: dict, pack_id: str, ps: PassState,
                state_dir: Path, emit, seq: list[int],
                clock=None, mutation_id=None) -> Path:
    """Write the gated doc as a flat candidate + pending lineage row."""
    cand_dir = templates.packs_dir() / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    digest = templates._hash_of(doc)
    slug = re.sub(r"[^a-z0-9-]+", "-",
                  (mutation_id or "mut").lower())[:40].strip("-")
    out = cand_dir / f"cand-mut-{slug}-{digest[:8]}.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    _append_lineage(state_dir, {
        "candidate_id": out.stem, "target_pack": pack_id,
        "candidate_path": str(out), "candidate_hash": digest,
        "state": "pending"})
    seq[0] += 1
    emit(mutation_event("mutation.candidate", {
        "candidate_id": out.stem, "path": str(out), "hash": digest,
        "target_pack": pack_id, "mutation_id": mutation_id},
        seq[0], clock))
    ps.pending = out.stem
    return out


# -- feature-005 planner promotion (absorbed; T034) ----------------------------

def _compile_plan_ops(mutations: list) -> list[dict]:
    """feature-005 `policy_mutations` vocabulary -> packmut ops:
    add_template -> append capabilities.templates; add_emergency ->
    upsert reflexes; edit_decision_map -> append decision_map (retained
    v0 surface — inert under v1, kept for replay)."""
    ops = []
    for mut in mutations or []:
        op, patch = mut.get("op"), mut.get("patch") or {}
        if op == "add_template":
            ops.append({"op": "append", "path": "templates",
                        "value": patch})
        elif op == "add_emergency":
            rule = dict(patch)
            rule.setdefault("id", mut.get("target") or "rule")
            ops.append({"op": "upsert", "path": "emergency",
                        "value": rule})
        elif op == "edit_decision_map":
            ops.append({"op": "append", "path": "decision_map",
                        "value": patch})
    return ops


def materialize_candidate(pack_file: str, base_doc: dict,
                          mutations: list) -> dict:
    """Write ``candidates/<file>-<sha8>.yaml``; re-validate before
    returning. The same gate vocabulary as the reflect pass — one
    candidate format across every mutation path (T037)."""
    doc = copy.deepcopy(base_doc)
    ops = _compile_plan_ops(mutations)
    _changed, misses = packmut.apply_ops(doc, ops)
    problems = list(misses) + validate_candidate(doc, fair=False)
    if problems:
        return {"ok": False,
                "error": {"code": "plan.mutation_invalid",
                          "message": "mutated candidate fails pack "
                                     "validation",
                          "retryable": False,
                          "details": {"issues": problems}}}
    digest = templates._hash_of(doc)
    out_dir = templates.packs_dir() / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{pack_file}-{digest[:8]}.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return {"ok": True, "path": str(out), "hash": digest, "doc": doc}


# -- feature-009 improve harness (absorbed; T035) ------------------------------

def _apply_ops(doc: dict, ops: list[dict] | None) -> bool:
    """FR-813: declarative pack mutations. Returns True if doc changed.

    Legacy op names compile to the packmut vocabulary:
    `set_cfg` -> `set`, `append` -> `append`, `drop_template` ->
    `remove` on `templates.<id>`, `drop_rule` -> `remove` on every rule
    list (`rules`, `reflexes`, `combat.*.rules`)."""
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
            remaining = [t for t in
                         templates.templates_of(cand)
                         if t.get("id") not in bad]
            if len(remaining) == len(templates.templates_of(cand)):
                continue  # quarantine removes nothing -> vacuous candidate
            cand["templates"] = remaining
            if isinstance(cand.get("capabilities"), dict):
                cand["capabilities"]["templates"] = remaining
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


def _hash_pack(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


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
        findings = improve.diagnose(evs, cfg)
        seq += 1
        emit(improve.diagnosed_event(cycle_id, findings, seq, clock))
        if not findings:
            outcomes.append({"cycle": cycle_id, "verdict": "noop"})
            continue
        cand_path = propose(findings, active_pack,
                            Path(packs_dir) / "candidates")
        cand_id = cand_path.stem if cand_path else f"cand-{cycle_id}"
        if cand_path is None:
            seq += 1
            emit(improve._env("improvement.rejected", {
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
            emit(improve._env("improvement.rejected", {
                "candidate_id": cand_id, "gate": "audit",
                "reasons": v["reasons"],
                "source_cycle": cycle_id}, seq, clock))
            outcomes.append({"cycle": cycle_id, "verdict": "audit_fail"})
            continue
        # evidence floor -> defer
        if len(evs) < min_events:
            seq += 1
            emit(improve._env("improvement.rejected", {
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
        inc = improve.score(episode_metrics(evs), weights)
        quarantined = {a for f in findings for a in f["affected"]}
        cand = improve.score(improve.predict_metrics(evs, quarantined),
                             weights)
        cls = cand_path.stem[len("cand-"):].split("-")[0]
        ops_rem = next((isinstance(f.get("remediation"), dict)
                        for f in findings if f["defect_class"] == cls),
                       False)
        if cand < inc or (ops_rem and cand <= inc):
            promoted = Path(packs_dir) / cand_path.stem / "pack.yaml"
            promoted.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cand_path, promoted)
            seq += 1
            emit(improve._env("improvement.promoted", {
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
        emit(improve._env("improvement.rejected", {
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


# -- the pass (FR-1401) --------------------------------------------------------

def maybe_trigger(ps: PassState, *, dispatcher, ledger, pack_loaded: dict,
                  pack: dict, pack_id: str, state_dir: Path, tick: int,
                  poll: int, fair: bool, emit, clock=None,
                  resolver=None, chat=None,
                  usage_tracker=None,
                  force: bool | str = False) -> dict | None:
    """One reflection pass when a trigger fires; None when nothing fired.
    ``force`` runs a pass unconditionally (the ``--stage reflect``
    debug entry); a string force supplies the reason verbatim (the
    fast-evolve day triggers, feature 021). Never raises — a pass
    failure is an event, not a crash."""
    resolver = resolver or resolve_role
    chat = chat or openai_compat_chat
    reason, evidence = ((force, {}) if isinstance(force, str)
                        else ("manual", {}) if force
                        else check_triggers(ps, pack, poll))
    if reason is None:
        return None
    seq = [max(getattr(dispatcher, "_events", 0),
               getattr(ledger, "_events", 0)) + ps._n]

    def _emit(t, payload):
        seq[0] += 1
        emit(mutation_event(t, payload, seq[0], clock))

    ps.mark = ps._n
    ps._dmark = len(ps._decisions or [])
    ps.terminal_since = 0
    ps.last_pass_poll = poll
    ps.passes += 1
    _emit("mutation.triggered", {"reason": reason, "evidence": evidence,
                                 "poll": poll})
    digest = build_digest(ps, ledger, pack_loaded, pack, reason, evidence,
                          tick, poll)
    prop = reflect(ps, digest, pack_loaded, pack, reason,
                   resolver=resolver, chat=chat,
                   usage_tracker=usage_tracker)
    if not prop.get("ok"):
        if prop.get("degraded"):
            ps.last_verdict = "degraded"
            _emit("mutation.degraded", {
                "reason": reason,
                "detail": (prop.get("error") or {}).get("message", "?")})
            return {"verdict": "degraded"}
        ps.last_verdict = "rejected"
        _emit("mutation.rejected", {
            "mutation_id": None, "candidate_id": None, "gate": "schema",
            "violations": prop.get("violations")
            or [(prop.get("error") or {}).get("message", "?")]})
        return {"verdict": "rejected"}
    proposal = prop["proposal"]
    _emit("mutation.proposed", {
        "mutation_id": proposal["mutation_id"],
        "endpoint_id": prop["endpoint_id"], "model": prop["model"],
        "degraded": prop.get("degraded", False),
        "analysis": proposal.get("analysis"),
        "op_count": len(proposal.get("mutations") or []),
        "usage": prop.get("usage") or {}})
    if not proposal.get("mutations"):
        ps.last_verdict = "noop"
        _emit("mutation.noop", {"reason": reason,
                                "rationale": proposal.get("rationale", "")})
        return {"verdict": "noop"}
    g = gate(proposal, pack_loaded, pack, ps.cfg, fair)
    if not g.get("ok"):
        ps.last_verdict = "rejected"
        _emit("mutation.rejected", {
            "mutation_id": proposal["mutation_id"], "candidate_id": None,
            "gate": g["gate"], "violations": g["violations"]})
        return {"verdict": "rejected", "gate": g["gate"]}
    out = materialize(g["doc"], pack_id, ps, state_dir,
                      emit, seq, clock,
                      mutation_id=proposal["mutation_id"])
    ps.last_verdict = "candidate"
    return {"verdict": "candidate", "path": str(out)}


# -- boundary: promote / revert (FR-1408/1409) --------------------------------

def _events_after(state_dir: Path, offset: int) -> list[dict]:
    p = Path(state_dir) / "events.jsonl"
    rows = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines()[offset:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _event_count(state_dir: Path) -> int:
    p = Path(state_dir) / "events.jsonl"
    if not p.is_file():
        return 0
    return sum(1 for _ in p.open(encoding="utf-8"))


def boundary(pack_id: str, state_dir: Path, *, emit=None, clock=None,
             fair: bool = True, weights: dict | None = None) -> dict:
    """Run-start boundary: revert a regressed promotion, then install a
    pending candidate. Called before load_pack — never mid-run."""
    state_dir = Path(state_dir)
    seq = [0]

    def _emit(t, payload):
        if emit is not None:
            seq[0] += 1
            emit(mutation_event(t, payload, seq[0], clock))

    if weights is None:
        # incumbent pack's declared scoring weights, else the improve
        # defaults — read the file BEFORE any promotion replaces it
        try:
            _doc = yaml.safe_load(
                templates.pack_path(pack_id).read_text(encoding="utf-8")) \
                or {}
            weights = ((_doc.get("improve") or {}).get("metrics")
                       or {}).get("weights")
        except Exception:
            weights = None
    weights = weights or {"refusal_rate": 0.4, "verify_failure_rate": 0.3,
                          "task_completion_rate": 0.3}
    rows = lineage_rows(state_dir)
    out = {"promoted": None, "reverted": None, "rejected": []}
    promoted = next((r for r in reversed(rows)
                     if r.get("target_pack") == pack_id
                     and r.get("state") == "promoted"), None)
    if promoted and promoted.get("events_offset") is not None:
        ep = _events_after(state_dir, int(promoted["events_offset"]))
        ep_score = improve.score(episode_metrics(ep), weights)
        base = promoted.get("baseline_score")
        if base is not None and ep and ep_score > base:
            parent = promoted.get("parent_path")
            target = templates.pack_path(pack_id)
            if parent and Path(parent).is_file():
                write_atomic(target, Path(parent).read_bytes())
                _emit("mutation.reverted", {
                    "pack_hash": promoted.get("parent_hash"),
                    "restored_parent": parent,
                    "episode_score": ep_score,
                    "baseline_score": base,
                    "candidate_id": promoted.get("candidate_id")})
                _mark_lineage(state_dir, promoted["candidate_id"],
                              "reverted")
                out["reverted"] = promoted["candidate_id"]
                rows = lineage_rows(state_dir)
    pending = next((r for r in reversed(rows)
                    if r.get("target_pack") == pack_id
                    and r.get("state") == "pending"), None)
    if not pending:
        return out
    ep_score = improve.score(
        episode_metrics(_events_after(state_dir, 0)), weights)
    res = promote_candidate(
        Path(pending.get("candidate_path") or ""), pending, pack_id,
        state_dir, fair=fair, baseline_score=ep_score,
        events_offset=_event_count(state_dir), emit=emit, clock=clock,
        episode_boundary=True)
    if not res.get("ok"):
        out["rejected"].append(pending["candidate_id"])
        return out
    out["promoted"] = pending["candidate_id"]
    return out


def promote_candidate(cand_path: Path, pending: dict, pack_id: str,
                      state_dir: Path, *, fair: bool = True,
                      mid_run: bool = False, baseline_score=None,
                      events_offset=None, episode_boundary: bool = False,
                      emit=None, clock=None) -> dict:
    """Install a pending candidate over the target pack file — the shared
    install half of :func:`boundary` (ADR-020). Re-validate -> parent
    backup -> atomic write -> `promoted` lineage row -> `mutation.promoted`.

    ``mid_run=True`` is the fast-evolve retry path: same gate and lineage,
    marked ``mid_run: true``; the episode-score auto-revert stays a
    boundary() concern. The caller MUST ``load_pack`` after a mid-run
    install so the dispatcher's recorded hash rebinds (pack_drift stays
    sound)."""
    state_dir = Path(state_dir)
    seq = [0]

    def _emit(t, payload):
        if emit is not None:
            seq[0] += 1
            emit(mutation_event(t, payload, seq[0], clock))

    violations = []
    doc = None
    if not cand_path.is_file():
        violations.append(f"candidate file missing: {cand_path}")
    else:
        try:
            doc = yaml.safe_load(cand_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            violations.append(f"candidate YAML unreadable: {exc}")
    if doc is not None:
        violations += validate_candidate(doc, fair=fair)
    if violations:
        _emit("mutation.rejected", {
            "mutation_id": None,
            "candidate_id": pending.get("candidate_id"),
            "gate": "boundary", "violations": violations})
        _mark_lineage(state_dir, pending["candidate_id"], "rejected")
        return {"ok": False, "violations": violations}
    target = templates.pack_path(pack_id)
    parent_hash = templates.current_hash(pack_id) or ""
    parent_backup = (templates.packs_dir() / "candidates" /
                     f"parent-{pack_id.replace('/', '-')}-"
                     f"{parent_hash[:8]}.yaml")
    if target.is_file():
        parent_backup.parent.mkdir(parents=True, exist_ok=True)
        parent_backup.write_bytes(target.read_bytes())
    write_atomic(target, cand_path.read_bytes())
    lineage = dict(pending)
    lineage.update({"state": "promoted", "parent_hash": parent_hash,
                    "parent_path": str(parent_backup),
                    "baseline_score": baseline_score,
                    "events_offset": events_offset,
                    "mid_run": mid_run})
    _mark_lineage(state_dir, pending["candidate_id"], "promoted")
    _append_lineage(state_dir, lineage)
    _emit("mutation.promoted", {
        "candidate_id": pending["candidate_id"],
        "pack_hash": templates.current_hash(pack_id) or "",
        "parent_hash": parent_hash, "episode_boundary": episode_boundary,
        "mid_run": mid_run, "baseline_score": baseline_score})
    return {"ok": True, "candidate_id": pending["candidate_id"],
            "parent_hash": parent_hash}
