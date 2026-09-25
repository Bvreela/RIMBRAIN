"""Review gate (feature 005; FR-403, SC-401).

Code decides, the model advises: ``deterministic_check()`` produces the
violations list — non-empty means rejected, full stop. The ``rimbrain.review``
model call runs only on a clean gate and returns advisory feedback text; its
failure degrades to ``model_unavailable`` with the deterministic verdict
standing. A model can never approve a violating plan, and its text cannot
flip a clean verdict either (it is recorded, not executed).
"""

from __future__ import annotations

import json

from . import planning, templates
from .bindings import resolve_role
from .client import openai_compat_chat
from .dispatch import validate_template_params

__all__ = ["deterministic_check", "review"]

_MUTATION_OPS = {"add_template", "edit_decision_map", "add_emergency"}


def _template_ids(pack_loaded: dict) -> set[str]:
    return {t["id"] for t in pack_loaded["pack"].get("templates", [])}


def _known_entities(state: dict | None) -> set[str]:
    """Observed entity ids/names; empty set when the state has no roster."""
    if not state:
        return set()
    known = set()
    for m in planning.colonist_roster(state):
        for k in ("id", "name"):
            if m.get(k):
                known.add(str(m[k]))
    return known


def deterministic_check(proposal: dict, pack_loaded: dict,
                        state: dict | None = None) -> list[str]:
    """Hard violations for a proposal; any entry => rejected (SC-401).

    When ``state`` is given and carries a colonist roster, entity params are
    verified against observed entities — the planner may not invent pawns or
    targets (project rule: plans act on observed colony data only).
    """
    pack = pack_loaded["pack"]
    tids = _template_ids(pack_loaded)
    by_id = {t["id"]: t for t in pack.get("templates", [])}
    known = _known_entities(state)
    violations: list[str] = []

    if proposal.get("base_revision") != pack_loaded["hash"]:
        violations.append(
            f"stale base_revision {proposal.get('base_revision')!r} "
            f"!= current pack hash {pack_loaded['hash']!r}")

    for i, action in enumerate(proposal.get("actions", [])):
        tid = action.get("template_id")
        if tid not in by_id:
            violations.append(f"actions[{i}]: unknown template '{tid}'")
            continue
        params = action.get("params") or {}
        for p in validate_template_params(by_id[tid], params):
            violations.append(f"actions[{i}] '{tid}': {p}")
        if known:
            for key in ("pawn", "target"):
                val = params.get(key)
                if isinstance(val, str) and val not in known:
                    violations.append(
                        f"actions[{i}] '{tid}': {key} '{val}' is not an "
                        "observed colony entity")

    for i, mut in enumerate(proposal.get("policy_mutations", [])):
        op, target, patch = (mut.get("op"), mut.get("target"),
                             mut.get("patch") or {})
        if op not in _MUTATION_OPS:
            violations.append(f"policy_mutations[{i}]: illegal op '{op}'")
            continue
        if op == "add_template":
            if patch.get("id") != target:
                violations.append(
                    f"policy_mutations[{i}]: patch.id {patch.get('id')!r} "
                    f"!= target {target!r}")
            if target in tids:
                violations.append(
                    f"policy_mutations[{i}]: template '{target}' exists")
            if not isinstance(patch.get("params_schema"), dict):
                violations.append(
                    f"policy_mutations[{i}]: missing params_schema")
            method = patch.get("method")
            if method and method not in templates.inventory_methods():
                violations.append(
                    f"policy_mutations[{i}]: method '{method}' not in "
                    "bridge inventory")
        else:  # edit_decision_map / add_emergency -> patch embeds an action
            ref = (patch.get("action") or {}).get("template_id")
            if ref is None:
                violations.append(
                    f"policy_mutations[{i}]: patch.action.template_id missing")
            elif ref not in tids:
                violations.append(
                    f"policy_mutations[{i}]: patch references unknown "
                    f"template '{ref}'")
            if op == "add_emergency" and not isinstance(
                    patch.get("condition"), dict):
                violations.append(
                    f"policy_mutations[{i}]: missing condition")
    return violations[:25]


def _critique_prompt(proposal: dict, pack_loaded: dict) -> list[dict]:
    return [
        {"role": "system", "content":
         "You are rimbrain.review. Critique the plan briefly; your text is "
         "advisory — the deterministic gate already decided legality."},
        {"role": "user", "content":
         "Pack " + pack_loaded["pack"]["pack_id"] + " rev "
         + pack_loaded["hash"][:12] + "\nPlan:\n"
         + json.dumps(proposal, sort_keys=True)[:6000]},
    ]


def review(proposal: dict, pack_loaded: dict, *, state: dict | None = None,
           resolver=resolve_role, chat=openai_compat_chat,
           usage_tracker=None) -> dict:
    """Gate + advisory critique -> ``{verdict, violations, feedback, ...}``."""
    violations = deterministic_check(proposal, pack_loaded, state=state)
    zero = {"prompt_tokens": 0, "completion_tokens": 0}
    if violations:
        return {"verdict": "rejected", "violations": violations,
                "feedback": "", "model_unavailable": False, "usage": zero}

    res = resolver("rimbrain.review", probe_live=False)
    if (not res.get("ok")
            or res["resolved"].get("kind") == "fallback"):
        return {"verdict": "approved", "violations": [],
                "feedback": "", "model_unavailable": True, "usage": zero}
    resolved = res["resolved"]
    r = chat(resolved["endpoint_id"], resolved["model"],
             _critique_prompt(proposal, pack_loaded),
             usage_tracker=usage_tracker)
    if not r.get("ok"):
        return {"verdict": "approved", "violations": [],
                "feedback": "", "model_unavailable": True, "usage": zero}
    body = r.get("body") or {}
    usage = body.get("usage") or {}
    try:
        feedback = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        feedback = ""
    return {"verdict": "approved", "violations": [],
            "feedback": feedback[:4000], "model_unavailable": False,
            "usage": {"prompt_tokens": int(usage.get("prompt_tokens") or 0),
                      "completion_tokens":
                          int(usage.get("completion_tokens") or 0)}}
