"""Single-writer dispatcher (feature 004; FR-301..304, FR-307).

Every framework game mutation flows through :meth:`Dispatcher.dispatch` after
template validation. Failure modes are named and refuse before any bridge
call (SC-302): ``dispatch.unknown_action``, ``dispatch.params_invalid``,
``dispatch.decision_unmapped``, ``dispatch.locked``, ``dispatch.pack_drift``.

Evidence (FR-307): each outcome emits canonical ``action.*`` events with
``{pack_revision, decision_id?, template_id, params, outcome}`` — the event
stream equals the write stream (SC-301). Pack immutability: dispatch re-hashes
the pack file on every call and refuses on drift (constitution: scored runs
reject dirty state).
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - tests install it
    jsonschema = None  # type: ignore[assignment]

from . import templates
from .bridgeclient import BridgeClient
from .templates import PackError

DEFAULT_STATE_DIR = Path(os.environ.get(
    "RIMBRAIN_STATE_DIR",
    str(Path(__file__).resolve().parents[4] / "state"),
))

__all__ = ["Dispatcher", "substitute_params", "validate_template_params",
           "DEFAULT_STATE_DIR"]


def validate_template_params(template: dict, params: dict) -> list[str]:
    """Params-schema + require check; shared by dispatch and the review gate."""
    problems: list[str] = []
    schema = template.get("params_schema")
    if schema and jsonschema is not None:
        try:
            for e in jsonschema.Draft202012Validator(schema).iter_errors(params):
                problems.append(f"{list(e.absolute_path) or '$'}: {e.message}")
        except Exception as exc:  # malformed schema in pack -> fail closed
            problems.append(f"params_schema error: {exc}")
    for key in template.get("require", []):
        if key not in params:
            problems.append(f"missing required param '{key}'")
    return problems[:20]


def _err(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message, "retryable": False}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


def _dotted(state: dict, path: str):
    cur: object = state
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            return None
    return cur


def substitute_params(params: dict, state: dict, answer: dict | None) -> dict:
    """Resolve ``{state.a.b}`` and ``{answer.key}`` placeholders in param values.

    Unresolvable placeholders stay literal (the template's params_schema will
    reject wrong types; a stray placeholder is a data error, not a crash).
    """

    def walk(value):
        if isinstance(value, str):
            if value.startswith("{") and value.endswith("}"):
                key = value[1:-1]
                if key.startswith("state."):
                    got = _dotted(state, key[len("state."):])
                    if got is not None:
                        return got
                elif key.startswith("answer."):
                    got = _dotted(answer or {}, key[len("answer."):])
                    if got is not None:
                        return got
            return value
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return walk(params)


class Dispatcher:
    """One instance per process; the single writer for framework game writes."""

    def __init__(self, bridge: BridgeClient | None = None, *,
                 state_dir: str | Path | None = None,
                 sink=None, game_tick: int | None = None,
                 clock=None, fair: bool = False) -> None:
        self.bridge = bridge or BridgeClient()
        # fair mode: no debug/cheat surface — dev.* plus save-load
        # (checkpoint restore is a test harness, not fair play)
        self._fair = fair
        self._state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self._sink = sink
        self._lock = threading.RLock()
        self._events = 0
        self._pack: dict | None = None          # {pack, hash, path}
        self._pack_file: str | None = None      # file id the pack was loaded from
        self._last_tick = game_tick
        self._clock = clock or (lambda: datetime.now(timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"))

    # -- pack ---------------------------------------------------------------

    def load_pack(self, pack_id: str) -> dict:
        """Load (or reload) a policy pack; fail-closed on any violation."""
        loaded = templates.load_pack(pack_id)
        self._pack = loaded
        self._pack_file = pack_id   # file id (may differ from declared pack_id)
        return loaded

    @property
    def pack(self) -> dict | None:
        return self._pack

    # -- evidence -----------------------------------------------------------

    def _emit(self, event_type: str, payload: dict) -> dict:
        self._events += 1
        envelope = {
            "schema_version": 0,
            "event_id": f"evt.action-{self._events:06d}",
            "sequence": self._events,
            "event_type": event_type,
            "game_tick": self._last_tick,
            "wall_time_utc": self._clock(),
            "source": "rimbrainagent.runtime.dispatch",
            "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": payload,
            "privacy": {"classification": "internal", "redactions": []},
        }
        if self._sink is not None:
            self._sink(envelope)
        return envelope

    def _payload(self, template_id: str, params: dict, outcome: str,
                 decision_id: str | None = None) -> dict:
        payload = {
            "pack_revision": self._pack["hash"],
            "template_id": template_id,
            "params": params,
            "outcome": outcome,
        }
        if decision_id is not None:
            payload["decision_id"] = decision_id
        return payload

    # -- single write path --------------------------------------------------

    def dispatch(self, action_id: str, params: dict,
                 decision_id: str | None = None) -> dict:
        """Validate + execute one template action; returns an ok/error envelope.

        Refusals happen before any bridge call and emit ``action.refused``.
        """
        if self._pack is None:
            return _err("dispatch.no_pack", "no policy pack loaded")
        if templates.pack_drift(self._pack_file, self._pack["hash"]):
            return self._refuse("", params, "dispatch.pack_drift",
                                "policy pack changed on disk since load",
                                decision_id)
        template = next((t for t in self._pack["pack"]["templates"]
                         if t["id"] == action_id), None)
        if template is None:
            return self._refuse(action_id, params, "dispatch.unknown_action",
                                f"action '{action_id}' is not in the pack",
                                decision_id)
        if self._fair and (template["method"].startswith("dev.")
                           or template["method"] in
                           ("game.save", "game.load")):
            return self._refuse(action_id, params, "dispatch.fair_mode",
                                f"'{template['method']}' denied: fair run "
                                "(no debug/save-load)", decision_id)
        problems = self._validate_params(template, params)
        if problems:
            return self._refuse(action_id, params, "dispatch.params_invalid",
                                f"params for '{action_id}' invalid: "
                                + "; ".join(problems), decision_id,
                                details={"issues": problems})

        with self._lock:  # single writer: no concurrent dispatch
            self._emit("action.issued", self._payload(
                action_id, params, "issued", decision_id))
            r = self.bridge.rpc(template["method"], params)
            if not r.get("ok"):
                error = r["error"]
                if not isinstance(error, dict):  # bridge may return bare strings
                    error = {"code": "bridge.error", "message": str(error)}
                self._emit("action.failed", {
                    **self._payload(action_id, params, "failed", decision_id),
                    "error": {"code": error["code"],
                              "message": error["message"],
                              "retryable": bool(error.get("retryable"))},
                })
                return _err(error["code"], error["message"])
            result = r.get("result")
            if isinstance(result, dict):
                self._last_tick = result.get("tick", self._last_tick)
            self._emit("action.completed", {
                **self._payload(action_id, params, "completed", decision_id),
                "result": result if isinstance(result, dict) else {},
            })
            return {"ok": True, "result": result}

    def _validate_params(self, template: dict, params: dict) -> list[str]:
        return validate_template_params(template, params)

    def _refuse(self, action_id: str, params: dict, code: str, message: str,
                decision_id: str | None,
                details: dict | None = None) -> dict:
        self._emit("action.refused", {
            **self._payload(action_id, params, "refused", decision_id),
            "error": {"code": code, "message": message, "retryable": False},
        })
        return _err(code, message, details)

    # -- typed decisions (FR-303) -------------------------------------------

    def dispatch_from_decision(self, answer: dict, state: dict,
                               question: str = "q.action",
                               decision_id: str | None = None) -> dict:
        """Map a systemone answer to a template action and dispatch it.

        First decision_map entry wins: exact ``choice`` match, or
        ``score``/``noul`` threshold. Unmapped answers are refused with
        ``dispatch.decision_unmapped`` (no write).
        """
        if self._pack is None:
            return _err("dispatch.no_pack", "no policy pack loaded")
        answer = answer or {}
        for entry in self._pack["pack"].get("decision_map", []):
            if entry.get("question") != question:
                continue
            if (entry.get("choice") is not None
                    and answer.get("choice") == entry["choice"]):
                return self._go(entry["action"], state, answer, decision_id)
            for threshold_key in ("score", "noul"):
                if entry.get(threshold_key) is not None and isinstance(
                        answer.get(threshold_key), (int, float)):
                    if answer[threshold_key] >= entry[threshold_key]:
                        return self._go(entry["action"], state, answer,
                                        decision_id)
        return self._refuse("", {}, "dispatch.decision_unmapped",
                            f"answer for '{question}' ({answer.get('choice')!r}) "
                            "maps to no template action", decision_id)

    def _go(self, action: dict, state: dict, answer: dict,
            decision_id: str | None) -> dict:
        params = substitute_params(action.get("params") or {}, state, answer)
        return self.dispatch(action["template_id"], params,
                             decision_id=decision_id)

    # -- emergency reflex (FR-308) ------------------------------------------

    def reflex(self, state: dict) -> list[dict]:
        """Evaluate deterministic emergency rules (no model); dispatch matches.

        Returns the list of dispatch envelopes for rules that fired, ordered by
        ``priority``. Reflexes never wait for a model (SC-305).
        """
        if self._pack is None:
            return []
        fired: list[dict] = []
        for rule in sorted(self._pack["pack"].get("emergency", []),
                           key=lambda r: r.get("priority", 999)):
            if self._condition(rule.get("condition"), state):
                params = substitute_params(
                    rule["action"].get("params") or {}, state, None)
                self._emit("action.emergency", {
                    **self._payload(rule["action"]["template_id"], params,
                                    "emergency"),
                    "rule_id": rule["id"],
                })
                fired.append(self.dispatch(rule["action"]["template_id"],
                                           params))
        return fired

    @staticmethod
    def _condition(condition: dict | None, state: dict) -> bool:
        if not condition:
            return False
        results = []
        for p in condition.get("predicates", []):
            observed = _dotted(state, p["field"])
            results.append(_op_holds(p["op"], observed, p["value"]))
        combo = condition.get("combinator", "all")
        return all(results) if combo == "all" else any(results)


def _op_holds(op: str, observed, expected) -> bool:
    if observed is None:
        return False
    try:
        if op == "eq":
            return observed == expected
        if op == "ne":
            return observed != expected
        if op == "gt":
            return observed > expected
        if op == "gte":
            return observed >= expected
        if op == "lt":
            return observed < expected
        if op == "lte":
            return observed <= expected
        if op == "contains":
            return expected in observed
    except TypeError:
        return False
    return False
