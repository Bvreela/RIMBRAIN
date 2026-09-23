"""Ordered, enumerable mutation space for retry loops (T050, FR-204).

A mutation space is a declared ordered list of edits to a *candidate plan dict*
(never an in-place edit of an immutable pack -- UR-RL-006). Each retry pops
exactly one entry; retrying identical state is forbidden, and a space smaller
than the retry cap ends the loop ``exhausted`` (spec edge case: mutation budget
exhaustion).

Mutation shape::

    {"id": "bump-priority",
     "apply": {"path": "plan.priorities.0.weight", "op": "bump", "value": 1}}

Ops (``apply.op``):

- ``set``  -- assign ``value`` at ``path``, creating intermediate dicts;
- ``bump`` -- add numeric ``value`` to the numeric leaf at ``path``;
- ``swap`` -- ``path`` must resolve to a list; ``value`` is an ``[i, j]`` index
  pair whose elements are exchanged (e.g. reordering a priority list).

``MutationSpace.next()`` pops the next declared entry (or ``None`` on
exhaustion); ``MutationSpace.apply_mutation(candidate, mutation)`` returns
``(new_candidate, None)`` on success or ``(candidate_unchanged, error)`` on an
invalid apply -- the caller keeps the prior valid revision, so the loop never
runs an invalid plan (FR-204, US3-2).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = ["OPS", "MutationSpace", "apply_mutation"]

OPS = ("set", "bump", "swap")


def _error(message: str, details: dict | None = None) -> dict:
    err: dict[str, Any] = {"code": "mutation.invalid", "message": message}
    if details:
        err["details"] = details
    return err


def _resolve_parent(root: dict, path: str, create: bool) -> tuple[Any, str] | dict:
    """Walk ``path`` to ``(parent_node, leaf_key)``; returns an error dict on failure.

    Numeric segments index lists; other segments index dicts. With
    ``create=True`` missing intermediate dict keys are created (``set``).
    """
    segments = path.split(".")
    if not path or any(seg == "" for seg in segments):
        return _error(f"mutation path {path!r} is empty or has empty segments")
    node: Any = root
    for segment in segments[:-1]:
        if isinstance(node, dict):
            if segment not in node:
                if not create:
                    return _error(f"mutation path {path!r} missing segment {segment!r}")
                node[segment] = {}
            node = node[segment]
        elif isinstance(node, list):
            if not segment.isdigit() or int(segment) >= len(node):
                return _error(
                    f"mutation path {path!r}: {segment!r} is not a valid list index"
                )
            node = node[int(segment)]
        else:
            return _error(
                f"mutation path {path!r}: segment {segment!r} descends into a scalar"
            )
    return node, segments[-1]


def _leaf(parent: Any, key: str) -> tuple[bool, Any]:
    """Fetch ``parent[key]`` (list index or dict key)."""
    if isinstance(parent, dict):
        return (key in parent), parent.get(key)
    if isinstance(parent, list) and key.isdigit() and int(key) < len(parent):
        return True, parent[int(key)]
    return False, None


def _assign(parent: Any, key: str, value: Any) -> dict | None:
    """Assign ``parent[key] = value``; returns an error dict on failure."""
    if isinstance(parent, dict):
        parent[key] = value
        return None
    if isinstance(parent, list) and key.isdigit() and int(key) < len(parent):
        parent[int(key)] = value
        return None
    return _error(f"mutation leaf {key!r} is not assignable")


def apply_mutation(candidate: dict, mutation: dict) -> tuple[dict, dict | None]:
    """Apply one mutation to a deep copy of ``candidate``.

    Returns ``(new_candidate, None)`` on success; on any invalid apply returns
    ``(candidate, error)`` with ``candidate`` untouched -- callers keep the
    prior valid revision (FR-204).
    """
    if not isinstance(mutation, dict):
        return candidate, _error("mutation is not an object")
    mut_id = mutation.get("id")
    apply = mutation.get("apply")
    if not isinstance(mut_id, str) or not mut_id:
        return candidate, _error("mutation is missing a non-empty 'id'")
    if not isinstance(apply, dict):
        return candidate, _error(
            f"mutation {mut_id!r} is missing an 'apply' object", {"id": mut_id}
        )
    missing_keys = [k for k in ("path", "op", "value") if k not in apply]
    if missing_keys:
        return candidate, _error(
            f"mutation {mut_id!r} apply is missing {missing_keys}", {"id": mut_id}
        )
    path, op, value = apply["path"], apply["op"], apply["value"]
    if not isinstance(path, str) or not path:
        return candidate, _error(f"mutation {mut_id!r} path must be a non-empty string")
    if op not in OPS:
        return candidate, _error(
            f"mutation {mut_id!r} has unknown op {op!r}", {"id": mut_id, "op": op}
        )

    new_candidate = deepcopy(candidate)
    resolved = _resolve_parent(new_candidate, path, create=(op == "set"))
    if isinstance(resolved, dict):  # error envelope
        resolved.setdefault("details", {})["id"] = mut_id
        return candidate, resolved
    parent, leaf = resolved

    if op == "set":
        err = _assign(parent, leaf, deepcopy(value))
        if err:
            return candidate, err
        return new_candidate, None

    if op == "bump":
        exists, current = _leaf(parent, leaf)
        if not exists:
            return candidate, _error(
                f"mutation {mut_id!r} bump path {path!r} does not resolve",
                {"id": mut_id},
            )
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            return candidate, _error(
                f"mutation {mut_id!r} bump target at {path!r} is not numeric",
                {"id": mut_id},
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return candidate, _error(
                f"mutation {mut_id!r} bump value must be numeric", {"id": mut_id}
            )
        err = _assign(parent, leaf, current + value)
        if err:
            return candidate, err
        return new_candidate, None

    # op == "swap": path resolves to a list; value is an [i, j] index pair.
    exists, target = _leaf(parent, leaf)
    if not exists or not isinstance(target, list):
        return candidate, _error(
            f"mutation {mut_id!r} swap target at {path!r} is not a list",
            {"id": mut_id},
        )
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(i, bool) or not isinstance(i, int) for i in value)
    ):
        return candidate, _error(
            f"mutation {mut_id!r} swap value must be an [i, j] index pair",
            {"id": mut_id},
        )
    i, j = value
    if not (0 <= i < len(target) and 0 <= j < len(target)):
        return candidate, _error(
            f"mutation {mut_id!r} swap indices {value} out of range "
            f"(len={len(target)})",
            {"id": mut_id},
        )
    target[i], target[j] = target[j], target[i]
    return new_candidate, None


class MutationSpace:
    """Ordered declared mutation space: one pop per retry (FR-204)."""

    def __init__(self, mutations: list[dict] | None = None) -> None:
        self._mutations = list(mutations or [])
        self._index = 0

    def __len__(self) -> int:
        return len(self._mutations)

    @property
    def index(self) -> int:
        """0-based position of the next mutation to pop."""
        return self._index

    @property
    def remaining(self) -> int:
        return len(self._mutations) - self._index

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._mutations)

    def next(self) -> tuple[int, dict] | None:
        """Pop the next mutation as ``(index, mutation)``; ``None`` when exhausted."""
        if self.exhausted:
            return None
        entry = self._index, self._mutations[self._index]
        self._index += 1
        return entry

    @staticmethod
    def apply(candidate: dict, mutation: dict) -> tuple[dict, dict | None]:
        return apply_mutation(candidate, mutation)
