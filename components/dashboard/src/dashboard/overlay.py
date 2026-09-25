"""Guided launcher + agent-thought overlay (features 013/018).

One window, stacked screens — the overlay is the run supervisor
(UR-VIEW-001..004 + FR-001..024):

- Setup: declarative parameter grid (paramspec.PARAM_SPEC), pack list
  with class badges, live brain checks; GO spawns the loop child via
  the RIMBRAIN_LOOP_CMD argv prefix and swaps to Monitor.
- Monitor: tails the canonical view records — ``state/planning.json``
  (goals), ``state/decisions.jsonl`` (quick-action matrix),
  ``state/events.jsonl`` (learning) — plus loop process status and
  Stop/Restart. Flat files in, pixels out; it never touches the game.

    python -m dashboard.overlay --state-dir state          # monitor
    python -m dashboard.overlay --state-dir state --setup  # launcher menu
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import urlparse

try:
    from . import brains, gamecheck, packedit, paramspec
except ImportError:  # direct `python overlay.py`
    import brains, gamecheck, packedit, paramspec  # type: ignore[no-redef]

import yaml

_DASH_SRC = Path(__file__).resolve().parents[1]
_RUNTIME_SRC = _DASH_SRC.parents[1] / "runtime" / "src"
if str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

try:
    # Public facade only (repo boundary: dashboard never imports
    # runtime internals — same pattern as dashboard/server.py).
    from runtime import api as _ra
    _RUNTIME_OK = True
except ImportError:
    _ra = None
    _RUNTIME_OK = False

ACTION_ROWS = 60
RESET_REQUEST = "brain_reset.request"
BRAIN_STATUS = "brain_status.json"
LEARN_TYPES = {"selfcheck.diagnosed", "audit.verdict",
               "improvement.promoted", "improvement.rejected",
               "episode.metrics", "cycle.completed",
               "mutation.triggered", "mutation.proposed",
               "mutation.candidate", "mutation.noop",
               "mutation.rejected", "mutation.degraded",
               "mutation.promoted", "mutation.reverted",
               "fastevolve.day_start", "fastevolve.triggered",
               "fastevolve.anchor_missing", "fastevolve.exhausted",
               "fastevolve.promoted", "fastevolve.reloaded"}
LEARN_ROWS = 5
LEARN_TAIL = 1024 * 1024  # bounded tail read of events.jsonl

_TONE = {"ok": "#7fd17f", "warn": "#d8a860", "bad": "#e08080",
         "dim": "#808080"}


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
    return [d["id"] for d in scan_pack_descriptors(root)]


def scan_pack_descriptors(root: Path | None) -> list[dict]:
    """Pack descriptors (FR-011): id, file path, declared class
    (fail-open ``fair``), pack_id, derived_from lineage."""
    out: dict[str, dict] = {}
    if root is None or not Path(root).is_dir():
        return []
    for f in Path(root).rglob("*.yaml"):
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if rel.parts[0] == "candidates":
            continue                    # reserved for the mutation pipeline
        if f.name == "pack.yaml":
            if not rel.parent.parts:
                continue
            pid = rel.parent.as_posix()
        elif (f.parent / "pack.yaml").is_file():
            continue
        else:
            pid = rel.with_suffix("").as_posix()
        d = {"id": pid, "path": f, "class": "fair",
             "pack_id": None, "derived_from": None,
             "game_load": None}
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if isinstance(doc, dict):
                d["class"] = doc.get("class") or "fair"
                d["pack_id"] = doc.get("pack_id")
                d["derived_from"] = doc.get("derived_from")
                tmpl = ((doc.get("capabilities") or {})
                        .get("templates") or doc.get("templates") or [])
                d["game_load"] = any(
                    isinstance(t, dict)
                    and t.get("method") == "game.load" for t in tmpl)
        except (OSError, yaml.YAMLError):
            pass
        out[pid] = d
    return [out[k] for k in sorted(out)]


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
    return out


def _ev_brief(ev: dict) -> str:
    """Compact evidence summary for a mutation trigger row."""
    bits = []
    for key, label in (("tasks", "failed"), ("requeued", "requeued"),
                       ("refusals", "refused"), ("defects", "defects")):
        v = ev.get(key)
        if v:
            bits.append(f"{label}: "
                        + ",".join(str(x) for x in list(v)[:4]))
    if ev.get("blocked_polls"):
        bits.append(f"blocked {ev['blocked_polls']} polls")
    if ev.get("escalations"):
        bits.append(f"{ev['escalations']} escalations")
    if ev.get("terminal_goals"):
        bits.append(f"{ev['terminal_goals']} goals terminal")
    return "; ".join(bits)


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
    if t == "mutation.triggered":
        brief = _ev_brief(p.get("evidence") or {})
        return (f"mutate pass: {p.get('reason', '?')}"
                + (f" — {brief}" if brief else "")), ""
    if t == "mutation.proposed":
        ops = "; ".join(p.get("ops") or []) or f"{p.get('op_count')} ops"
        line = f"proposal {p.get('mutation_id')}: {ops}"
        if p.get("endpoint_error"):
            line += f" [endpoint down: {str(p['endpoint_error'])[:32]}]"
        return line, ""
    if t == "mutation.candidate":
        return f"candidate {p.get('candidate_id')}", ""
    if t == "mutation.noop":
        return f"noop: {str(p.get('rationale') or '')[:72]}", ""
    if t == "mutation.rejected":
        v = "; ".join(str(x) for x in (p.get("violations") or []))
        ops = "; ".join(p.get("ops") or [])
        return (f"rejected at {p.get('gate')}"
                + (f" — {v[:56]}" if v else "")
                + (f" [tried: {ops[:48]}]" if ops else ""), "bad")
    if t == "mutation.degraded":
        brief = _ev_brief(p.get("evidence") or {})
        detail = (f"HTTP {p['status']}" if p.get("status")
                  else str(p.get("detail") or "")[:40])
        streak = p.get("streak") or 0
        return (f"degraded ({p.get('reason')}): {brief or '?'}"
                f" — {detail} — no change"
                + (f" ×{streak}" if streak > 1 else ""), "bad")
    if t == "mutation.promoted":
        b = p.get("baseline_score")
        return (f"MUTATION PROMOTED {p.get('candidate_id')}"
                + (f" (baseline {b:.3f})" if isinstance(b, (int, float))
                   else ""), "promo")
    if t == "mutation.reverted":
        return (f"REVERTED {p.get('candidate_id')} — score "
                f"{p.get('episode_score')} vs baseline "
                f"{p.get('baseline_score')}", "bad")
    if t == "fastevolve.day_start":
        return f"day {p.get('day')} start (anchor {p.get('anchor')})", ""
    if t == "fastevolve.triggered":
        ev = p.get("evidence") or {}
        return (f"day {p.get('day')} evolve attempt {p.get('attempt')}"
                + (f" — {str(ev)[:56]}" if ev else ""), "")
    if t == "fastevolve.anchor_missing":
        return f"day {p.get('day')}: anchor missing", "bad"
    if t == "fastevolve.exhausted":
        return (f"day {p.get('day')}: retries exhausted "
                f"({p.get('attempts')})", "bad")
    if t == "fastevolve.promoted":
        return f"day {p.get('day')}: PROMOTED {p.get('candidate_id')}", "promo"
    if t == "fastevolve.reloaded":
        return (f"day {p.get('day')}: reloaded anchor "
                f"(attempt {p.get('attempt')})", "")
    return t, ""


class RunHandle:
    """The supervised loop child — one per window (data-model.md).

    ``RIMBRAIN_LOOP_CMD`` is a JSON argv prefix exported by the launcher
    (contracts/launch-cli.md); malformed/missing => GO disabled."""

    def __init__(self, environ=None):
        env = os.environ if environ is None else environ
        raw = env.get("RIMBRAIN_LOOP_CMD")
        self.loop_cmd: list[str] | None = None
        self.cmd_err: str | None = None
        if not raw:
            self.cmd_err = ("RIMBRAIN_LOOP_CMD not set — launch via "
                            "rimbrain(.exe) to enable GO")
        else:
            try:
                v = json.loads(raw)
                if isinstance(v, list) and v \
                        and all(isinstance(x, str) for x in v):
                    self.loop_cmd = [str(x) for x in v]
                else:
                    self.cmd_err = ("RIMBRAIN_LOOP_CMD is not a JSON "
                                    "string array")
            except ValueError:
                self.cmd_err = "RIMBRAIN_LOOP_CMD is not valid JSON"
        self.proc: subprocess.Popen | None = None
        self.argv: list[str] | None = None
        self.started_utc: str | None = None
        self.exit_code: int | None = None

    @property
    def available(self) -> bool:
        return self.loop_cmd is not None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> str:
        if self.proc is None:
            return "no run"
        code = self.proc.poll()
        if code is None:
            return f"running pid {self.proc.pid}"
        return f"exited code {code}"

    def spawn(self, flags: list[str]) -> None:
        if self.loop_cmd is None:
            raise RuntimeError(self.cmd_err or "loop cmd unavailable")
        self.argv = list(self.loop_cmd) + list(flags)
        self.proc = subprocess.Popen(self.argv)
        self.started_utc = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.exit_code = None

    def poll(self) -> int | None:
        if self.proc is None:
            return None
        code = self.proc.poll()
        if code is not None:
            self.exit_code = code
        return code

    def terminate(self, timeout: float = 5.0) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass


class SetupFrame(ttk.Frame):
    """Launch Configuration screen — widgets generated from
    paramspec.PARAM_SPEC (FR-002), constraint mirror live (FR-004),
    pack list with class badges (FR-011/012), brains panel
    (FR-006..009), verbatim argv preview + GO (FR-005, Principle VII).
    """

    def __init__(self, parent, app: "Overlay"):
        super().__init__(parent)
        self.app = app
        self.vars: dict[str, tk.Variable] = {}
        self._widgets: dict[str, list] = {}
        self._descriptors: list[dict] = []
        self._brain_rows: dict[str, dict] = {}
        self._game_rows: dict[str, dict] = {}
        self._checking = False
        self._suppress = False
        self._build()
        self.apply_cfg(paramspec.defaults())

    # -- construction ---------------------------------------------------

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(top, text="Preset:", font=("Consolas", 9)).pack(
            side="left")
        for name in paramspec.presets():
            ttk.Button(top, text=name, command=(
                lambda n=name: self.apply_cfg(paramspec.preset(n)))
                ).pack(side="left", padx=(4, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=6, pady=2)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_params(left)
        ttk.Label(
            left, justify="left", anchor="sw",
            font=("Consolas", 8), foreground="#808080",
            text=("run        normal play — the loop drives the colony "
                  "every poll\n"
                  "fastevolve  live play w/ retry — failed day: reflect, "
                  "evolve the pack,\n"
                  "             reload the autosave (fair only, unscored)\n"
                  "cycle      scripted save→start→combat→improve harness "
                  "(needs dev)\n"
                  "improve    evidence-only pass — diagnose + score, no "
                  "game writes\n\n"
                  "sim = fake game, deterministic, never touches the "
                  "bridge\n"
                  "live = real RimWorld via RimBridge — needs Live "
                  "confirm\n"
                  "GO runs the command previewed at the bottom; Scored "
                  "marks\n"
                  "an evaluation episode (play modes refuse it)")).pack(
            side="bottom", fill="x", pady=(4, 0))
        self._build_packs(right)
        self._build_game(right)
        self._build_brains(right)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=6, pady=(0, 4))
        self.viol_lbl = tk.Label(bottom, font=("Consolas", 9),
                                 fg="#e08080", bg="#1e1e1e",
                                 justify="left", anchor="w")
        self.viol_lbl.pack(fill="x")
        self.next_lbl = ttk.Label(bottom, font=("Consolas", 8),
                                  foreground="#808080")
        self.next_lbl.pack(fill="x")
        row = ttk.Frame(bottom)
        row.pack(fill="x", pady=(2, 0))
        self.argv_lbl = ttk.Label(row, font=("Consolas", 8),
                                  foreground="#9cf", wraplength=560,
                                  justify="left")
        self.argv_lbl.pack(side="left", fill="x", expand=True)
        self.go_btn = ttk.Button(row, text="GO", command=self._go)
        self.go_btn.pack(side="right", padx=(6, 0))

    def _build_params(self, parent):
        groups: dict[str, ttk.Frame] = {}
        for row in paramspec.PARAM_SPEC:
            g = row.get("group") or "Run"
            if g not in groups:
                groups[g] = ttk.LabelFrame(parent, text=g)
                groups[g].pack(fill="x", pady=2)
            fr = groups[g]
            flag = row["flag"]
            hint = row.get("hint", "")
            if row["kind"] == "check":
                var = tk.BooleanVar()
                rowfr = ttk.Frame(fr)
                rowfr.pack(fill="x")
                w = ttk.Checkbutton(rowfr, text=row["label"],
                                    variable=var, width=11)
                w.pack(side="left")
                if hint:
                    ttk.Label(rowfr, text=hint, font=("Consolas", 8),
                              foreground="#808080", wraplength=200,
                              justify="left").pack(
                        side="left", padx=(4, 0), fill="x", expand=True)
                self._widgets[flag] = [w]
            elif row["kind"] == "radio":
                var = tk.StringVar()
                rowfr = ttk.Frame(fr)
                rowfr.pack(fill="x")
                ttk.Label(rowfr, text=row["label"], width=12,
                          anchor="w").pack(side="left")
                ws = []
                for c in row["choices"]:
                    b = ttk.Radiobutton(rowfr, text=c, value=c,
                                        variable=var)
                    b.pack(side="left", padx=(4, 0))
                    ws.append(b)
                self._widgets[flag] = ws
                if hint:
                    ttk.Label(fr, text=hint, font=("Consolas", 8),
                              foreground="#808080", wraplength=320,
                              justify="left").pack(fill="x",
                                                   padx=(24, 0))
            else:
                var = tk.StringVar()
                rowfr = ttk.Frame(fr)
                rowfr.pack(fill="x")
                ttk.Label(rowfr, text=row["label"], width=12,
                          anchor="w").pack(side="left")
                if row["kind"] == "spin":
                    w = ttk.Spinbox(
                        rowfr, from_=row.get("min", 0),
                        to=row.get("max", 10 ** 6), width=8,
                        textvariable=var)
                    w.pack(side="left")
                elif row["kind"] == "choice":
                    w = ttk.Combobox(rowfr, textvariable=var,
                                     values=list(row["choices"]),
                                     state="readonly", width=12)
                    w.pack(side="left")
                else:
                    w = ttk.Entry(rowfr, textvariable=var, width=30)
                    w.pack(side="left", fill="x", expand=True)
                self._widgets[flag] = [w]
                if hint:
                    ttk.Label(rowfr, text=hint, font=("Consolas", 8),
                              foreground="#808080",
                              wraplength=260).pack(side="left",
                                                   padx=(6, 0))
            self.vars[flag] = var
            var.trace_add("write", lambda *_: self._recompute())

    def _build_packs(self, parent):
        fr = ttk.LabelFrame(parent, text="Pack")
        fr.pack(fill="x", pady=2)
        self.pack_list = ttk.Frame(fr)
        self.pack_list.pack(fill="x")
        brow = ttk.Frame(fr)
        brow.pack(fill="x", pady=(2, 0))
        ttk.Button(brow, text="Rescan",
                   command=self._rescan_packs).pack(side="left")
        ttk.Button(brow, text="Use (live swap)",
                   command=self._use_selected).pack(side="left",
                                                    padx=(4, 0))
        ttk.Button(brow, text="Edit Pack",
                   command=self._edit_selected).pack(side="left",
                                                     padx=(4, 0))
        self.pack_note = ttk.Label(fr, font=("Consolas", 8),
                                   foreground="#808080")
        self.pack_note.pack(fill="x")

    def _build_game(self, parent):
        """Game-surface rows: RimBridge (required), Steward add-on and
        pardeike RimBridgeServer (optional), plus a Steam launch button —
        rimbrain never starts the game itself (DLLs load at boot only,
        Workshop Harmony requires a Steam launch)."""
        fr = ttk.LabelFrame(parent, text="Game")
        fr.pack(fill="x", pady=2)
        for key, label in (("rimbridge", "RimBridge"),
                           ("steward", "Steward add-on"),
                           ("gabp", "RimBridgeServer")):
            rowfr = ttk.Frame(fr)
            rowfr.pack(fill="x", pady=1)
            dot = tk.Label(rowfr, text="●", font=("Consolas", 10),
                           bg="#1e1e1e", fg="#808080", width=2)
            dot.pack(side="left")
            ttk.Label(rowfr, text=label, width=18,
                      anchor="w").pack(side="left")
            tgt = ttk.Label(rowfr, text="—", font=("Consolas", 8),
                            anchor="w")
            tgt.pack(side="left", fill="x", expand=True)
            verdict = ttk.Label(rowfr, text="", font=("Consolas", 8),
                                anchor="e")
            verdict.pack(side="right")
            self._game_rows[key] = {"dot": dot, "target": tgt,
                                    "verdict": verdict}
        brow = ttk.Frame(fr)
        brow.pack(fill="x", pady=(2, 0))
        self.launch_btn = ttk.Button(brow, text="Launch RimWorld",
                                     command=self._launch_game)
        self.launch_btn.pack(side="left")
        ttk.Label(brow, font=("Consolas", 8), foreground="#808080",
                  text="via Steam — Workshop mods need it").pack(
                      side="left", padx=(6, 0))

    def _launch_game(self):
        """Start RimWorld through the Steam URI handler so Workshop
        Harmony loads (direct exe launch skips Workshop mods)."""
        row = self._game_rows.get("rimbridge") or {}
        try:
            os.startfile("steam://rungameid/294100")       # win32
        except (AttributeError, OSError):
            webbrowser.open("steam://rungameid/294100")
        if row:
            row["verdict"].config(text="launching…")
        self._await_bridge()

    _bridge_up = False

    def _await_bridge(self, attempts=24):
        """Re-probe while the game boots — a modded RimWorld takes a
        while to bring the bridge up."""
        self._check_game()
        if not self._bridge_up and attempts > 0:
            self.after(10000, lambda: self._await_bridge(attempts - 1))

    def _check_game(self):
        """Worker-thread game-surface probe; posts ('game', status) onto
        the shared brains queue."""
        url = self.vars["bridge"].get() or "http://127.0.0.1:8765"

        def work():
            self.app._brain_q.put(
                ("game", gamecheck.bridge_status(url)))
        threading.Thread(target=work, daemon=True).start()

    def _render_game(self, res: dict):
        tones = {"rimbridge": ("ok", "bad"), "steward": ("ok", "warn"),
                 "gabp": ("ok", "dim")}
        for key, (up, down) in tones.items():
            row = self._game_rows.get(key)
            part = res.get(key) or {}
            if row is None or not part:
                continue
            ok = bool(part.get("ok"))
            row["dot"].config(fg=_TONE[up if ok else down])
            row["target"].config(text=part.get("detail", "—"))
            row["verdict"].config(text="ok" if ok else "check")
        self._bridge_up = bool(res.get("ok"))
        self.launch_btn.state(
            ["disabled"] if self._bridge_up else ["!disabled"])

    def _build_brains(self, parent):
        fr = ttk.LabelFrame(parent, text="Brains")
        fr.pack(fill="both", expand=True, pady=2)
        serve_map = self._serve_map()
        for label, role, tier in brains.ROLES:
            rowfr = ttk.Frame(fr)
            rowfr.pack(fill="x", pady=1)
            dot = tk.Label(rowfr, text="●", font=("Consolas", 10),
                           bg="#1e1e1e", fg="#808080", width=2)
            dot.pack(side="left")
            ttk.Label(rowfr, text=f"{tier} {label}", width=18,
                      anchor="w").pack(side="left")
            tgt = ttk.Label(rowfr, text="—", font=("Consolas", 8),
                            anchor="w")
            tgt.pack(side="left", fill="x", expand=True)
            verdict = ttk.Label(rowfr, text="", font=("Consolas", 8),
                                anchor="e")
            verdict.pack(side="right")
            row = {"dot": dot, "target": tgt,
                   "verdict": verdict}
            if role in serve_map:
                row["serve_ep"] = serve_map[role]
                row["serve_btn"] = ttk.Button(
                    rowfr, text="Start", width=6,
                    command=lambda r=role: self._start_brain(r))
                row["serve_btn"].pack(side="right", padx=(0, 4))
            self._brain_rows[role] = row
            fb = ttk.Label(fr, text="", font=("Consolas", 8),
                           foreground="#606060", anchor="w")
            fb.pack(fill="x", padx=(24, 0))
            row["fb"] = fb
        ttk.Button(fr, text="Re-check",
                   command=self.recheck).pack(anchor="e", pady=2)
        if not _RUNTIME_OK:
            for r in self._brain_rows.values():
                r["target"].config(text="runtime unavailable")
                r["verdict"].config(text="")

    # -- state -----------------------------------------------------------

    def apply_cfg(self, cfg: dict):
        self._suppress = True
        try:
            for flag, var in self.vars.items():
                if flag in cfg:
                    var.set(cfg[flag])
        finally:
            self._suppress = False
        self._rescan_packs()
        self._recompute()

    def collect(self) -> dict:
        cfg = {}
        for row in paramspec.PARAM_SPEC:
            flag = row["flag"]
            v = self.vars[flag].get()
            if row["kind"] == "check":
                cfg[flag] = bool(v)
            elif row["kind"] == "spin":
                try:
                    cfg[flag] = int(v)
                except (TypeError, ValueError):
                    cfg[flag] = row["default"]
            else:
                cfg[flag] = v
        return cfg

    def _descriptor(self, pack_id: str) -> dict | None:
        return next((d for d in self._descriptors
                     if d["id"] == pack_id), None)

    def _rescan_packs(self):
        self._descriptors = scan_pack_descriptors(self.app.packs_dir)
        for w in self.pack_list.winfo_children():
            w.destroy()
        var = self.vars["pack"]
        ids = [d["id"] for d in self._descriptors]
        for row in paramspec.PARAM_SPEC:
            if row["flag"] == "pack":
                for w in self._widgets["pack"]:
                    w.configure(values=ids)
        cfg = self.collect()
        for d in self._descriptors:
            text = d["id"] + f"  [{d['class']}]"
            if d.get("derived_from"):
                text += f"  (from {d['derived_from']})"
            rb = ttk.Radiobutton(self.pack_list, text=text, value=d["id"],
                                 variable=var)
            rb.pack(anchor="w")
            if cfg.get("fair") and d["class"] == "dev":
                rb.state(["disabled"])
        if ids and var.get() not in ids:
            var.set(ids[0])

    # -- recompute / go ----------------------------------------------------

    def _recompute(self):
        if self._suppress:
            return
        cfg = self.collect()
        d = self._descriptor(cfg.get("pack", ""))
        probs = paramspec.violations(cfg, pack_class=(d or {}).get("class"),
                              pack_game_load=(d or {}).get("game_load"))
        running = self.app.runner.running
        for row in paramspec.PARAM_SPEC:
            ok = paramspec.enabled(row, cfg) and not running
            for w in self._widgets[row["flag"]]:
                try:
                    w.state(["!disabled"] if ok else ["disabled"])
                except tk.TclError:
                    pass
        self.viol_lbl.config(text="\n".join(probs))
        av = paramspec.argv(cfg)
        cmd = (self.app.runner.loop_cmd or ["<loop>"]) + av
        self.argv_lbl.config(text=" ".join(cmd))
        if running:
            self.next_lbl.config(
                text="run live — parameters apply to next run")
        elif not self.app.runner.available:
            self.next_lbl.config(text=self.app.runner.cmd_err or "")
        else:
            self.next_lbl.config(text="")
        if not self.app.runner.available or probs:
            self.go_btn.state(["disabled"])
        else:
            self.go_btn.state(["!disabled"])
        self.go_btn.config(text="Restart run" if running else "GO")
        if running:  # GO doubles as the FR-023 restart path
            self.go_btn.state(["!disabled"] if not probs else ["disabled"])

    def _go(self):
        cfg = self.collect()
        d = self._descriptor(cfg.get("pack", ""))
        probs = paramspec.violations(cfg, pack_class=(d or {}).get("class"),
                              pack_game_load=(d or {}).get("game_load"))
        if probs:
            return
        if self.app.runner.running:
            if not messagebox.askyesno(
                    "Restart run",
                    "Restart the loop with these parameters?\n\n"
                    + " ".join(paramspec.argv(cfg)), parent=self):
                return
            self.app.runner.terminate()
        try:
            self.app.runner.spawn(paramspec.argv(cfg))
        except (OSError, RuntimeError) as e:
            self.next_lbl.config(text=f"spawn failed: {e}")
            return
        self.app.show("monitor")

    # -- brains ------------------------------------------------------------

    def on_show(self):
        self._rescan_packs()
        self._recompute()
        if not self._brain_checked:
            self.recheck()

    _brain_checked = False

    def recheck(self):
        if not _RUNTIME_OK or self._checking:
            return
        self._checking = True
        self._brain_checked = True
        for r in self._brain_rows.values():
            r["dot"].config(fg="#808080")
            r["verdict"].config(text="checking…")
        brains.check_all(_ra, self.app._brain_q)
        self._check_game()

    def drain_brains(self):
        while True:
            try:
                role, res = self.app._brain_q.get_nowait()
            except queue.Empty:
                break
            self._checking = False
            if role == "game":
                self._render_game(res)
                continue
            row = self._brain_rows.get(role)
            if row is None:
                continue
            m = brains.row_model(res)
            row["dot"].config(fg=_TONE.get(m["tone"], "#808080"))
            row["target"].config(text=m["target"])
            row["verdict"].config(text=m["text"])
            row["fb"].config(text=(
                "fallbacks: " + " → ".join(m["fallbacks"]))
                if m["fallbacks"] else "")
            btn = row.get("serve_btn")
            if btn is not None:
                btn.state(["disabled"] if m["verdict"] == "answered"
                          else ["!disabled"])

    def _serve_map(self) -> dict:
        """role -> endpoint entry for roles whose bound endpoint is
        locally launchable (declares serve.cmd and the exe exists)."""
        out = {}
        if not _RUNTIME_OK:
            return out
        try:
            binds = _ra.list_bindings().get("bindings") or {}
            eps = {e.get("id"): e for e
                   in (_ra.list_endpoints().get("endpoints") or [])}
        except Exception:
            return out
        for _l, role, _t in brains.ROLES:
            ep = eps.get((binds.get(role) or {}).get("endpoint"))
            if ep and brains.serve_cmd(ep):
                out[role] = ep
        return out

    def _start_brain(self, role):
        """Spawn the endpoint's local server in its own console, then
        re-check once it has had time to load the model. Never spawns a
        second instance — a port that already accepts means a server
        (ours or a manually started one) is live."""
        row = self._brain_rows.get(role) or {}
        ep = row.get("serve_ep") or {}
        cmd = brains.serve_cmd(ep)
        if not cmd:
            return
        if self._port_open(ep):
            row["verdict"].config(text="already running")
            self.recheck()
            return
        pending = getattr(self, "_serve_pending", None)
        if pending is None:
            pending = self._serve_pending = set()
        if role in pending:
            row["verdict"].config(text="starting…")
            return                              # spawn already in flight
        pending.add(role)
        env = dict(os.environ)
        pre = [str(p) for p
               in (ep.get("serve") or {}).get("path_prepend") or []]
        if pre:
            env["PATH"] = os.pathsep.join(pre) + os.pathsep \
                + env.get("PATH", "")
        try:
            subprocess.Popen(
                cmd, env=env, creationflags=getattr(
                    subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as e:
            pending.discard(role)
            row["verdict"].config(text="start failed")
            messagebox.showerror(
                "Start server",
                f"Could not launch:\n{' '.join(cmd)}\n\n{e}",
                parent=self)
            return
        row["verdict"].config(text="starting…")
        self._await_server(role)

    @staticmethod
    def _port_open(ep: dict) -> bool:
        """True when the endpoint's host:port already accepts TCP."""
        try:
            u = urlparse(ep.get("base_url", ""))
            socket.create_connection(
                (u.hostname or "127.0.0.1", u.port or 80),
                timeout=1).close()
            return True
        except OSError:
            return False

    def _await_server(self, role, attempts=30):
        """Watch the spawned server's port; re-check the brains the
        moment it accepts (model load can take ~90s — up to ~2.5min)."""
        row = self._brain_rows.get(role) or {}
        ep = row.get("serve_ep") or {}
        if not self._port_open(ep):
            if attempts > 0:
                self.after(5000, lambda: self._await_server(
                    role, attempts - 1))
            else:
                (getattr(self, "_serve_pending", set())
                 or set()).discard(role)
            return
        (getattr(self, "_serve_pending", set()) or set()).discard(role)
        self.recheck()

    # -- pack actions -------------------------------------------------------

    def _use_selected(self):
        sel = self.vars["pack"].get()
        if not sel:
            return
        try:
            write_reset_request(self.app.state_dir, {"pack": sel})
            self.pack_note.config(text=f"swap to {sel} requested…")
        except OSError as e:
            self.pack_note.config(text=f"swap failed: {e}")

    def _edit_selected(self):
        d = self._descriptor(self.vars["pack"].get())
        path = (d or {}).get("path") or self.app.pack_file
        if path is None or not Path(path).is_file():
            self.pack_note.config(text="no pack selected")
            return
        PackEditor(self.app, Path(path), self.vars["pack"].get(),
                   on_saved=lambda p: self._pack_saved(p))

    def _pack_saved(self, path: Path):
        self._rescan_packs()
        nid = packedit.source_id(path)
        self.vars["pack"].set(nid)
        self.pack_note.config(text=f"saved {nid}")


