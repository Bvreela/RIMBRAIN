"""RimBrain single-executable launcher (UR-ARC-009).

One entry point for the whole app — dev (`python rimbrain.py ...`) and
frozen (`rimbrain.exe ...`) behave identically:

  rimbrain run [loop args]    runtime loop + dashboard overlay together
  rimbrain overlay [--args]   overlay only (also the frozen child entry)
  rimbrain loop <args>        runtime loop pass-through (no overlay)

`run` defaults to a fair live-brain start-mode pass; every `runtime loop`
flag passes straight through, e.g.
  rimbrain run --mode sim --pack core-survival-v0 --iterations 50

Writable data (state/, packs/, profiles/) resolves beside the executable
when frozen, beside this file in dev — never inside the bundle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
ROOT = (Path(sys.executable).resolve().parent if FROZEN
        else Path(__file__).resolve().parent)

_SRCS = ("components/runtime/src", "components/contracts/src",
         "components/dashboard/src")


def _extend_path() -> None:
    """Dev: make the component srcs importable in this process + children."""
    if FROZEN:
        return
    parts = [str(ROOT / s) for s in _SRCS]
    for p in reversed(parts):
        if p not in sys.path:
            sys.path.insert(0, p)
    env = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        parts + ([env] if env else []))


def _env() -> dict:
    env = dict(os.environ)
    env.setdefault("RIMBRAIN_STATE_DIR", str(ROOT / "state"))
    return env


def _packs_dir() -> str | None:
    """Editable packs root — mirrors runtime.templates.packs_dir.

    Frozen first run seeds ``packs/`` beside the exe from the bundled
    copies so the overlay's pack picker edits real files, not MEIPASS.
    """
    env = os.environ.get("RIMBRAIN_PACKS_DIR")
    if env:
        return env
    ext = ROOT / "packs"
    if ext.is_dir():
        return str(ext)
    bundled = (Path(sys._MEIPASS) if FROZEN else ROOT) / \
        "components" / "rimbrain" / "packs"
    if FROZEN and bundled.is_dir():
        try:
            shutil.copytree(bundled, ext)
            return str(ext)
        except OSError:
            pass
    return str(bundled) if bundled.is_dir() else None


def _overlay_cmd() -> list[str]:
    return ([sys.executable, "overlay"] if FROZEN
            else [sys.executable, "-m", "dashboard.overlay"])


def _run_overlay(argv: list[str]) -> int:
    sys.argv = ["dashboard.overlay"] + argv
    from dashboard import overlay
    return overlay.main(argv)


def _run_loop(argv: list[str]) -> int:
    from runtime import loop
    return loop.main(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _extend_path()
    cmd = argv[0] if argv else "run"
    rest = argv[1:]
    if cmd == "overlay":
        return _run_overlay(rest)
    if cmd == "loop":
        return _run_loop(rest)
    if cmd != "run":
        print(__doc__)
        return 2
    if not rest:  # default: the fair live-brain + live-mutate pass
        rest = ["--pack", "start-mode-v0", "--mode", "start",
                "--iterations", "2000", "--live-flag", "--fair",
                "--live-brain", "--live-mutate", "--feed"]
    oargs = ["--state-dir", _env()["RIMBRAIN_STATE_DIR"]]
    packs = _packs_dir()  # before _run_loop imports runtime: a fresh
    if packs:             # frozen seed lands where the loop resolves it
        oargs += ["--packs-dir", packs]
    proc = subprocess.Popen(_overlay_cmd() + oargs, env=_env())
    try:
        return _run_loop(rest)
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
