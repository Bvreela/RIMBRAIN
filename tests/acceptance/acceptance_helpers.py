"""Shared helpers for superproject acceptance tests (US1).

Locates git via PATH with the standard Windows install fallback (git is not
on PATH on some dev machines; see AGENTS.md machine quirks) and provides a
thin subprocess wrapper. Imported by test modules via sys.path insertion of
this directory; named without a ``test_`` prefix so pytest does not collect
it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_FALLBACK = r"C:\Program Files\Git\cmd\git.exe"


def find_git() -> str:
    """Return a usable git executable path, or raise if none exists."""
    on_path = shutil.which("git")
    if on_path:
        return on_path
    if os.path.isfile(GIT_FALLBACK):
        return GIT_FALLBACK
    raise RuntimeError(f"git not found on PATH or at {GIT_FALLBACK}")


def run_git(*args: str, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run ``git -C <cwd> <args>`` and return the CompletedProcess."""
    return subprocess.run(
        [find_git(), "-C", str(cwd or REPO_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def git_stdout(*args: str, cwd: Path | None = None, timeout: int = 60) -> str:
    """Run git and return stdout; raises AssertionError on nonzero exit."""
    proc = run_git(*args, cwd=cwd, timeout=timeout)
    assert proc.returncode == 0, (
        f"git {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}"
    )
    return proc.stdout