class PackEditor(tk.Toplevel):
    """Guided pack editor (US4): outline tree -> typed forms; predicate
    builder, template dropdown + schema-generated params; Raw YAML tab
    retained (FR-020); save-as-new via api.validate_pack_doc (FR-018/019).
    """

    def __init__(self, app: "Overlay", path: Path, pack_id: str,
                 on_saved=None):
        super().__init__(app)
        self.app = app
        self.path = path
        self.on_saved = on_saved
        self.doc = packedit.load_doc(path)
        self.source = packedit.source_id(path, app.packs_dir)
        self.dirty = False
        self.title(f"Pack editor — {pack_id}")
        self.geometry("900x620")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        guided = ttk.Frame(nb)
        nb.add(guided, text="Guided")
        raw = ttk.Frame(nb)
        nb.add(raw, text="Raw YAML")

        paned = ttk.Panedwindow(guided, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, width=240)
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self.tree = ttk.Treeview(left, show="tree")
        self.tree.pack(fill="both", expand=True)
        self._nodes: dict[str, dict] = {}
        self._fill_outline()
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._tree_nav)

        self.form = ttk.Frame(right)
        self.form.pack(fill="both", expand=True)
        self.form_title = ttk.Label(right, font=("Consolas", 10, "bold"))
        self.form_title.pack(fill="x", before=self.form)
        self.form_hint = ttk.Label(right, font=("Consolas", 8),
                                   foreground="#808080",
                                   wraplength=560, justify="left")
        self.form_hint.pack(fill="x", before=self.form)
        self._form_stack: list[dict] = []

        bar = ttk.Frame(guided)
        bar.pack(fill="x")
        ttk.Button(bar, text="Save as new pack…",
                   command=self._save_new).pack(side="left",
                                                padx=4, pady=4)
        ttk.Button(bar, text="Close",
                   command=self.destroy).pack(side="right",
                                              padx=4, pady=4)
        self.status = ttk.Label(bar, font=("Consolas", 8),
                                foreground="#e08080")
        self.status.pack(side="left", padx=8)

        self.raw = tk.Text(raw, font=("Consolas", 9), wrap="none",
                           undo=True)
        self.raw.pack(fill="both", expand=True)
        self.raw.insert("1.0", path.read_text(encoding="utf-8"))
        rbar = ttk.Frame(raw)
        rbar.pack(fill="x")
        ttk.Button(rbar, text="Save in place + reset",
                   command=self._save_raw).pack(side="left",
                                                padx=4, pady=4)

    # -- outline ---------------------------------------------------------

    def _fill_outline(self):
        def add(parent, node):
            self.tree.insert(parent, "end", iid=node["id"],
                             text=node["label"])
            self._nodes[node["id"]] = node
            for c in node["children"]:
                add(node["id"], c)
        for n in packedit.build_outline(self.doc):
            add("", n)

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if sel:
            self._open_node(self._nodes[sel[0]])

    def _tree_nav(self, _e):
        pass  # expand/collapse default

    # -- form dispatch -----------------------------------------------------

    def _node_value(self, node):
        if node["path"] is None:
            return None
        return packedit.get_path(self.doc, node["path"])

    def _open_node(self, node):
        self._form_stack = []
        self._render(node)

    def _render(self, node, sub=None):
        for w in self.form.winfo_children():
            w.destroy()
        target = self.doc if node["path"] is None else \
            packedit.get_path(self.doc, node["path"])
        if sub is not None:
            target = sub
        self._current = (node, target)
        self.form_title.config(text=node["label"])
        if node["id"] == "meta":
            self._dict_form(node, {k: self.doc.get(k)
                                   for k in packedit._META_KEYS
                                   if k in self.doc},
                          prefix="")
            return
        if target is None:
            ttk.Label(self.form, text="(absent in this pack)").pack(
                anchor="w")
            return
        self._value_form(node, target, node["path"] or "",
                         self._set_node_value)

    def _set_node_value(self, path, value):
        packedit.set_path(self.doc, path, value)
        self.dirty = True

    def _value_form(self, node, value, path, setter):
        if packedit.is_pred(value):
            self._pred_form(self.form, value)
        elif packedit.is_steps(value):
            self._steps_form(value)
        elif isinstance(value, dict):
            self._dict_form(node, value, prefix=path)
        elif isinstance(value, list):
            self._list_form(value, path)
        else:
            self._scalar_form(node, value, path, setter)

    # -- scalar / dict ------------------------------------------------------

    def _entry(self, parent, get, set_, width=40, assist=False):
        var = tk.StringVar(value="" if get() is None else str(get()))
        fr = ttk.Frame(parent)
        fr.pack(fill="x")
        e = ttk.Entry(fr, textvariable=var, width=width)
        e.pack(side="left", fill="x", expand=True)

        def commit(*_):
            set_(var.get())
            self.dirty = True
        var.trace_add("write", commit)
        if assist:
            vocab = self._vocab()
            if vocab:
                ins = ttk.Combobox(fr, values=vocab, width=16,
                                   state="readonly")
                ins.pack(side="left", padx=(4, 0))
                ins.bind("<<ComboboxSelected>>", lambda _e: (
                    var.set(var.get() + ins.get()), ins.set("")))
        return var

    def _vocab(self) -> list[str]:
        if not _RUNTIME_OK:
            return []  # freeform only — never a copied table
        try:
            v = _ra.policy_vocabulary()
            return (["@fn:" + f for f in v.get("functions", [])]
                    + v.get("resolvers", []) + v.get("ops", []))
        except Exception:
            return []

    def _scalar_form(self, node, value, path, setter):
        fr = self.form
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            ttk.Checkbutton(fr, text="value", variable=var,
                            command=lambda: (
                                setter(path, bool(var.get())),
                                setattr(self, "dirty", True))
                            ).pack(anchor="w")
        elif isinstance(value, (int, float)):
            self._entry(fr, lambda: value,
                        lambda s: self._num_set(setter, path, s,
                                                float if isinstance(
                                                    value, float)
                                                else int))
        else:
            self._entry(fr, lambda: value,
                        lambda s: setter(path, s), assist=True)

    def _num_set(self, setter, path, s, cast):
        try:
            setter(path, cast(s))
        except (TypeError, ValueError):
            pass

    def _dict_form(self, node, d: dict, prefix: str):
        for k, v in d.items():
            rowfr = ttk.Frame(self.form)
            rowfr.pack(fill="x", pady=1)
            ttk.Label(rowfr, text=k, width=22, anchor="w").pack(
                side="left")
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, bool):
                var = tk.BooleanVar(value=v)
                ttk.Checkbutton(rowfr, variable=var, command=(
                    lambda p=path, vv=var: (
                        self._set_node_value(p, bool(vv.get())),
                    ))).pack(side="left")
            elif isinstance(v, (int, float)):
                self._entry(rowfr, lambda v=v: v,
                            lambda s, p=path, t=type(v):
                            self._num_set(self._set_node_value, p, s, t),
                            width=12)
            elif isinstance(v, (dict, list)):
                ttk.Button(rowfr, text="edit ▸",
                           command=lambda p=path, l=k: self._push(
                               l, p)).pack(side="left")
            else:
                self._entry(rowfr, lambda v=v: "" if v is None else v,
                            lambda s, p=path: self._set_node_value(p, s),
                            assist=isinstance(v, str) and "@" in str(v))

    def _push(self, label, path):
        """Drill into a nested dict/list as a subform."""
        self._form_stack.append(self._current)
        value = packedit.get_path(self.doc, path)
        node = {"id": f"sub.{path}", "label": label, "path": path}
        for w in self.form.winfo_children():
            w.destroy()
        back = ttk.Frame(self.form)
        back.pack(fill="x")
        ttk.Button(back, text="‹ back",
                   command=self._pop).pack(side="left")
        self._current = (node, value)
        self.form_title.config(text=label)
        self._value_form(node, value, path, self._set_node_value)

    def _pop(self):
        if not self._form_stack:
            return
        node, _target = self._form_stack.pop()
        self._render(node)

    # -- predicate builder ----------------------------------------------------

    def _pred_form(self, parent, pred: dict, path=""):
        fr = ttk.Frame(parent)
        fr.pack(fill="x", padx=(8 if path else 0, 0, 0, 0))
        for comb in ("all", "any"):
            if comb in pred:
                ttk.Label(fr, text=f"{comb}:").pack(anchor="w")
                for i, sub in enumerate(pred[comb] or []):
                    self._pred_form(fr, sub, f"{path}.{comb}.{i}")
                return
        if "not" in pred:
            ttk.Label(fr, text="not:").pack(anchor="w")
            self._pred_form(fr, pred["not"], f"{path}.not")
            return
        # leaf: field + op + value
        rowfr = ttk.Frame(fr)
        rowfr.pack(fill="x")
        fv = tk.StringVar(value=str(pred.get("field", "")))
        ttk.Entry(rowfr, textvariable=fv, width=26).pack(side="left")
        ops = self._ops()
        ov = tk.StringVar(value=str(pred.get("op", "")))
        oc = ttk.Combobox(rowfr, textvariable=ov, values=ops,
                          width=10, state="readonly" if ops else "normal")
        oc.pack(side="left", padx=4)
        vv = tk.StringVar(value=json.dumps(pred.get("value"),
                                           default=str))
        ttk.Entry(rowfr, textvariable=vv, width=20).pack(side="left")
        for v in (fv, ov, vv):
            v.trace_add("write", lambda *_: self._pred_commit(
                pred, fv.get(), ov.get(), vv.get()))

    def _ops(self) -> list[str]:
        if not _RUNTIME_OK:
            return []
        try:
            return _ra.policy_vocabulary().get("ops", [])
        except Exception:
            return []

    def _pred_commit(self, pred, field, op, raw_value):
        pred["field"] = field
        pred["op"] = op
        try:
            pred["value"] = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            pred["value"] = raw_value
        self.dirty = True

    # -- steps editor ---------------------------------------------------------

    def _steps_form(self, steps: list):
        templates = self._templates()
        head = ttk.Frame(self.form)
        head.pack(fill="x")
        ttk.Button(head, text="+ step",
                   command=lambda: (steps.append({"template": "",
                                                  "params": {}}),
                                    setattr(self, "dirty", True),
                                    self._rerender())).pack(side="left")
        for i, st in enumerate(steps):
            fr = ttk.LabelFrame(self.form, text=f"step {i}")
            fr.pack(fill="x", pady=2)
            row = ttk.Frame(fr)
            row.pack(fill="x")
            tv = tk.StringVar(value=st.get("template", ""))
            cb = ttk.Combobox(row, textvariable=tv,
                              values=[t.get("id", "") for t in templates],
                              state="readonly" if templates
                              else "normal", width=22)
            cb.pack(side="left")
            ttk.Button(row, text="↑", width=2,
                       command=lambda i=i: self._move(steps, i, -1)
                       ).pack(side="left")
            ttk.Button(row, text="↓", width=2,
                       command=lambda i=i: self._move(steps, i, 1)
                       ).pack(side="left")
            ttk.Button(row, text="✕", width=2,
                       command=lambda i=i: (steps.pop(i),
                                            setattr(self, "dirty", True),
                                            self._rerender())
                       ).pack(side="left")
            desc = next((t.get("description") for t in templates
                         if t.get("id") == st.get("template")), None)
            if desc:
                ttk.Label(fr, text=desc, font=("Consolas", 8),
                          foreground="#808080",
                          wraplength=520).pack(anchor="w")
            tv.trace_add("write", lambda *_, i=i, v=tv: (
                steps[i].__setitem__("template", v.get()),
                setattr(self, "dirty", True), self._rerender()))
            params_fr = ttk.Frame(fr)
            params_fr.pack(fill="x", padx=(8, 0))
            self._params_form(params_fr, st, st.get("template"),
                              templates)

    def _params_form(self, parent, step: dict, tid, templates):
        schema = next((t.get("params_schema") for t in templates
                       if t.get("id") == tid), None) or {}
        props = schema.get("properties") or {}
        params = step.setdefault("params", {})
        for name in list(props) + [k for k in params if k not in props]:
            row = ttk.Frame(parent)
            row.pack(fill="x")
            ttk.Label(row, text=name, width=18, anchor="w").pack(
                side="left")
            cur = params.get(name)
            pv = tk.StringVar(value="" if cur is None else
                              json.dumps(cur, default=str))
            ttk.Entry(row, textvariable=pv, width=28).pack(side="left")
            pv.trace_add("write", lambda *_, p=name, v=pv: (
                self._param_set(step, p, v.get())))
            hint = (props.get(name) or {}).get("description") or \
                (props.get(name) or {}).get("type", "")
            if hint:
                ttk.Label(row, text=hint, font=("Consolas", 8),
                          foreground="#606060").pack(side="left",
                                                     padx=(6, 0))

    def _param_set(self, step, name, raw):
        try:
            step["params"][name] = yaml.safe_load(raw)
        except yaml.YAMLError:
            step["params"][name] = raw
        self.dirty = True

    def _move(self, steps, i, d):
        j = i + d
        if 0 <= j < len(steps):
            steps[i], steps[j] = steps[j], steps[i]
            self.dirty = True
            self._rerender()

    def _rerender(self):
        node, _t = self._current
        self._render(node)

    def _templates(self) -> list:
        caps = (self.doc.get("capabilities") or {}).get("templates") \
            or self.doc.get("templates") or []
        return [t for t in caps if isinstance(t, dict)]

    # -- generic list editor ----------------------------------------------------

    def _list_form(self, lst: list, path: str):
        head = ttk.Frame(self.form)
        head.pack(fill="x")
        lb = tk.Listbox(head, height=8, bg="#252526", fg="#d4d4d4")
        lb.pack(side="left", fill="x", expand=True)
        for i, item in enumerate(lst):
            label = (item.get("id") or item.get("template")
                     or item.get("name") or f"item {i}") \
                if isinstance(item, dict) else str(item)[:40]
            lb.insert("end", label)
        btns = ttk.Frame(head)
        btns.pack(side="left", padx=4)
        ttk.Button(btns, text="edit", command=lambda: self._list_edit(
            lst, lb.curselection(), path)).pack()
        ttk.Button(btns, text="del", command=lambda: self._list_del(
            lst, lb)).pack()

    def _list_edit(self, lst, sel, path):
        if not sel:
            return
        i = sel[0]
        node = {"id": f"{path}.{i}", "label": f"{path} › {i}",
                "path": None}
        self._form_stack.append(self._current)
        for w in self.form.winfo_children():
            w.destroy()
        back = ttk.Frame(self.form)
        back.pack(fill="x")
        ttk.Button(back, text="‹ back",
                   command=self._pop).pack(side="left")
        item = lst[i]
        self._current = (node, item)
        self.form_title.config(text=node["label"])
        if isinstance(item, dict):
            for k, v in item.items():
                rowfr = ttk.Frame(self.form)
                rowfr.pack(fill="x", pady=1)
                ttk.Label(rowfr, text=k, width=18, anchor="w").pack(
                    side="left")
                if isinstance(v, (dict, list)) and packedit.is_pred(v):
                    self._pred_form(rowfr, v, k)
                elif isinstance(v, (dict, list)):
                    ttk.Button(rowfr, text="edit ▸", command=(
                        lambda kk=k: self._push_item(item, kk))
                        ).pack(side="left")
                elif isinstance(v, bool):
                    bv = tk.BooleanVar(value=v)
                    ttk.Checkbutton(rowfr, variable=bv, command=(
                        lambda kk=k, vv=bv: (
                            item.__setitem__(kk, bool(vv.get())),
                            setattr(self, "dirty", True)))
                        ).pack(side="left")
                else:
                    self._entry(rowfr, lambda v=v: v,
                                lambda s, kk=k: (
                                    item.__setitem__(kk, s),
                                    setattr(self, "dirty", True)),
                                assist=isinstance(v, str)
                                and "@" in str(v))

    def _push_item(self, item, key):
        node = {"id": f"item.{key}", "label": key, "path": None}
        self._form_stack.append(self._current)
        for w in self.form.winfo_children():
            w.destroy()
        back = ttk.Frame(self.form)
        back.pack(fill="x")
        ttk.Button(back, text="‹ back",
                   command=self._pop).pack(side="left")
        v = item[key]
        self._current = (node, v)
        self.form_title.config(text=key)
        if packedit.is_pred(v):
            self._pred_form(self.form, v)
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                rowfr = ttk.Frame(self.form)
                rowfr.pack(fill="x", pady=1)
                ttk.Label(rowfr, text=k2, width=18, anchor="w").pack(
                    side="left")
                self._entry(rowfr, lambda v2=v2: v2,
                            lambda s, kk=k2: (
                                v.__setitem__(kk, s),
                                setattr(self, "dirty", True)),
                            assist=isinstance(v2, str)
                            and "@" in str(v2))

    def _list_del(self, lst, lb):
        sel = lb.curselection()
        if sel:
            lst.pop(sel[0])
            self.dirty = True
            self._rerender()

    # -- save -----------------------------------------------------------------

    def _save_new(self):
        if not _RUNTIME_OK:
            self.status.config(
                text="runtime facade unavailable — validation blocked")
            return
        name = simpledialog.askstring(
            "Save as new pack", "pack name (a-z 0-9 -):",
            initialvalue=f"{self.source}-custom", parent=self)
        if name is None:
            return
        name = name.strip()
        prob = packedit.save_name_problem(name, self.app.packs_dir)
        if prob == "exists":
            active = packedit.active_pack_id(self.app.state_dir)
            if active == name:
                if not messagebox.askyesno(
                        "Overwrite live pack",
                        f"'{name}' is the running pack — overwriting "
                        "hot-swaps the live brain. Continue?",
                        parent=self):
                    return
                self._write(name)
                write_reset_request(self.app.state_dir)
                self.status.config(text="overwrote live pack — "
                                        "reset posted")
                return
            if not messagebox.askyesno(
                    "Pack exists",
                    f"'{name}' exists — overwrite it?", parent=self):
                return
        elif prob:
            self.status.config(text=prob)
            return
        self._write(name)

    def _write(self, name):
        res = _ra.validate_pack_doc(self.doc)
        if not res.get("ok"):
            self.status.config(text="blocked: "
                               + "; ".join(res.get("issues") or
                                           ["invalid"])[:160])
            return
        try:
            path = packedit.save_as_new(self.doc, name, self.source,
                                        self.app.packs_dir)
        except (OSError, ValueError) as e:
            self.status.config(text=f"save failed: {e}")
            return
        self.dirty = False
        self.status.config(text=f"saved {name}")
        if callable(self.on_saved):
            self.on_saved(path)

    def _save_raw(self):
        """Raw YAML tab: direct in-place write + reset when the pack is
        active (pre-existing Edit Brain semantics, FR-020)."""
        try:
            self.path.write_text(self.raw.get("1.0", "end-1c"),
                                 encoding="utf-8")
        except OSError as e:
            self.status.config(text=f"save failed: {e}")
            return
        if packedit.active_pack_id(self.app.state_dir) == self.source:
            try:
                write_reset_request(self.app.state_dir)
            except OSError:
                pass
        self.status.config(text="saved in place")


