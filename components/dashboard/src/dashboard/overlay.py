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
RESET_REQUEST = "brain_reset.request"
BRAIN_STATUS = "brain_status.json"
LEARN_TYPES = {"selfcheck.diagnosed", "audit.verdict",
               "improvement.promoted", "improvement.rejected",
               "episode.metrics", "cycle.completed"}
LEARN_ROWS = 8
LEARN_TAIL = 128 * 1024  # bounded tail read of events.jsonl


def write_reset_request(state_dir: Path, payload: dict | None = None) -> Path:
    """Post a brain-reset request for a --live-brain runtime (FR-1107).

    ``{}`` refreshes the active pack; ``{"pack": id}`` swaps to another
    pack under the packs dir (full state wipe, fresh-eyes reload)."""
    p = state_dir / RESET_REQUEST
    p.write_text(json.dumps(payload or {}) + "\n", encoding="utf-8")
    return p


def scan_packs(root: Path | None) -> list[str]:
    """Pack ids under ``root``: ``<dir>/pack.yaml`` -> ``<dir>`` plus flat
    ``*.yaml`` (mirrors runtime.templates.list_packs — the dashboard never
    imports runtime internals)."""
    if root is None or not root.is_dir():
        return []
    out: set[str] = set()
    for f in root.rglob("*.yaml"):
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if f.name == "pack.yaml":
            if rel.parent.parts:
                out.add(rel.parent.as_posix())
        elif not (f.parent / "pack.yaml").is_file():
            out.add(rel.with_suffix("").as_posix())
    return sorted(out)


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


def load_learning(state_dir: Path) -> list[dict]:
    """Tail events.jsonl for learning-loop envelopes (fail-open)."""
    try:
        with (state_dir / "events.jsonl").open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - LEARN_TAIL))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event_type") in LEARN_TYPES:
            out.append(e)
    return out[-LEARN_ROWS:]


def learn_line(e: dict) -> tuple[str, str]:
    """(text, tag) render of one learning-loop envelope."""
    t = e.get("event_type", "?")
    p = e.get("payload") or {}
    if t == "selfcheck.diagnosed":
        if p.get("noop"):
            return f"{p.get('cycle_id')}: self-check clean", ""
        return (f"{p.get('cycle_id')}: defect "
                f"{p.get('defect_class')} on "
                f"{','.join(p.get('affected') or [])}", "")
    if t == "audit.verdict":
        v = p.get("verdict", "?")
        return f"audit {p.get('check_id')}: {v.upper()}", \
            "" if v == "pass" else "bad"
    if t == "improvement.promoted":
        m = p.get("metrics") or {}
        return (f"MUTATION PROMOTED {p.get('candidate_id')} "
                f"score {m.get('candidate_score', 0):.3f} vs "
                f"{m.get('incumbent_score', 0):.3f}", "promo")
    if t == "improvement.rejected":
        r = "; ".join(p.get("reasons") or [])
        return (f"rejected {p.get('candidate_id')} at {p.get('gate')}"
                + (f" — {r[:64]}" if r else ""), "bad")
    if t == "episode.metrics":
        return (f"metrics {p.get('episode_id')}: refusal "
                f"{p.get('refusal_rate', 0):.0%} verify-fail "
                f"{p.get('verify_failure_rate', 0):.0%} done "
                f"{p.get('task_completion_rate', 0):.0%}", "")
    if t == "cycle.completed":
        ph = p.get("phases") or {}
        return (f"cycle {p.get('iteration')} done "
                f"(improve: {ph.get('improve', '?')})", "")
    return t, ""


