"""Floating agent-thought overlay (feature 013 follow-on; UR-VIEW-001..004).

An always-on-top, resizable desktop window that tails the canonical view
records the runtime already writes each poll — ``state/planning.json``
(goals view on top) and ``state/decisions.jsonl`` (quick-action matrix
below). It never imports runtime internals and never touches the game:
flat files in, pixels out. Safe to run beside a live game or a sim.

    python -m dashboard.overlay --state-dir state
"""

from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ACTION_ROWS = 60


def load_view(state_dir: Path) -> tuple[dict, list[dict]]:
    """Read the canonical view records; missing/torn files -> empty."""
    planning = {}
    try:
        planning = json.loads(
            (state_dir / "planning.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    decisions: list[dict] = []
    try:
        lines = (state_dir / "decisions.jsonl").read_text(
            encoding="utf-8").splitlines()
        decisions = [json.loads(l) for l in lines[-ACTION_ROWS:] if l.strip()]
    except (OSError, ValueError):
        pass
    return planning, decisions


def _fmt_params(p: dict) -> str:
    s = json.dumps(p, separators=(",", ":"), default=str)
    return s if len(s) <= 72 else s[:69] + "..."


def epoch_window(rows: list[dict]) -> list[dict]:
    """Rows since the last save-load epoch boundary.

    A ``load-game`` dispatch or a tick decrease (save loaded, checkpoint
    restored) starts a fresh epoch — earlier decisions described a world
    that no longer exists, so the matrix resets to the current epoch.
    ``decisions.jsonl`` itself stays append-only canonical; this is a
    display window only."""
    cut = 0
    prev_tick = None
    for i, r in enumerate(rows):
        if r.get("template") == "load-game":
            cut = i + 1
        t = r.get("tick")
        if (i >= cut and isinstance(t, int)
                and isinstance(prev_tick, int) and t < prev_tick):
            cut = i
        prev_tick = t
    return rows[cut:]


class Overlay(tk.Tk):
    def __init__(self, state_dir: Path, interval_ms: int = 1000,
                 topmost: bool = True, alpha: float = 0.92):
        super().__init__()
        self.state_dir = state_dir
        self.interval = interval_ms
        self.title("RimBrain agent")
        self.attributes("-topmost", topmost)
        self.attributes("-alpha", alpha)
        self.minsize(340, 240)

        self.header = ttk.Label(self, font=("Consolas", 10, "bold"))
        self.header.pack(fill="x", padx=6, pady=(4, 0))

        cols = ("goal", "state", "tries", "success condition", "blocker")
        self.goals = ttk.Treeview(self, columns=cols, show="headings",
                                  height=8)
        widths = (110, 80, 45, 260, 140)
        for c, w in zip(cols, widths):
            self.goals.heading(c, text=c)
            self.goals.column(c, width=w,
                              stretch=c in ("success condition",
                                            "blocker"))
        self.goals.pack(fill="x", padx=6, pady=2)
        self.exit_lbl = ttk.Label(self, font=("Consolas", 9))
        self.exit_lbl.pack(fill="x", padx=6)

        self.actions = tk.Text(self, font=("Consolas", 9), height=14,
                               state="disabled", wrap="none",
                               bg="#101010", fg="#c8c8c8")
        self.actions.pack(fill="both", expand=True, padx=6, pady=4)

        self._mtimes: dict[str, float] = {}
        self.after(0, self._refresh)

    def _changed(self, name: str) -> bool:
        try:
            m = (self.state_dir / name).stat().st_mtime
        except OSError:
            return False
        if self._mtimes.get(name) != m:
            self._mtimes[name] = m
            return True
        return False

    def _refresh(self):
        planning, decisions = load_view(self.state_dir)
        self._render_planning(planning)
        if self._changed("decisions.jsonl"):
            self._render_actions(decisions)
        self.after(self.interval, self._refresh)

    def _render_planning(self, p: dict):
        self.header.config(text=(
            f"{p.get('mode', '—')}  tick {p.get('tick', '—')}  "
            f"poll {p.get('poll', '—')}  pack {p.get('pack_revision', '—')}"
            + ("  COMPLETE" if p.get("complete") else "")))
        self.goals.delete(*self.goals.get_children())
        for g in p.get("goals") or []:
            self.goals.insert("", "end", values=(
                g.get("id"), g.get("state"), g.get("attempts", 0),
                g.get("effect") or g.get("detail") or "—",
                g.get("blocker") or "—"))
        exits = p.get("exit_conditions") or {}
        self.exit_lbl.config(text="  ".join(
            f"[{'x' if ok else ' '}] {k}" for k, ok in exits.items()))

    def _render_actions(self, rows: list[dict]):
        self.actions.config(state="normal")
        self.actions.delete("1.0", "end")
        for r in epoch_window(rows):
            self.actions.insert("end", (
                f"{r.get('tick', '?'):>7} p{r.get('poll', '?'):<3} "
                f"{r.get('source', '?'):<24} {r.get('template', '?'):<14} "
                f"{_fmt_params(r.get('params') or {}):<72} "
                f"{'ok' if r.get('ok') else 'FAIL'}\n"))
        self.actions.see("end")
        self.actions.config(state="disabled")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--interval", type=int, default=1000,
                    help="poll interval ms")
    ap.add_argument("--no-topmost", action="store_true")
    ap.add_argument("--alpha", type=float, default=0.92)
    a = ap.parse_args(argv)
    Overlay(Path(a.state_dir), a.interval,
            topmost=not a.no_topmost, alpha=a.alpha).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