class Overlay(tk.Tk):
    def __init__(self, state_dir: Path, interval_ms: int = 1000,
                 topmost: bool = True, alpha: float = 0.92,
                 packs_dir: Path | None = None,
                 pack_file: Path | None = None,
                 setup: bool = False):
        super().__init__()
        self.state_dir = state_dir
        self.interval = interval_ms
        self.packs_dir = packs_dir
        self.pack_file = pack_file
        self.runner = RunHandle()
        self._brain_q: queue.Queue = queue.Queue()
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
        st.configure("TLabelframe", background=bg, foreground=fg)
        st.configure("TLabelframe.Label", background=bg, foreground=fg)
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

        self._host = ttk.Frame(self)
        self._host.pack(fill="both", expand=True)
        self._monitor = ttk.Frame(self._host)
        self._build_monitor()
        self._setup = SetupFrame(self._host, self)
        self._screen = None
        self.show("setup" if setup else "monitor")

        self._mtimes: dict[str, float] = {}
        self._was_running = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, self._refresh)

    # -- screens -----------------------------------------------------------

    def show(self, name: str):
        if self._screen == name:
            return
        self._screen = name
        for f in (self._monitor, self._setup):
            f.pack_forget()
        f = self._setup if name == "setup" else self._monitor
        f.pack(fill="both", expand=True)
        if name == "setup":
            self._setup.on_show()

    def _build_monitor(self):
        m = self._monitor
        row = ttk.Frame(m)
        row.pack(fill="x", padx=6, pady=(4, 0))
        self.run_lbl = ttk.Label(row, text="no run",
                                 font=("Consolas", 9, "bold"))
        self.run_lbl.pack(side="left")
        ttk.Button(row, text="Setup",
                   command=lambda: self.show("setup")).pack(side="right")
        ttk.Button(row, text="Restart",
                   command=self._restart).pack(side="right", padx=(0, 4))
        ttk.Button(row, text="Stop",
                   command=self._stop).pack(side="right", padx=(0, 4))

        self.header = ttk.Label(m, font=("Consolas", 10, "bold"))
        self.header.pack(fill="x", padx=6, pady=(4, 0))

        cols = ("goal", "state", "now", "tries",
                "success condition", "blocker")
        goal_fr = ttk.Frame(m)
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
        self.exit_lbl = ttk.Label(m, font=("Consolas", 9))
        self.exit_lbl.pack(fill="x", padx=6)

        ttk.Label(m, text="Learning", font=("Consolas", 9, "bold"),
                  anchor="w").pack(fill="x", padx=6, pady=(4, 0))
        lf = ttk.Frame(m)
        lf.pack(fill="x", padx=6, pady=2)
        self.learn = tk.Text(lf, font=("Consolas", 9),
                             height=LEARN_ROWS, state="disabled",
                             wrap="none", bg="#101010", fg="#c8c8c8")
        self.learn.pack(side="left", fill="x", expand=True)
        lsb = ttk.Scrollbar(lf, orient="vertical",
                            command=self.learn.yview)
        self.learn.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.learn.tag_config("promo", foreground="#7fd17f")
        self.learn.tag_config("bad", foreground="#e08080")

        self.actions = tk.Text(m, font=("Consolas", 9), height=14,
                               state="disabled", wrap="none",
                               bg="#101010", fg="#c8c8c8")
        self.actions.pack(fill="both", expand=True, padx=6, pady=4)

    # -- lifecycle ---------------------------------------------------------

    def _stop(self):
        self.runner.terminate()
        self._setup._recompute()

    def _restart(self):
        if self.runner.running:
            if not messagebox.askyesno(
                    "Restart run", "Stop the current run and return to "
                    "Setup to launch with new parameters?", parent=self):
                return
            self.runner.terminate()
        self.show("setup")

    def _on_close(self):
        self.runner.terminate()
        self.destroy()

    # -- refresh -----------------------------------------------------------

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
        self.runner.poll()
        self.run_lbl.config(text=self.runner.status())
        running = self.runner.running
        if running != self._was_running:  # run start/stop flips
            self._was_running = running   # argv editability (FR-022)
            self._setup._recompute()
        self._setup.drain_brains()
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
        PackEditor(self, path, self.pack_var.get() or path.stem,
                   on_saved=lambda p: self._pack_saved(p))

    def _pack_saved(self, path: Path):
        self._scan_packs()
        self.pack_var.set(packedit.source_id(path))
        self._setup._rescan_packs()

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
    ap.add_argument("--setup", action="store_true",
                    help="open on the launcher Setup screen (the window "
                         "then owns the loop child via RIMBRAIN_LOOP_CMD)")
    ap.add_argument("--no-topmost", action="store_true")
    ap.add_argument("--alpha", type=float, default=0.92)
    a = ap.parse_args(argv)
    Overlay(Path(a.state_dir), a.interval,
            topmost=not a.no_topmost, alpha=a.alpha,
            packs_dir=Path(a.packs_dir) if a.packs_dir else None,
            pack_file=Path(a.pack_file) if a.pack_file else None,
            setup=a.setup).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
