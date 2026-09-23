#!/usr/bin/env python3
"""Upstream-baseline integrity scanner (T008; FR-002, SC-006).

Verifies the pinned upstream checkout that every fork validation story depends
on:

  1. Locates git via PATH, falling back to the standard Windows install path.
  2. Auto-recovers uninitialized submodules (a ``-`` or ``U`` prefix in
     ``git submodule status`` triggers ``git submodule update --init
     --recursive`` once, then re-checks).
  3. Compares ``git rev-parse HEAD`` per submodule against the recorded pins
     (EXPECTED_PINS below; also recorded in AGENTS.md).
  4. Requires ``git status --porcelain`` to be clean inside the pinned
     worktrees (``upstream/rimagent`` and its nested ``mod`` submodule).

Success: exit 0 and print a human-readable summary.
Any drift or failure: exit 1 and print a structured error envelope on stdout::

    {"ok": false, "error": {"code": "...", "message": "...",
                            "details": {...}, "retryable": true|false}}

The envelope shape is the shared error primitive (contracts/error.schema.json).
``upstream/`` is READ-ONLY: this tool never writes inside it (submodule
recovery only materializes the recorded pin, it does not modify content).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# --- Manifest of record -----------------------------------------------------
# Pinned submodule revisions (context facts; mirrored in AGENTS.md and
# specs/001-fork-bootstrap-contracts/quickstart.md section 1).
EXPECTED_PINS = {
    "upstream/rimagent": "85cb050dec47691f2a80096fdc8c8a8e2051bb13",
    "upstream/rimagent/mod": "3c1e4c7cee151104b85bf9c8372e113f91c5f08d",
}

# Worktrees whose porcelain status must be empty (baseline must be pristine).
PORCELAIN_DIRS = ["upstream/rimagent", "upstream/rimagent/mod"]

GIT_FALLBACK = r"C:\Program Files\Git\cmd\git.exe"
GIT_TIMEOUT_S = 60
SUBMODULE_UPDATE_TIMEOUT_S = 300

_STATUS_LINE = re.compile(r"^([ +-U])([0-9a-fA-F]{40}) (\S+)(?: \(.*\))?$")


def emit_error(code: str, message: str, details: dict, retryable: bool) -> "NoReturn":  # noqa: F821
    """Print the structured error envelope on stdout and exit nonzero."""
    envelope = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "retryable": retryable,
        },
    }
    print(json.dumps(envelope, indent=2, sort_keys=True))
    sys.exit(1)


def find_git() -> str | None:
    """Locate git: PATH first, then the standard Windows install fallback."""
    on_path = shutil.which("git")
    if on_path:
        return on_path
    if os.path.isfile(GIT_FALLBACK):
        return GIT_FALLBACK
    return None


def run_git(git: str, repo: str | Path, args: list[str], timeout: int = GIT_TIMEOUT_S) -> subprocess.CompletedProcess:
    """Run a git command, returning the CompletedProcess (no exceptions on rc!=0)."""
    try:
        return subprocess.run(
            [git, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        emit_error(
            "GIT_TIMEOUT",
            f"git {' '.join(args)} exceeded {timeout}s in {repo}",
            {"repo": str(repo), "args": args, "timeout_s": timeout},
            retryable=True,
        )
    except OSError as exc:  # pragma: no cover - defensive
        emit_error(
            "GIT_EXEC_FAILED",
            f"could not execute git: {exc}",
            {"git": git, "repo": str(repo), "args": args},
            retryable=True,
        )


def git_stdout(git: str, repo: str | Path, args: list[str], code: str, timeout: int = GIT_TIMEOUT_S) -> str:
    """Run git and return stdout, emitting a structured error on failure."""
    proc = run_git(git, repo, args, timeout=timeout)
    if proc.returncode != 0:
        emit_error(
            code,
            f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip() or proc.stdout.strip()}",
            {"repo": str(repo), "args": args, "returncode": proc.returncode,
             "stderr": proc.stderr.strip()},
            retryable=True,
        )
    return proc.stdout


def submodule_status(git: str, root: Path) -> list[dict]:
    """Parse `git submodule status --recursive` into structured entries."""
    out = git_stdout(git, root, ["submodule", "status", "--recursive"],
                     code="SUBMODULE_STATUS_FAILED")
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        m = _STATUS_LINE.match(line)
        if not m:
            emit_error(
                "SUBMODULE_STATUS_UNPARSEABLE",
                f"unrecognized submodule status line: {line!r}",
                {"line": line},
                retryable=False,
            )
        flag, sha, path = m.groups()
        entries.append({"flag": flag, "sha": sha.lower(), "path": path})
    return entries


def main() -> int:
    script_dir = Path(__file__).resolve().parent

    # 1. Locate git.
    git = find_git()
    if not git:
        emit_error(
            "GIT_NOT_FOUND",
            "git not found on PATH and fallback path does not exist",
            {"path_fallback": GIT_FALLBACK},
            retryable=True,
        )

    # 2. Resolve repo root (works even if invoked from elsewhere).
    top = git_stdout(git, script_dir, ["rev-parse", "--show-toplevel"],
                     code="REPO_ROOT_NOT_FOUND").strip()
    if not top:
        emit_error("REPO_ROOT_NOT_FOUND",
                   "git rev-parse --show-toplevel returned empty",
                   {"cwd": str(script_dir)}, retryable=False)
    root = Path(top)

    # 3. Auto-recover uninitialized submodules.
    entries = submodule_status(git, root)
    flagged = [e["path"] for e in entries if e["flag"] in ("-", "U")]
    if flagged:
        run_git(git, root, ["submodule", "update", "--init", "--recursive"],
                timeout=SUBMODULE_UPDATE_TIMEOUT_S)
        entries = submodule_status(git, root)
        still = [e["path"] for e in entries if e["flag"] in ("-", "U")]
        if still:
            emit_error(
                "SUBMODULE_INIT_FAILED",
                "submodules still uninitialized after update --init --recursive",
                {"uninitialized": still},
                retryable=True,
            )

    # 4. Compare each submodule HEAD against the recorded pin.
    mismatches = []
    missing = []
    for path, expected in EXPECTED_PINS.items():
        worktree = root / path
        if not worktree.is_dir():
            missing.append(path)
            continue
        actual = git_stdout(git, worktree, ["rev-parse", "HEAD"],
                            code="REV_PARSE_FAILED").strip().lower()
        if actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
    extras = [e["path"] for e in entries if e["path"] not in EXPECTED_PINS]
    if missing or mismatches:
        emit_error(
            "PIN_MISMATCH",
            "submodule pins do not match the recorded baseline",
            {"mismatches": mismatches, "missing_worktrees": missing,
             "unpinned_submodules": extras},
            retryable=False,
        )

    # 5. Porcelain cleanliness inside the pinned worktrees.
    dirty = {}
    for rel in PORCELAIN_DIRS:
        worktree = root / rel
        if not worktree.is_dir():
            continue
        out = git_stdout(git, worktree, ["status", "--porcelain"],
                         code="PORCELAIN_FAILED")
        lines = [ln for ln in out.splitlines() if ln.strip()]
        if lines:
            dirty[rel] = lines[:100]
    if dirty:
        emit_error(
            "BASELINE_DIRTY",
            "pinned upstream baseline has uncommitted content; "
            "upstream/ is read-only and must be pristine",
            {"dirty": dirty},
            retryable=False,
        )

    # Success: human summary.
    print("baseline integrity: OK")
    print(f"  repo root: {root}")
    print(f"  git: {git}")
    for path, expected in EXPECTED_PINS.items():
        print(f"  ok:{path} @ {expected[:12]} (pin match)")
    for rel in PORCELAIN_DIRS:
        print(f"  ok:{rel} porcelain clean")
    if extras:
        print(f"  note: unpinned submodules present: {', '.join(extras)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
