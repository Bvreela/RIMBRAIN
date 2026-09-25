"""Success-gate predicate evaluator for checkpoint-retry loops (T049, FR-203).

Gates are *state predicates*, never event equality -- RimWorld RNG makes exact
replays non-deterministic, so predicates are robust comparisons over an
observed state dict (``game.status`` plus any bridge-reported fields).

Gate shape::

    {"combinator": "all"|"any",          # default "all"
     "predicates": [{"id": str, "field": "dotted.path", "op": op, "value": ...}]}

``field`` is a dotted path into the state dict; numeric segments index into
lists. Ops: ``eq | ne | gt | gte | lt | lte | contains`` (contains = list
membership, substring, or dict key). A missing field or a type-incompatible
comparison evaluates ``met=false`` with ``observed=null`` -- never an exception,
never a silent pass.

:func:`evaluate` returns a GateVerdict dict::

    {"passed": bool,
     "predicates": [{"id", "field", "expected", "observed", "met"}],
     "early_exit": bool}   # mirrors passed -- a pass ends retries (FR-203)
"""

from __future__ import annotations

from typing import Any

__all__ = ["OPS", "GateError", "evaluate", "resolve_field"]

OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")

_MISSING = object()  # sentinel: field path not resolvable in the state dict


class GateError(ValueError):
    """Raised when the gate definition itself is malformed."""


def resolve_field(state: Any, field: str) -> Any:
    """Walk a dotted path (numeric segments index lists); ``_MISSING`` if absent."""
    node = state
    for segment in field.split("."):
        if isinstance(node, dict):
            if segment not in node:
                return _MISSING
            node = node[segment]
        elif isinstance(node, (list, tuple)):
            if not segment.isdigit() or int(segment) >= len(node):
                return _MISSING
            node = node[int(segment)]
        else:
            return _MISSING
    return node


def _compare(op: str, observed: Any, expected: Any) -> bool:
    """One predicate comparison; incompatible operands are simply unmet."""
    if op == "eq":
        return bool(observed == expected)
    if op == "ne":
        return bool(observed != expected)
    if op == "contains":
        if isinstance(observed, dict):
            return expected in observed
        if isinstance(observed, (list, tuple, str)):
            try:
                return expected in observed
            except TypeError:
                return False
        return False
    # ordering ops: only meaningful on mutually comparable types
    try:
        if op == "gt":
            return bool(observed > expected)
        if op == "gte":
            return bool(observed >= expected)
        if op == "lt":
            return bool(observed < expected)
        if op == "lte":
            return bool(observed <= expected)
    except TypeError:
        return False
    raise GateError(f"unknown predicate op {op!r}")


def _check_definition(predicates: list[dict], combinator: str) -> None:
    if combinator not in ("all", "any"):
        raise GateError(f"gate combinator must be 'all' or 'any', got {combinator!r}")
    if not predicates:
        raise GateError("gate must declare at least one predicate")
    for index, pred in enumerate(predicates):
        if not isinstance(pred, dict):
            raise GateError(f"predicate {index} is not an object")
        for key in ("id", "field", "op", "value"):
            if key not in pred:
                raise GateError(f"predicate {index} is missing {key!r}")
        if pred["op"] not in OPS:
            raise GateError(
                f"predicate {index} ({pred.get('id')!r}) has unknown op {pred['op']!r}"
            )


def evaluate(gate: dict | list, state: dict) -> dict:
    """Evaluate ``gate`` against ``state``; returns the GateVerdict dict."""
    if isinstance(gate, list):
        gate = {"combinator": "all", "predicates": gate}
    if not isinstance(gate, dict):
        raise GateError("gate must be a mapping or a predicate list")
    combinator = gate.get("combinator", "all")
    predicates = gate.get("predicates") or []
    _check_definition(predicates, combinator)

    detail: list[dict[str, Any]] = []
    for pred in predicates:
        observed = resolve_field(state, pred["field"])
        missing = observed is _MISSING
        met = False if missing else _compare(pred["op"], observed, pred["value"])
        detail.append(
            {
                "id": pred["id"],
                "field": pred["field"],
                "expected": pred["value"],
                "observed": None if missing else observed,
                "met": met,
            }
        )

    mets = [p["met"] for p in detail]
    passed = all(mets) if combinator == "all" else any(mets)
    return {"passed": passed, "predicates": detail, "early_exit": passed}
