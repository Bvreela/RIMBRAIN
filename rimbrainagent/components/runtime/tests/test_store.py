"""Event store tests (feature 006; FR-501..503/506/507, SC-501..503).

- append/load round-trip survives reopen (SC-501);
- torn tail truncated to last newline + recovery marker (SC-502);
- complete-but-unterminated final line preserved;
- mid-file corruption counted and skipped, never rewritten;
- sequence gaps reported; write_atomic leaves no .tmp (SC-503).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime.store import EventStore, write_atomic  # noqa: E402

import json


def _env(seq: int, etype: str = "action.issued") -> dict:
    return {"schema_version": 0, "event_id": f"evt.x-{seq:06d}",
            "sequence": seq, "event_type": etype, "game_tick": seq,
            "wall_time_utc": "2026-01-01T00:00:00Z",
            "source": "test", "correlation": {},
            "revisions": {"schema_version": 0},
            "payload": {"template_id": "t", "outcome": "issued",
                        "pack_revision": "h", "params": {}},
            "privacy": {"classification": "internal", "redactions": []}}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    return EventStore(tmp_path / "events.jsonl")


def test_round_trip_across_reopen(store, tmp_path):
    """SC-501: append, new instance, all events replayed in order."""
    for i in range(1, 4):
        store.append(_env(i))
    reopened = EventStore(tmp_path / "events.jsonl")
    data = reopened.load()
    assert data["total"] == 3
    assert [e["sequence"] for e in data["events"]] == [1, 2, 3]
    assert data["corrupt_lines"] == 0


def test_torn_tail_salvaged(tmp_path, monkeypatch):
    """SC-502: truncated final line removed; recovery marker written."""
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    path = tmp_path / "events.jsonl"
    path.write_bytes(
        json.dumps(_env(1)).encode() + b"\n"
        + json.dumps(_env(2)).encode() + b"\n"
        + b'{"schema_version": 0, "event_id": "evt.x-0000')
    s = EventStore(path, clock=lambda: "2026-01-01T00:00:00Z")
    data = s.load()
    assert data["total"] == 2 and data["corrupt_lines"] == 0
    rec = (tmp_path / "recovery.jsonl").read_text()
    assert "torn_tail" in rec and '"salvaged_bytes"' in rec


def test_complete_unterminated_tail_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    path = tmp_path / "events.jsonl"
    path.write_bytes(json.dumps(_env(1)).encode() + b"\n"
                     + json.dumps(_env(2)).encode())  # no trailing newline
    s = EventStore(path)
    assert s.load()["total"] == 2
    assert not (tmp_path / "recovery.jsonl").exists()


def test_midfile_corruption_counted_not_rewritten(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    path = tmp_path / "events.jsonl"
    good = json.dumps(_env(1)).encode()
    path.write_bytes(good + b"\n" + b"not json\n" + good + b"\n")
    s = EventStore(path)
    data = s.load()
    assert data["total"] == 2 and data["corrupt_lines"] == 1
    # file bytes unchanged by load â€” append-only integrity
    assert b"not json\n" in path.read_bytes()


def test_sequence_gaps_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path))
    s = EventStore(tmp_path / "events.jsonl")
    for seq in (1, 2, 5, 5, 9):
        s.append(_env(seq))
    gaps = s.load()["sequence_gaps"]
    assert gaps == [2, 5, 5]  # prev at each violation: 2->5, 5->5, 5->9


def test_write_atomic_no_tmp_left(tmp_path):
    """SC-503: atomic write leaves the target and zero temp files."""
    out = write_atomic(tmp_path / "projection.json", b'{"a":1}\n')
    assert out.read_bytes() == b'{"a":1}\n'
    assert list(tmp_path.glob("*.tmp")) == []


def test_state_dir_env_honored(tmp_path, monkeypatch):
    monkeypatch.setenv("RIMBRAIN_STATE_DIR", str(tmp_path / "iso"))
    s = EventStore()  # default path under env dir
    s.append(_env(1))
    assert (tmp_path / "iso" / "events.jsonl").is_file()


def test_concurrent_appends_all_lines_intact(store):
    """T117/spec edge case: threaded appends through the msvcrt path produce
    N complete parseable lines — no interleaving, no torn writes."""
    import threading
    n = 40
    threads = [threading.Thread(
        target=lambda i=i: store.append(_env(i + 1, "loop.iteration")))
        for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = store.path.read_bytes().split(b"\n")
    assert lines[-1] == b""
    assert len(lines) - 1 == n
    for raw in lines[:-1]:
        json.loads(raw)  # every line is a complete canonical record
