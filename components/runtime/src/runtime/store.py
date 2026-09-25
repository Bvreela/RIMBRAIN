"""Canonical event/state stores (feature 006; WP-101, FR-501..503/506/507).

Flat-file canonical records are authoritative; anything derived is disposable.

- ``EventStore`` — append-only JSONL of canonical envelopes: one
  ``canonical_bytes(envelope)`` + ``\\n`` per event. Opening an existing log
  performs torn-tail recovery: an unparseable/truncated final line is cut back
  to the last newline and the salvage is recorded to ``recovery.jsonl`` —
  append-only, so only tail bytes are ever removed, and only when corrupt.
- ``load()`` replays the log in order, counting unparseable mid-file lines
  and reporting sequence gaps/dups — it never renumbers or rewrites.
- ``write_atomic(path, data)`` — tmp-file + ``os.replace``; readers see old or
  new, never partial. Same-volume, Windows-safe, no symlinks.

All paths honor ``RIMBRAIN_STATE_DIR`` (same convention as dispatch.py).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

try:  # Windows byte-range lock for cross-process append safety
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]

try:
    from contracts.canonical import canonical_bytes
except ImportError:  # pragma: no cover
    from contracts import canonical_bytes  # type: ignore[no-redef]

__all__ = ["EventStore", "write_atomic", "state_dir"]


def state_dir() -> Path:
    from ._root import repo_root
    return Path(os.environ.get(
        "RIMBRAIN_STATE_DIR",
        str(repo_root() / "state")))


def write_atomic(path: str | Path, data: bytes) -> Path:
    """All-or-nothing write: ``<path>.tmp`` then ``os.replace`` (SC-503).
    Windows AV/indexers transiently hold the target open (WinError 5) —
    retry briefly rather than crash the loop on a phantom lock."""
    import time
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    last = None
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return path
        except PermissionError as exc:
            last = exc
            time.sleep(0.1)
    raise last


class EventStore:
    """Append-only canonical JSONL log with torn-tail recovery."""

    def __init__(self, path: str | Path | None = None, *,
                 clock=None) -> None:
        self.dir = state_dir()
        self.path = Path(path) if path else self.dir / "events.jsonl"
        self.recovery_path = self.path.with_name("recovery.jsonl")
        self._lock = threading.Lock()
        self._clock = clock
        self.dir.mkdir(parents=True, exist_ok=True)
        self._recover_tail()

    # -- recovery ------------------------------------------------------------

    def _recover_tail(self) -> None:
        """Truncate a torn final line; complete-but-unterminated lines stay."""
        if not self.path.is_file():
            return
        data = self.path.read_bytes()
        if not data or data.endswith(b"\n"):
            return  # clean tail (or empty)
        last_nl = data.rfind(b"\n")
        tail = data[last_nl + 1:] if last_nl != -1 else data
        try:
            json.loads(tail)
            return  # complete final line, just unterminated — preserve
        except ValueError:
            pass
        salvaged = len(tail)
        with open(self.path, "r+b") as fh:
            fh.truncate(last_nl + 1 if last_nl != -1 else 0)
        self._record_recovery(salvaged, "torn_tail")

    def _record_recovery(self, salvaged_bytes: int, reason: str) -> None:
        rec = {"salvaged_bytes": salvaged_bytes, "reason": reason}
        if self._clock is not None:
            rec["ts"] = self._clock()
        line = json.dumps(rec, sort_keys=True).encode() + b"\n"
        with open(self.recovery_path, "ab") as fh:
            fh.write(line)

    # -- write ----------------------------------------------------------------

    @staticmethod
    def _win_lock(fh, pos: int) -> bool:
        """Best-effort 1-byte range lock at ``pos`` (msvcrt); never blocks.

        Returns True when the lock was taken so the caller can unlock.
        """
        if msvcrt is None:
            return False
        try:
            fh.seek(pos)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            fh.seek(0, os.SEEK_END)
            return True
        except OSError:
            fh.seek(0, os.SEEK_END)
            return False

    @staticmethod
    def _win_unlock(fh, pos: int) -> None:
        if msvcrt is None:
            return
        try:
            fh.seek(pos)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

    def append(self, envelope: dict) -> dict:
        """Canonical-JSON line append; drop-in dispatcher/planloop sink.

        In-process ``threading.Lock`` + a non-blocking ``msvcrt`` range lock at
        EOF (cross-process best-effort — a contested lock still appends; the
        log's integrity never depends on it).
        """
        line = canonical_bytes(envelope) + b"\n"
        with self._lock, open(self.path, "ab") as fh:
            pos = os.path.getsize(self.path) if self.path.exists() else 0
            locked = self._win_lock(fh, pos)
            try:
                fh.write(line)
            finally:
                if locked:
                    self._win_unlock(fh, pos)
        return envelope

    # -- read -----------------------------------------------------------------

    def load(self) -> dict:
        """Replay the log: ``{events, corrupt_lines, sequence_gaps}``.

        Mid-file corrupt lines are skipped and counted (never rewritten);
        ``sequence_gaps`` lists indices where ``sequence`` jumps or repeats.
        """
        events: list[dict] = []
        corrupt = 0
        if self.path.is_file():
            for raw in self.path.read_bytes().split(b"\n"):
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    corrupt += 1
                    continue
                events.append(obj)
        seqs = [e.get("sequence") for e in events
                if isinstance(e.get("sequence"), int)]
        gaps = [prev for prev, cur in zip(seqs, seqs[1:]) if cur != prev + 1]
        return {"events": events, "corrupt_lines": corrupt,
                "sequence_gaps": gaps, "total": len(events)}
