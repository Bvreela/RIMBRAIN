"""Path roots that survive PyInstaller freezing (UR-ARC-009).

Dev layout: everything resolves under the repo root. Frozen layout:
read-only bundled data lives under ``sys._MEIPASS`` mirroring the repo
relative paths; user-writable/user-editable data (state, packs, profiles)
resolves beside the executable so strategy files stay external.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)


def repo_root() -> Path:
    """Writable root: repo checkout in dev, executable's dir when frozen."""
    if _FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[4]


def bundle_root() -> Path:
    """Read-only bundled-data root: repo checkout in dev, MEIPASS frozen."""
    if _FROZEN:
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[4]
