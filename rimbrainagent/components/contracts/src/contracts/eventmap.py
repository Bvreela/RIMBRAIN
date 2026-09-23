"""Upstream ``bus.py`` <-> canonical event envelope mapping (FR-007/FR-008).

Driven by ``registry/event-map.yaml`` — the versioned kind -> event_type map
implementing the table in
``specs/001-fork-bootstrap-contracts/contracts/canonical-event-envelope.md``.

Mapping rules (per the envelope contract):

- ``{seq, t, kind, data}`` -> ``{sequence, wall_time_utc, event_type, payload}``;
  ``data`` is carried verbatim as the payload for mapped kinds, so
  :func:`unwrap` reproduces the original ``{seq, t, kind, data}`` losslessly
  (SC-004).
- ``game_tick``, ``correlation`` and ``revisions`` have no upstream source and
  are emitted ``null`` — never fabricated (R5). ``episode_id`` is derived only
  when ``data.episode`` is a real upstream integer; otherwise ``null``.
- Unknown ``kind`` values map to ``legacy.unmapped`` with the raw kind
  preserved inside the payload as ``{"kind", "data"}``: stored, but rejected
  by the strict execution consumer (:func:`consume_strict`).

Versioning (FR-006, compatibility/VERSIONING.md): the envelope schema carries
no ``maximum`` on ``schema_version`` — the max is consumer policy, so archival
readers can schema-validate and preserve newer records losslessly. The strict
consumer path enforces it instead and rejects ``schema_version > max`` with
``{ok:false, error:{code:"schema.version.too_new", ...}}``, never a silent
misread.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

__all__ = [
    "SCHEMA_VERSION",
    "UNMAPPED_EVENT_TYPE",
    "EventMapError",
    "load_event_map",
    "map_kind",
    "registered_event_types",
    "wrap",
    "unwrap",
    "validate_envelope",
    "consume_strict",
    "check_stream_order",
    "error_envelope",
]

CONTRACTS_DIR = (Path(getattr(sys, "_MEIPASS", None)
                      or Path(__file__).resolve().parents[2])
                 / "components" / "contracts"
                 if getattr(sys, "frozen", False)
                 else Path(__file__).resolve().parents[2])
REGISTRY_PATH = CONTRACTS_DIR / "registry" / "event-map.yaml"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
ENVELOPE_SCHEMA_PATH = SCHEMAS_DIR / "events" / "envelope.schema.json"
PAYLOAD_TYPES_DIR = SCHEMAS_DIR / "events" / "types"

# Envelope contract revision emitted by wrap() and the default strict-consumer
# max. Draft baseline is 0 per compatibility/MIGRATIONS.md.
SCHEMA_VERSION = 0

UNMAPPED_EVENT_TYPE = "legacy.unmapped"
DEFAULT_SOURCE = "rimagent.bus"


class EventMapError(ValueError):
    """Raised when the registry map or a record cannot be mapped."""


def error_envelope(
    code: str,
    message: str,
    retryable: bool = False,
    details: dict | None = None,
) -> dict:
    """The one failure grammar shared from bridge boundary to contract validation."""
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


@lru_cache(maxsize=1)
def load_event_map(path: Path = REGISTRY_PATH) -> dict:
    """Load and sanity-check ``registry/event-map.yaml``."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("kinds"), dict):
        raise EventMapError(f"{path} is not a valid event map (missing 'kinds')")
    unknown = doc.get("unknown_kind") or {}
    if unknown.get("event_type") != UNMAPPED_EVENT_TYPE:
        raise EventMapError(
            f"{path}: unknown_kind.event_type must be {UNMAPPED_EVENT_TYPE!r}"
        )
    return doc


def map_kind(kind: str, event_map: dict | None = None) -> str:
    """Map an upstream ``kind`` to its canonical ``event_type``.

    Unknown kinds map to ``legacy.unmapped`` (FR-008).
    """
    doc = load_event_map() if event_map is None else event_map
    entry = doc["kinds"].get(kind)
    if entry is None:
        return doc["unknown_kind"]["event_type"]
    return entry["event_type"]


def registered_event_types(event_map: dict | None = None) -> set[str]:
    """All registered event types: mapped values plus ``legacy.unmapped`` plus
    every key under ``native`` (first-party types with no upstream kind)."""
    doc = load_event_map() if event_map is None else event_map
    return (
        {entry["event_type"] for entry in doc["kinds"].values()}
        | {doc["unknown_kind"]["event_type"]}
        | set((doc.get("native") or {}).keys())
    )


def _rejected_for_execution(event_map: dict) -> set[str]:
    return set((event_map.get("strict_execution") or {}).get("reject") or ())


def _epoch_to_rfc3339(t: float) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _rfc3339_to_epoch(text: str) -> float:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.timestamp()


def _episode_ref(data: dict) -> str | None:
    """Derive ep.* from a real upstream ``data.episode`` integer; else null."""
    episode = data.get("episode")
    if isinstance(episode, int) and not isinstance(episode, bool) and episode >= 0:
        return f"ep.{episode:06d}"
    return None


def wrap(record: dict, event_map: dict | None = None) -> dict:
    """Map one upstream ``{seq, t, kind, data}`` record to a canonical envelope.

    ``data`` is carried verbatim as the payload for mapped kinds; unknown kinds
    are wrapped as ``{"kind": <raw>, "data": <verbatim>}`` under
    ``legacy.unmapped`` so nothing upstream is ever rewritten or dropped.
    """
    doc = load_event_map() if event_map is None else event_map
    kind = record["kind"]
    data = record.get("data") or {}
    entry = doc["kinds"].get(kind)
    if entry is None:
        event_type = doc["unknown_kind"]["event_type"]
        payload = {"kind": kind, "data": data}
        classification = "internal"
    else:
        event_type = entry["event_type"]
        payload = data
        classification = entry.get("privacy", "internal")
    sequence = record["seq"]
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"evt.bus-{sequence:06d}",
        "episode_id": _episode_ref(data),
        "sequence": sequence,
        "event_type": event_type,
        "game_tick": None,
        "wall_time_utc": _epoch_to_rfc3339(record["t"]),
        "source": DEFAULT_SOURCE,
        "correlation": None,
        "revisions": None,
        "payload": payload,
        "privacy": {"classification": classification, "redactions": []},
    }


