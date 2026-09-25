"""Fixture exporter for completed retry-loop runs (T052; FR-209, US4).

Turns a ``lab.retryloop.run_loop`` result into a US5 fixture package
(``specs/001-fork-bootstrap-contracts/contracts/fixture-package.md``) that
``lab.fixtures.run_fixture`` replays offline:

```text
fix.retry-<slug>/
|-- manifest.yaml    # provenance + sha256 of every member
|-- input.jsonl      # canonical retry.* envelopes, one per line
|-- expected.jsonl   # per-event {event_type, sequence, payload} projections
+-- run.json         # run summary: outcome, checkpoint, iterations, candidate
```

``expected.jsonl`` holds a projection of each input envelope so replay under
``expected_comparison.mode=field-subset`` verifies event type, ordering, and
payload -- the fields a reviewer diffs to answer "which mutation produced this
outcome" (SC-203) -- while tolerating re-recorded ids/timestamps.

Canonical bytes come from ``contracts.canonical_bytes`` when the sibling
contracts package is importable (same soft-optional pattern as fixtures.py);
the fallback is sorted-keys compact JSON, identical for ASCII-safe content.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

__all__ = ["export_fixture"]

_ID_TAIL = re.compile(r"[^A-Za-z0-9_-]+")


def _canonical_bytes(obj: Any) -> bytes:
    try:
        from contracts import canonical_bytes  # type: ignore

        return canonical_bytes(obj)
    except ImportError:
        candidate = Path(__file__).resolve().parents[3] / "contracts" / "src"
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            try:
                from contracts import canonical_bytes  # type: ignore

                return canonical_bytes(obj)
            except ImportError:
                pass
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(text: str) -> str:
    slug = _ID_TAIL.sub("-", str(text)).strip("-").lower()
    return slug or "run"


def _fixture_id_for(result: dict) -> str:
    run_id = str(result.get("run_id") or "run.unknown")
    tail = run_id.split(".", 1)[-1]
    return f"fix.retry-{_slug(tail)}"


def export_fixture(
    result: dict,
    dest_dir: str | Path,
    *,
    fixture_id: str | None = None,
    source: str = "synthesized",
    mode: str = "field-subset",
    created_utc: str | None = None,
    notes: str | None = None,
) -> Path:
    """Export one completed run result as a US5 fixture package.

    ``source`` is the manifest provenance source
    (``live-run`` | ``synthesized`` | ``baseline-bundle``); ``created_utc``
    defaults to the last emitted event's ``wall_time_utc`` so deterministic
    (ManualClock) runs produce byte-identical packages.
    """
    events = result.get("events") or []
    fixture_id = fixture_id or _fixture_id_for(result)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    input_bytes = b"".join(_canonical_bytes(e) + b"\n" for e in events)
    expected_lines = [
        {
            "event_type": e["event_type"],
            "sequence": e["sequence"],
            "payload": e["payload"],
        }
        for e in events
    ]
    expected_bytes = b"".join(_canonical_bytes(e) + b"\n" for e in expected_lines)

    run_doc = {
        "run_id": result.get("run_id"),
        "config_id": result.get("config_id"),
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "error": result.get("error"),
        "checkpoint": result.get("checkpoint"),
        "window_ticks": result.get("window_ticks"),
        "max_retries": result.get("max_retries"),
        "speed": result.get("speed"),
        "iterations": result.get("iterations") or [],
        "candidate": result.get("candidate"),
        "event_ids": [e["event_id"] for e in events],
    }
    run_bytes = _canonical_bytes(run_doc) + b"\n"

    (dest / "input.jsonl").write_bytes(input_bytes)
    (dest / "expected.jsonl").write_bytes(expected_bytes)
    (dest / "run.json").write_bytes(run_bytes)

    if created_utc is None:
        created_utc = events[-1]["wall_time_utc"] if events else "1970-01-01T00:00:00Z"
    manifest = {
        "schema_version": 0,
        "fixture_id": fixture_id,
        "created_utc": created_utc,
        "provenance": {
            "source": source,
            "source_hash": _sha256(input_bytes),
            "notes": notes
            or "checkpoint-retry loop run exported by lab.retryfixture "
            "(feature 003); input.jsonl is the emitted retry.* event stream.",
        },
        "schema_pins": {
            "envelope_schema": "schemas/events/envelope.schema.json",
            "envelope_schema_version": 0,
            "retry_config_schema": "schemas/runtime/retry-config.schema.json",
            "retry_config_schema_version": 0,
            "retry_config_id": result.get("config_id"),
        },
        "files": {
            "input.jsonl": _sha256(input_bytes),
            "expected.jsonl": _sha256(expected_bytes),
            "run.json": _sha256(run_bytes),
        },
        "expected_comparison": {"mode": mode},
    }
    if result.get("episode_id"):
        manifest["provenance"]["episode_id"] = result["episode_id"]
    (dest / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    return dest
