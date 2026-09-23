"""Planning tier (feature 005; FR-401/402/408).

``propose()`` resolves ``rimbrain.plan`` through feature-002 bindings, calls
the chat endpoint, extracts a JSON PlanProposal (fenced or bare object), and
schema-validates it against ``contracts/schemas/runtime/plan.schema.json``.
Every failure is a named error — never a guess (``plan.unresolved``,
``plan.endpoint_error``, ``plan.malformed``).

When resolution lands on the terminal ``rules-only`` sentinel the loop emits
the pack's ``fallback_plan`` — deterministic, pack-authored data (FR-408).
The planner holds no bridge client; plan actions dispatch through the
feature-004 Dispatcher only (FR-406).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .bindings import resolve_role
from .client import openai_compat_chat
from .registry import err

REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_SCHEMA = (REPO_ROOT / "components" / "contracts" / "schemas" /
               "runtime" / "plan.schema.json")

__all__ = ["propose", "extract_json", "build_prompt", "validate_plan"]

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict | None:
    """Pull a JSON object out of model output: fenced block, else first
    balanced top-level ``{...}``. Returns None when nothing parses."""
    if not isinstance(text, str):
        return None
    m = _FENCED.search(text)
    candidates = [m.group(1)] if m else []
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
    for raw in candidates:
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if isinstance(doc, dict):
            return doc
    return None


def colonist_roster(state: dict) -> list[dict]:
    """Observed colonist entities (id/name/downed) from any status shape.

    Live and sim `game.status` differ; accept ``colonists.members[]`` or a
    top-level ``colonists[]`` list of strings/dicts. An empty list means the
    state carried no roster — the gate then cannot verify entity references.
    """
    colonists = state.get("colonists")
    members = ((colonists.get("members") if isinstance(colonists, dict) else None)
               or state.get("colonist_list")
               or state.get("pawns")
               or [])
    roster = []
    for m in members:
        if isinstance(m, dict):
            roster.append({"id": m.get("id"), "name": m.get("name"),
                           "downed": bool(m.get("downed"))})
        elif isinstance(m, str):
            roster.append({"id": m, "name": m, "downed": False})
    return roster


def build_prompt(state: dict, pack_loaded: dict) -> list[dict]:
    """Deterministic prompt: colony digest + template menu + output contract.

    The digest carries the observed colonist roster — the planner may only
    reference entities that exist in state (project rule: never invent).
    """
    pack = pack_loaded["pack"]
    menu = [{"id": t["id"], "method": t["method"],
             "params_schema": t.get("params_schema"),
             "require": t.get("require", []),
             "description": t.get("description", "")}
            for t in pack.get("templates", [])]
    digest = {
        "tick": state.get("tick"), "day": state.get("day"),
        "colonists": {
            "roster": colonist_roster(state),
            "count": state.get("colonists") if isinstance(
                state.get("colonists"), int)
                else len(colonist_roster(state)),
            "downed": ((state.get("colonists") or {}).get("downed")
                       if isinstance(state.get("colonists"), dict)
                       else (state.get("summary") or {}).get("downed")),
            "downed_id": ((state.get("colonists") or {}).get("downed_id")
                          if isinstance(state.get("colonists"), dict)
                          else None)},
        "map": state.get("map"),
        "haul_cell": state.get("haul_cell"),
        "priorities": state.get("priorities"),
        "summary": state.get("summary"),
    }
    contract = {
        "schema_version": 0, "plan_id": "plan.<slug>",
        "base_revision": pack_loaded["hash"], "horizon_ticks": 60000,
        "actions": [{"template_id": "<id>", "params": {}}],
        "policy_mutations": [{"op": "add_template|edit_decision_map|add_emergency",
                              "target": "<id>", "patch": {}}],
        "rationale": "<why>",
    }
    return [
        {"role": "system", "content":
         "You are rimbrain.plan, the strategic planner for a RimWorld colony. "
         "Output ONLY a JSON object matching the PlanProposal contract — no "
         "prose. Use only the listed template ids in actions[]. Reference ONLY "
         "colonists and entities present in the provided colony state (roster "
         "ids/names) — never invent entity ids or names."},
        {"role": "user", "content":
         "Colony state:\n" + json.dumps(digest, sort_keys=True)
         + "\n\nAvailable action templates:\n"
         + json.dumps(menu, sort_keys=True)
         + "\n\nEmit exactly this shape:\n"
         + json.dumps(contract, sort_keys=True)},
    ]


def validate_plan(doc: dict) -> list[str]:
    """Schema problems for a candidate proposal; [] means valid."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - tests install it
        return []
    schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
    return [f"{list(e.absolute_path) or '$'}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)][:25]


def _content(body: dict) -> str | None:
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def _finalize(doc: dict, pack_loaded: dict) -> dict:
    """Fill deterministic fields the model may omit, then validate."""
    doc = dict(doc)
    doc.setdefault("schema_version", 0)
    if not doc.get("plan_id"):
        tag = hashlib.sha256(json.dumps(
            doc, sort_keys=True, default=str).encode()).hexdigest()[:8]
        doc["plan_id"] = f"plan.auto-{tag}"
    doc.setdefault("base_revision", pack_loaded["hash"])
    doc.setdefault("actions", [])
    doc.setdefault("policy_mutations", [])
    doc.setdefault("rationale", "")
    doc.setdefault("horizon_ticks", 60000)
    return doc


def _fallback(state: dict, pack_loaded: dict, resolved: dict) -> dict:
    """Rules-only terminal path (FR-408): pack-authored deterministic plan."""
    plan = (pack_loaded["pack"].get("fallback_plan") or {})
    if not plan:
        return err("plan.no_fallback",
                   "planner degraded to rules-only but pack declares no "
                   "fallback_plan")
    doc = _finalize(dict(plan), pack_loaded)
    problems = validate_plan(doc)
    if problems:
        return err("plan.malformed",
                   "pack fallback_plan fails plan.schema.json",
                   {"issues": problems})
    return {"ok": True, "proposal": doc, "endpoint_id": resolved["name"],
            "model": resolved["name"], "degraded": True,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}}


