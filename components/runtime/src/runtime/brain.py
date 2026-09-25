"""Live brain-reset control channel (feature 013, FR-1107/1108).

The dashboard overlay posts ``state/brain_reset.request``; a runtime
launched with ``--live-brain`` polls for it each iteration, re-validates
and reloads the active pack, clears planning/mode state, and re-derives
goals from the colony as-observed. Result lands in
``state/brain_status.json`` for the overlay to render.

The channel is deliberately inert without ``--live-brain``: scored and
immutable runs never set the flag, so UR-BRN pack immutability holds —
a stray request file is refused, never honored.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUEST = "brain_reset.request"
STATUS = "brain_status.json"


def poll_request(state_dir: Path, enabled: bool,
                 started_at: float | None = None) -> dict | None:
    """Consume a pending reset request. Returns None when absent.

    When the channel is disabled the file is still consumed and a refusal
    is written — an unanswered request must not linger into a later run
    that does enable it. A request whose file predates ``started_at``
    (the run's launch time) is a leftover from a previous session — it
    is consumed and refused the same way, never honored.
    """
    req_path = state_dir / REQUEST
    if not req_path.is_file():
        return None
    try:
        raw = req_path.read_text(encoding="utf-8").strip()
        mtime = req_path.stat().st_mtime
    except OSError:
        raw, mtime = "", None
    try:
        req_path.unlink()
    except OSError:
        pass
    if started_at is not None and mtime is not None \
            and mtime < started_at:
        write_status(state_dir, ok=False,
                     error="stale request predates this run — ignored")
        return None
    if not enabled:
        write_status(state_dir, ok=False,
                     error="live-brain channel disabled (launch with --live-brain)")
        return None
    try:
        req = json.loads(raw) if raw else {}
    except ValueError:
        req = {}
    return req if isinstance(req, dict) else {}


def write_status(state_dir: Path, **fields) -> None:
    try:
        (state_dir / STATUS).write_text(
            json.dumps(fields, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass
