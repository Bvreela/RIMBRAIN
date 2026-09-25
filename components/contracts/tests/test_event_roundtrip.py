"""Event round-trip contract test (SC-004, FR-008).

Every synthesized upstream ``bus.py`` record in the baseline corpus
(``baselines/upstream-85cb050/event-corpus/bus-kinds.jsonl`` — 18 kinds per the
real bus.py docstring) is mapped through ``registry/event-map.yaml`` into the
canonical envelope, serialized through canonical JSON (RFC 8785 — the byte form
records are stored/hashed in), and unwrapped again. The original
``{seq, kind, data}`` must be reproduced losslessly, with ordering preserved.

An unknown-kind record must map to ``legacy.unmapped``: stored (envelope-valid)
but rejected by the strict execution consumer (FR-008).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTRACTS_DIR.parents[1]
sys.path.insert(0, str(CONTRACTS_DIR / "src"))

from contracts import canonical_bytes, canonical_hash
from contracts import eventmap

CORPUS_PATH = (
    REPO_ROOT / "baselines" / "upstream-85cb050" / "event-corpus" / "bus-kinds.jsonl"
)

EXPECTED_KINDS = [
    "status",
    "think_start",
    "reasoning",
    "assistant",
    "tool_call",
    "tool_result",
    "think_end",
    "ledger",
    "watcher",
    "brain_change",
    "watchdog",
    "episode_start",
    "episode_end",
    "situation",
    "operator",
    "reply",
    "log",
    "error",
]


def _corpus() -> list[dict]:
    return [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_corpus_covers_all_18_upstream_kinds() -> None:
    records = _corpus()
    assert len(records) == 18
    assert [r["kind"] for r in records] == EXPECTED_KINDS


def test_event_map_covers_corpus_bijectively() -> None:
    event_map = eventmap.load_event_map()
    mapped_kinds = set(event_map["kinds"])
    assert mapped_kinds == set(EXPECTED_KINDS)
    event_types = [eventmap.map_kind(k, event_map) for k in EXPECTED_KINDS]
    # kind -> event_type must be a bijection so unwrap() can recover the kind.
    assert len(set(event_types)) == 18
    assert eventmap.UNMAPPED_EVENT_TYPE not in event_types


@pytest.mark.parametrize("index", range(18), ids=EXPECTED_KINDS)
def test_roundtrip_lossless(index: int) -> None:
    original = _corpus()[index]

    envelope = eventmap.wrap(original)

    # Storage path: the canonical record must validate against the envelope
    # schema and against its event_type payload schema (strict consumer).
    assert eventmap.validate_envelope(envelope) == []
    verdict = eventmap.consume_strict(envelope)
    assert verdict == {"ok": True, "result": envelope}, verdict

    # Serialize through canonical JSON (the stored/hashed byte form) and back.
    wire = canonical_bytes(envelope)
    restored = json.loads(wire.decode("utf-8"))
    assert canonical_hash(restored) == canonical_hash(envelope)

    unwrapped = eventmap.unwrap(restored)
    assert unwrapped["seq"] == original["seq"]
    assert unwrapped["kind"] == original["kind"]
    assert unwrapped["data"] == original["data"]
    assert abs(unwrapped["t"] - original["t"]) < 0.001


def test_ordering_preserved() -> None:
    originals = _corpus()
    restored = [
        eventmap.unwrap(json.loads(canonical_bytes(eventmap.wrap(r)).decode("utf-8")))
        for r in originals
    ]
    assert [r["seq"] for r in restored] == [r["seq"] for r in originals]
    envelopes = [eventmap.wrap(r) for r in originals]
    assert eventmap.check_stream_order(envelopes)["ok"] is True


def test_mapped_records_never_fabricate_sources() -> None:
    # R5: game_tick, correlation, revisions have no upstream source -> null.
    for original in _corpus():
        envelope = eventmap.wrap(original)
        assert envelope["game_tick"] is None
        assert envelope["correlation"] is None
        assert envelope["revisions"] is None
        assert envelope["privacy"]["redactions"] == []
    # reasoning is the one restricted-classification kind per the mapping table.
    reasoning = eventmap.wrap(_corpus()[2])
    assert reasoning["event_type"] == "model.reasoning"
    assert reasoning["privacy"]["classification"] == "restricted"


def test_unknown_kind_maps_to_legacy_unmapped() -> None:
    original = {"seq": 99, "t": 1790035200.0, "kind": "telemetry", "data": {"x": 1}}
    envelope = eventmap.wrap(original)

    assert envelope["event_type"] == "legacy.unmapped"
    # Raw kind preserved verbatim inside the payload.
    assert envelope["payload"] == {"kind": "telemetry", "data": {"x": 1}}

    # Stored: envelope-schema valid, survives a canonical serialization round.
    assert eventmap.validate_envelope(envelope) == []
    restored = json.loads(canonical_bytes(envelope).decode("utf-8"))
    unwrapped = eventmap.unwrap(restored)
    assert unwrapped["kind"] == "telemetry"
    assert unwrapped["data"] == {"x": 1}

    # ...but rejected by the strict execution consumer (FR-008).
    verdict = eventmap.consume_strict(envelope)
    assert verdict["ok"] is False
    assert verdict["error"]["code"] == "event.type.not_executable"
    assert verdict["error"]["retryable"] is False
