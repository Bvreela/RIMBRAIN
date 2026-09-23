#!/usr/bin/env python3
"""Shared component validation runner (T011; FR-003).

Discovers each ``components/*/`` directory and invokes its declared
self-check, in priority order:

  1. ``validate.py``  -> run with the current interpreter.
  2. ``pyproject.toml`` + a ``tests/`` dir containing ``test_*.py``
                      -> run ``uv run --with pytest pytest tests -q`` when uv
                      is available (isolated env resolved from the component's
                      own pyproject), else ``python -m pytest tests -q``.
  3. otherwise        -> skip with ``no validator``.

Prints a per-component banner with name/version/toolchain presence and an
``ok:<component>`` / ``skip:<component> (no validator)`` /
``fail:<component>`` line, then a summary. Exit 0 when nothing failed
(skips are not failures: placeholder components legitimately have no
validator yet). Runs fully offline -- no game, model, network, or secrets.

Usage: ``python tools/validate_components.py [--only NAME ...]``
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_DIR = REPO_ROOT / "components"
GIT_FALLBACK = r"C:\Program Files\Git\cmd\git.exe"
VALIDATOR_TIMEOUT_S = 300

_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


def toolchain_presence() -> dict[str, str]:
    """Report toolchain presence without requiring any of it (FR-003)."""
    git = shutil.which("git") or (
        GIT_FALLBACK if Path(GIT_FALLBACK).is_file() else None
    )
    return {
        "python": ".".join(str(p) for p in sys.version_info[:3]),
        "git": "yes" if git else "no",
        "uv": "yes" if shutil.which("uv") else "no",
        "dotnet": "yes" if shutil.which("dotnet") else "no",
    }


def component_version(comp: Path) -> str:
    pyproject = comp / "pyproject.toml"
    if pyproject.is_file():
        m = _VERSION_RE.search(pyproject.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return "unversioned"


def declared_validator(comp: Path) -> list[str] | None:
    """Return the self-check command for a component, or None if undeclared."""
    if (comp / "validate.py").is_file():
        return [sys.executable, "validate.py"]
    tests_dir = comp / "tests"
    if (comp / "pyproject.toml").is_file() and tests_dir.is_dir() and any(
        tests_dir.glob("test_*.py")
    ):
        if shutil.which("uv"):
            # Isolated env resolved from the component's own pyproject; works
            # even when the system interpreter lacks pytest.
            return ["uv", "run", "--with", "pytest", "pytest", "tests", "-q"]
        return [sys.executable, "-m", "pytest", "tests", "-q"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only", nargs="+", metavar="NAME",
        help="validate only the named component(s)",
    )
    args = parser.parse_args()

    if not COMPONENTS_DIR.is_dir():
        print("fail:components directory not found", file=sys.stderr)
        return 1

    tools = toolchain_presence()
    tool_summary = " ".join(f"{k}={v}" for k, v in tools.items())

    only = set(args.only or [])
    results: dict[str, str] = {}
    for comp in sorted(p for p in COMPONENTS_DIR.iterdir() if p.is_dir()):
        name = comp.name
        if only and name not in only:
            continue
        version = component_version(comp)
        cmd = declared_validator(comp)
        if cmd is None:
            print(f"component:{name} version:{version} {tool_summary} validator:none")
            print(f"skip:{name} (no validator)")
            results[name] = "skip"
            continue
        kind = "validate.py" if cmd[1] == "validate.py" else "pytest tests/"
        print(f"component:{name} version:{version} {tool_summary} validator:{kind}")
        try:
            proc = subprocess.run(
                cmd, cwd=comp, capture_output=True, text=True,
                timeout=VALIDATOR_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            proc = None
            print(f"  validator exceeded {VALIDATOR_TIMEOUT_S}s")
        if proc is not None and proc.returncode == 0:
            tail = (proc.stdout or "").strip().splitlines()
            for line in tail[-5:]:
                print(f"  {line}")
            print(f"ok:{name}")
            results[name] = "ok"
        else:
            rc = proc.returncode if proc is not None else "timeout"
            detail = ""
            if proc is not None:
                detail = (proc.stdout + proc.stderr).strip().splitlines()
            print(f"fail:{name} (rc={rc})")
            for line in (detail[-20:] if detail else []):
                print(f"  {line}")
            results[name] = "fail"

    ok = sum(1 for v in results.values() if v == "ok")
    skip = sum(1 for v in results.values() if v == "skip")
    fail = sum(1 for v in results.values() if v == "fail")
    print(f"summary: {ok} ok, {skip} skipped (no validator), {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