class Overlay(tk.Tk):
    def __init__(self, state_dir: Path, interval_ms: int = 1000,
                 topmost: bool = True, alpha: float = 0.92,
                 packs_dir: Path | None = None,
                 pack_file: Path | None = None):
        super().__init__()
        self.state_dir = state_dir
        self.interval = interval_ms
        self.packs_dir = packs_dir
        self.pack_file = pack_file
        self.title("RimBrain agent")
        self.attributes("-topmost", topmost)
        self.attributes("-alpha", alpha)
        self.minsize(340, 240)

        bg, fg, field = "#1e1e1e", "#d4d4d4", "#252526"
        self.configure(bg=bg)
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=bg, foreground=fg,
                     fieldbackground=field, bordercolor="#3e3e42")
        st.configure("TFrame", background=bg)
        st.configure("TLabel", background=bg, foreground=fg)
        st.configure("TButton", background="#2d2d30", foreground=fg)
        st.map("TButton", background=[("active", "#3e3e42")])
        st.configure("Treeview", background=field, fieldbackground=field,
                     foreground=fg)
        st.configure("Treeview.Heading", background="#2d2d30",
                     foreground=fg)
        st.map("Treeview", background=[("selected", "#094771")])
        st.configure("Vertical.TScrollbar", background="#3e3e42",
                     troughcolor=bg, arrowcolor=fg)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(4, 0))
        self.pack_var = tk.StringVar()
        self.pack_pick = ttk.Combobox(
            bar, textvariable=self.pack_var, state="readonly",
            width=24, postcommand=self._scan_packs)
        self.pack_pick.pack(side="left")
        self._scan_packs()
        if pack_file is not None and not self.pack_var.get():
            self.pack_var.set(pack_file.stem)
        ttk.Button(bar, text="Use",
                   command=self._use_pack).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Brain Reset",
                   command=self._brain_reset).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Edit Brain",
                   command=self._edit_brain).pack(side="left", padx=(4, 0))
        self.brain_lbl = ttk.Label(bar, font=("Consolas", 9))
        self.brain_lbl.pack(side="left", padx=(8, 0))

        self.header = ttk.Label(self, font=("Consolas", 10, "bold"))
        self.header.pack(fill="x", padx=6, pady=(4, 0))

        cols = ("goal", "state", "now", "tries",
                "success condition", "blocker")
        goal_fr = ttk.Frame(self)
        goal_fr.pack(fill="both", expand=True, padx=6, pady=2)
        self.goals = ttk.Treeview(goal_fr, columns=cols, show="headings",
                                  height=5)
        widths = (150, 78, 38, 40, 260, 140)
        for c, w in zip(cols, widths):
            self.goals.heading(c, text=c)
            self.goals.column(c, width=w,
                              stretch=c in ("success condition",
                                            "blocker"))
        gsb = ttk.Scrollbar(goal_fr, orient="vertical",
                            command=self.goals.yview)
        self.goals.configure(yscrollcommand=gsb.set)
        self.goals.tag_configure("bad", foreground="#e08080")
        self.goals.tag_configure("ok", foreground="#7fd17f")
        self.goals.pack(side="left", fill="both", expand=True)
        gsb.pack(side="right", fill="y")
        # tail-follow: pinned to the last rows; scrolling up reads
        # history, returning to the bottom re-pins
        self._goals_pinned = True
        self.goals.bind("<MouseWheel>", lambda e:
                        self.after_idle(self._check_goal_pin))
        gsb.bind("<ButtonRelease-1>", lambda e:
                 self.after_idle(self._check_goal_pin))
        self.exit_lbl = ttk.Label(self, font=("Consolas", 9))
        self.exit_lbl.pack(fill="x", padx=6)

        ttk.Label(self, text="Learning", font=("Consolas", 9, "bold"),
                  anchor="w").pack(fill="x", padx=6, pady=(4, 0))
        self.learn = tk.Text(self, font=("Consolas", 9),
                             height=LEARN_ROWS, state="disabled",
                             wrap="none", bg="#101010", fg="#c8c8c8")
        self.learn.pack(fill="x", padx=6, pady=2)
        self.learn.tag_config("promo", foreground="#7fd17f")
        self.learn.tag_config("bad", foreground="#e08080")

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
        if self._changed("events.jsonl"):
            self._render_learning()
        if self._changed(BRAIN_STATUS):
            self._render_brain_status()
        self.after(self.interval, self._refresh)

    def _check_goal_pin(self):
        yv = self.goals.yview()
        self._goals_pinned = yv[1] >= 0.999 or yv == (0.0, 1.0)

    def _render_planning(self, p: dict):
        self.header.config(text=(
            f"{p.get('mode', '—')}  tick {p.get('tick', '—')}  "
            f"poll {p.get('poll', '—')}  pack {p.get('pack_revision', '—')}"
            + (f"  phase {p['phase']}" if p.get("phase") else "")
            + ("  COMPLETE" if p.get("complete") else "")))
        self.goals.delete(*self.goals.get_children())
        for g in p.get("goals") or []:
            h = g.get("holds")
            mark = "yes" if h is True else ("NO" if h is False else "—")
            st = g.get("state")
            tag = ("bad" if st in ("failed", "cancelled", "lapsed")
                   else "ok" if (h is True or st == "succeeded") else "")
            self.goals.insert("", "end", tags=(tag,) if tag else (),
                              values=(
                g.get("id"), st, mark, g.get("attempts", 0),
                g.get("effect") or g.get("detail") or "—",
                g.get("blocker") or "—"))
        if self._goals_pinned:
            self.goals.yview_moveto(1)
        exits = p.get("exit_conditions") or {}
        extra = []
        sl = p.get("select")
        if sl:
            tag = "shadow" if sl.get("shadow") else \
                ("fb" if sl.get("fallback") else "")
            extra.append(f"sel:{sl.get('applied')}"
                         + (f"({tag})" if tag else ""))
        pl = p.get("plan")
        if pl:
            extra.append(f"plan:{pl.get('id')} stale:{pl.get('stale_ticks')}")
        mv = p.get("mutation")
        if mv:
            extra.append(f"reflect:{mv.get('last_verdict') or 'idle'}"
                         f"/{mv.get('passes', 0)}")
        fv = p.get("fastevolve")
        if fv:
            extra.append(f"fe:d{fv.get('day')}"
                         f" r{fv.get('reloads_used', 0)}"
                         f"/{fv.get('max_reloads', 0)}"
                         + ("!" if fv.get("exhausted") else ""))
        self.exit_lbl.config(text=(
            "  ".join(f"[{'x' if ok else ' '}] {k}"
                     for k, ok in exits.items())
            + ("   " + "  ".join(extra) if extra else "")))

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

    def _render_learning(self):
        self.learn.config(state="normal")
        self.learn.delete("1.0", "end")
        for e in load_learning(self.state_dir):
            line, tag = learn_line(e)
            if tag:
                self.learn.insert("end", line + "\n", tag)
            else:
                self.learn.insert("end", line + "\n")
        self.learn.see("end")
        self.learn.config(state="disabled")

    def _scan_packs(self):
        ids = scan_packs(self.packs_dir)
        self.pack_pick.configure(values=ids)
        if ids and not self.pack_var.get():
            self.pack_var.set(ids[0])

    def _selected_path(self) -> Path | None:
        sel = self.pack_var.get()
        if self.packs_dir is not None and sel:
            folder = self.packs_dir / sel / "pack.yaml"
            if folder.is_file():
                return folder
            flat = self.packs_dir / f"{sel}.yaml"
            if flat.is_file():
                return flat
        return self.pack_file

    def _use_pack(self):
        sel = self.pack_var.get()
        if not sel:
            self.brain_lbl.config(text="no pack selected")
            return
        try:
            write_reset_request(self.state_dir, {"pack": sel})
            self.brain_lbl.config(text=f"swap to {sel} requested...")
        except OSError as e:
            self.brain_lbl.config(text=f"swap failed: {e}")

    def _brain_reset(self):
        try:
            write_reset_request(self.state_dir)
            self.brain_lbl.config(text="reset requested...")
        except OSError as e:
            self.brain_lbl.config(text=f"reset failed: {e}")

    def _edit_brain(self):
        path = self._selected_path()
        if path is None or not path.is_file():
            self.brain_lbl.config(text="no pack selected")
            return
        win = tk.Toplevel(self)
        win.title(f"Brain pack — {self.pack_var.get() or path.name}")
        win.geometry("760x560")
        txt = tk.Text(win, font=("Consolas", 9), wrap="none",
                      undo=True)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", path.read_text(encoding="utf-8"))
        row = ttk.Frame(win)
        row.pack(fill="x")

        def save_and_reset():
            try:
                path.write_text(txt.get("1.0", "end-1c"),
                                encoding="utf-8")
                write_reset_request(self.state_dir)
            except OSError as e:
                self.brain_lbl.config(text=f"save failed: {e}")
                return
            win.destroy()
            self.brain_lbl.config(text="saved — reset requested...")

        ttk.Button(row, text="Save & Reset",
                   command=save_and_reset).pack(side="left", padx=4, pady=4)
        ttk.Button(row, text="Cancel",
                   command=win.destroy).pack(side="left", padx=4)

    def _render_brain_status(self):
        try:
            s = json.loads((self.state_dir / BRAIN_STATUS)
                           .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if s.get("pack_id") and s["pack_id"] != self.pack_var.get():
            self.pack_var.set(s["pack_id"])  # follow the live pack
        if s.get("ok"):
            self.brain_lbl.config(
                text=f"brain ok {str(s.get('pack_revision', ''))[:8]}")
        else:
            self.brain_lbl.config(
                text=f"brain FAIL: {s.get('error', '?')[:60]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--interval", type=int, default=1000,
                    help="poll interval ms")
    ap.add_argument("--packs-dir", default=None,
                    help="packs root — enables the pack picker "
                         "(<dir>/pack.yaml folders + flat <id>.yaml)")
    ap.add_argument("--pack-file", default=None,
                    help="active pack YAML path for Edit Brain")
    ap.add_argument("--no-topmost", action="store_true")
    ap.add_argument("--alpha", type=float, default=0.92)
    a = ap.parse_args(argv)
    Overlay(Path(a.state_dir), a.interval,
            topmost=not a.no_topmost, alpha=a.alpha,
            packs_dir=Path(a.packs_dir) if a.packs_dir else None,
            pack_file=Path(a.pack_file) if a.pack_file else None
            ).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