def propose(state: dict, pack_loaded: dict, *,
            resolver=resolve_role, chat=openai_compat_chat,
            usage_tracker=None) -> dict:
    """Resolve -> chat -> extract -> validate. Named-error envelope on failure.

    Returns ``{ok, proposal, endpoint_id, model, degraded, usage}`` or the
    canonical ``{ok:false,error:{code,...}}``.
    """
    res = resolver("rimbrain.plan", probe_live=False)
    if not res.get("ok"):
        return err("plan.unresolved",
                   f"rimbrain.plan unresolvable: "
                   f"{res['error']['message']}",
                   {"resolution": res["error"]})
    resolved = res["resolved"]
    if resolved.get("kind") == "fallback":
        return _fallback(state, pack_loaded, resolved)

    r = chat(resolved["endpoint_id"], resolved["model"],
             build_prompt(state, pack_loaded), usage_tracker=usage_tracker)
    if not r.get("ok"):
        return err("plan.endpoint_error",
                   f"planning call failed: {r['error']['message']}",
                   {"endpoint": resolved["endpoint_id"],
                    "upstream": r["error"]},
                   )
    usage = (r.get("body") or {}).get("usage") or {}
    text = _content(r.get("body") or {})
    doc = extract_json(text or "")
    if doc is None:
        return err("plan.malformed",
                   "planner output contained no parseable JSON object",
                   {"endpoint": resolved["endpoint_id"]})
    doc = _finalize(doc, pack_loaded)
    problems = validate_plan(doc)
    if problems:
        return err("plan.malformed",
                   "planner output fails plan.schema.json",
                   {"issues": problems})
    return {"ok": True, "proposal": doc,
            "endpoint_id": resolved["endpoint_id"],
            "model": resolved["model"],
            "degraded": bool(res.get("degraded")),
            "usage": {"prompt_tokens": int(usage.get("prompt_tokens") or 0),
                      "completion_tokens":
                          int(usage.get("completion_tokens") or 0)}}