def unwrap(record: dict, event_map: dict | None = None) -> dict:
    """Map a canonical envelope back to the upstream ``{seq, t, kind, data}``."""
    doc = load_event_map() if event_map is None else event_map
    event_type = record["event_type"]
    if event_type == doc["unknown_kind"]["event_type"]:
        kind = record["payload"]["kind"]
        data = record["payload"]["data"]
    else:
        reverse = {entry["event_type"]: k for k, entry in doc["kinds"].items()}
        if event_type not in reverse:
            raise EventMapError(f"unregistered event_type {event_type!r}")
        kind = reverse[event_type]
        data = record["payload"]
    return {
        "seq": record["sequence"],
        "t": _rfc3339_to_epoch(record["wall_time_utc"]),
        "kind": kind,
        "data": data,
    }


@lru_cache(maxsize=1)
def _schema_registry() -> Registry:
    """referencing.Registry resolving every schema under schemas/ by its $id."""
    resources = []
    for path in sorted(SCHEMAS_DIR.rglob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _validator(schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema, registry=_schema_registry())


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _errors(schema: dict, instance: Any) -> list[str]:
    return sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '/'}: {e.message}"
        for e in _validator(schema).iter_errors(instance)
    )


def validate_envelope(record: Any) -> list[str]:
    """Schema-validate a record against the envelope schema (archival/storage path).

    Returns sorted error strings; empty list means accepted. This path has no
    schema_version ceiling: storage preserves newer-version records losslessly.
    """
    return _errors(_load_schema(ENVELOPE_SCHEMA_PATH), record)


def _payload_schema_path(event_type: str) -> Path:
    return PAYLOAD_TYPES_DIR / f"{event_type}.schema.json"


def consume_strict(record: Any, max_schema_version: int = SCHEMA_VERSION) -> dict:
    """Strict execution-consumer gate (FR-006/FR-008).

    Returns the shared result envelope. Rejects, in order:

    1. non-object records or missing/non-integer ``schema_version``
       (``contract.validation.failed``);
    2. ``schema_version > max_schema_version`` — ``schema.version.too_new``,
       checked before schema validation so the named code is never masked;
    3. envelope schema violations (``contract.validation.failed``);
    4. unregistered ``event_type`` (``event.type.unregistered``);
    5. registered-but-not-executable types, i.e. ``legacy.unmapped``
       (``event.type.not_executable`` — stored, never executed);
    6. payload schema violations (``contract.validation.failed``).
    """
    event_map = load_event_map()
    if not isinstance(record, dict):
        return error_envelope(
            "contract.validation.failed",
            "Record is not a JSON object",
            details={"expected": "events/envelope"},
        )
    version = record.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        return error_envelope(
            "contract.validation.failed",
            "schema_version is missing or not a non-negative integer",
            details={"schema_version": version},
        )
    if version > max_schema_version:
        return error_envelope(
            "schema.version.too_new",
            f"Record declares schema_version {version}; consumer maximum is {max_schema_version}",
            details={"schema_version": version, "consumer_max": max_schema_version},
        )
    errors = validate_envelope(record)
    if errors:
        return error_envelope(
            "contract.validation.failed",
            "Record rejected by events/envelope schema",
            details={"errors": errors},
        )
    event_type = record["event_type"]
    if event_type not in registered_event_types(event_map):
        return error_envelope(
            "event.type.unregistered",
            f"event_type {event_type!r} is not in the registered event map",
            details={"event_type": event_type},
        )
    if event_type in _rejected_for_execution(event_map):
        return error_envelope(
            "event.type.not_executable",
            f"event_type {event_type!r} is preserved for storage but not executable",
            details={"event_type": event_type},
        )
    payload_schema_path = _payload_schema_path(event_type)
    if not payload_schema_path.is_file():
        return error_envelope(
            "event.payload.schema_missing",
            f"No payload schema for event_type {event_type!r}",
            details={"event_type": event_type},
        )
    payload_errors = _errors(_load_schema(payload_schema_path), record["payload"])
    if payload_errors:
        return error_envelope(
            "contract.validation.failed",
            f"Payload rejected by schema for event_type {event_type!r}",
            details={"event_type": event_type, "errors": payload_errors},
        )
    return {"ok": True, "result": record}


def check_stream_order(records: list[dict]) -> dict:
    """Load-time stream check: ``sequence`` strictly increasing, no gaps/dupes.

    Per the envelope contract validation rules; returns the shared envelope.
    """
    seen: set[int] = set()
    previous: int | None = None
    for index, record in enumerate(records):
        sequence = record.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            return error_envelope(
                "event.sequence.invalid",
                f"Record {index} has no integer sequence",
                details={"index": index},
            )
        if sequence in seen:
            return error_envelope(
                "event.sequence.duplicate",
                f"Duplicate sequence {sequence} at record {index}",
                details={"index": index, "sequence": sequence},
            )
        if previous is not None and sequence != previous + 1:
            return error_envelope(
                "event.sequence.gap",
                f"Sequence gap/decrease: {previous} -> {sequence} at record {index}",
                details={"index": index, "previous": previous, "sequence": sequence},
            )
        seen.add(sequence)
        previous = sequence
    return {"ok": True, "result": len(records)}
