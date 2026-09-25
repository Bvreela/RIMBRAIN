#!/usr/bin/env python3
"""Baseline characterization capture for the pinned upstream rimagent tree.

US2 / T020-T023 (specs/001-fork-bootstrap-contracts). Builds an immutable
BaselineBundle under ``baselines/upstream-85cb050/`` entirely offline per
research.md R2: static ``[Rpc]`` attribute extraction, a docstring-synthesized
event corpus from ``agent/rimagent/bus.py``, a Steward automation-surface
inventory, and a sealed manifest + gaps record.

Capture target is zorrobyte RimBridge + Steward per ADR-013 (ADR-001/T004
outcome). ``upstream/`` is read-only input; nothing here writes into it.

Modes (argparse subcommands): rpc | events | steward | manifest | all

Determinism contract (FR-009): two runs on an unchanged tree produce
byte-identical outputs except the ``created_utc`` line of MANIFEST.yaml.
Everything else is sorted and free of timestamps.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = REPO_ROOT / "upstream" / "rimagent"
BUNDLE_DIR = REPO_ROOT / "baselines" / "upstream-85cb050"

BUNDLE_ID = "upstream-85cb050"
PIN_RIMAGENT = "85cb050dec47691f2a80096fdc8c8a8e2051bb13"
PIN_MOD = "3c1e4c7cee151104b85bf9c8372e113f91c5f08d"

TOOL_NAME = "baseline_capture.py"
TOOL_VERSION = "1.0.0"

# Directories never scanned or hashed as source (build output, VCS metadata).
_SKIP_DIRS = {".git", "obj", "bin"}

RPC_DIRS = (UPSTREAM / "mod" / "Source", UPSTREAM / "mod-steward" / "Source")
BUS_PY = UPSTREAM / "agent" / "rimagent" / "bus.py"
AGENTS_MD = UPSTREAM / "AGENTS.md"
ORDERS_DIR = UPSTREAM / "mod-steward" / "Source" / "Steward" / "Orders"

RPC_ATTR_RE = re.compile(
    r'\[Rpc\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"'
)
BUS_KIND_RE = re.compile(r"^\s*([a-z_]+)\s+data:", re.MULTILINE)
ORDER_ID_RE = re.compile(r'public\s+override\s+string\s+Id\s*=>\s*"([^"]+)"')
ORDER_LABEL_RE = re.compile(r'public\s+override\s+string\s+Label\s*=>\s*"([^"]+)"')
# String-literal run terminated by `;` — tolerates embedded semicolons and
# $-interpolated literals (interpolation holes are left verbatim).
ORDER_DOC_RE = re.compile(
    r'public\s+override\s+string\s+Doc\s*=>\s*'
    r'((?:\$?"(?:[^"\\]|\\.)*"\s*\+?\s*)+);'
)
ORDER_INTERVAL_RE = re.compile(r"public\s+override\s+int\s+IntervalTicks\s*=>\s*(\d+)")
CS_STR_RE = re.compile(r'\$?"((?:[^"\\]|\\.)*)"')

# Fixed synthetic wall-time for generated corpus records: the upstream pin
# date (2026-09-22T00:00:00Z), constant so captures are byte-identical.
SYNTH_T = datetime(2026, 9, 22, tzinfo=timezone.utc).timestamp()

# Minimal synthesized `data` shapes per bus.py docstring contract. Unknown
# kinds parsed from the docstring still get a record with an empty dict so
# the corpus tracks upstream if it adds kinds.
KIND_DATA = {
    "status": {"episode": 1, "seed": "synthetic", "phase": "playing"},
    "think_start": {"trigger": "schedule", "step": 1},
    "reasoning": {"text": "synthetic"},
    "assistant": {"text": "synthetic"},
    "tool_call": {"name": "rw_state_summary", "args": {}, "id": "call-1"},
    "tool_result": {
        "name": "rw_state_summary",
        "id": "call-1",
        "ok": True,
        "text": "{}",
        "elapsed": 0.0,
    },
    "think_end": {"notes": "synthetic", "wake": {}, "calls": 0, "elapsed": 0.0},
    "ledger": {"kind": "synthetic", "text": "synthetic", "tick": 0, "day": 0},
    "watcher": {"name": "synthetic", "action": "synthetic"},
    "brain_change": {"kind": "skill", "name": "synthetic", "action": "write"},
    "watchdog": {
        "summary": "synthetic",
        "fixes": [],
        "skipped": [],
        "commits": [],
        "errors": 0,
        "uncommitted": [],
    },
    "episode_start": {"episode": 1, "seed": "synthetic"},
    "episode_end": {
        "episode": 1,
        "score": 0.0,
        "reason": "synthetic",
        "assisted": False,
        "brain_sha": "0" * 40,
    },
    "situation": {
        "trigger": "synthetic",
        "tracked": "synthetic",
        "changes": "synthetic",
        "day": 0,
        "hour": 0,
        "chars": 0,
    },
    "operator": {"text": "synthetic"},
    "reply": {"text": "synthetic"},
    "log": {"text": "synthetic"},
    "error": {"text": "synthetic"},
}

_YAML_PLAIN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-/]*")
_YAML_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _iter_cs_files(root: Path) -> list[Path]:
    """All .cs files under root, excluding build output and VCS dirs."""
    out = []
    for p in root.rglob("*.cs"):
        rel_parts = p.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        out.append(p)
    return sorted(out)


def _unescape_cs(s: str) -> str:
    """Resolve C# string-literal escapes in an attribute argument."""
    escapes = {"n": "\n", "t": "\t", "r": "\r", "0": "\0",
               '"': '"', "'": "'", "\\": "\\"}
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(escapes.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def extract_rpcs() -> list[dict]:
    """Parse every [Rpc("name", "doc")] attribute in the mod Source trees."""
    rows = []
    for source_root in RPC_DIRS:
        for path in _iter_cs_files(source_root):
            text = path.read_text(encoding="utf-8")
            for m in RPC_ATTR_RE.finditer(text):
                name = _unescape_cs(m.group(1))
                rows.append({
                    "name": name,
                    "group": name.split(".", 1)[0],
                    "doc": _unescape_cs(m.group(2)),
                    "source_file": path.relative_to(REPO_ROOT).as_posix(),
                    "line": text.count("\n", 0, m.start()) + 1,
                })
    rows.sort(key=lambda r: (r["name"], r["source_file"], r["line"]))
    return rows


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------
# minimal deterministic YAML emitter (block style, JSON-quoted unsafe scalars)
# ---------------------------------------------------------------------------

def _yaml_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if _YAML_PLAIN_RE.fullmatch(s) and s.lower() not in _YAML_RESERVED:
        return s
    return json.dumps(s, ensure_ascii=False)


def _yaml_lines(obj, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and not v:
                lines.append(f"{pad}{k}: {{}}")
            elif isinstance(v, list) and not v:
                lines.append(f"{pad}{k}: []")
            elif isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.extend(_yaml_lines(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_yaml_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
    else:
        lines.append(f"{pad}{_yaml_scalar(obj)}")
    return lines


def _yaml_dump(obj) -> str:
    return "\n".join(_yaml_lines(obj)) + "\n"


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------

def mode_rpc() -> Path:
    """T020: static [Rpc] inventory -> rpc-inventory.json."""
    rows = extract_rpcs()
    out = _write_text(
        BUNDLE_DIR / "rpc-inventory.json",
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
    )
    print(f"rpc: {len(rows)} methods -> {out.relative_to(REPO_ROOT)}")
    return out


def parse_bus_kinds() -> list[str]:
    """Ordered event kinds from the bus.py module docstring."""
    doc = ast.get_docstring(ast.parse(BUS_PY.read_text(encoding="utf-8"))) or ""
    kinds, seen = [], set()
    for m in BUS_KIND_RE.finditer(doc):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            kinds.append(m.group(1))
    return kinds


def mode_events() -> Path:
    """T021: synthesized per-kind event corpus -> event-corpus/bus-kinds.jsonl."""
    kinds = parse_bus_kinds()
    lines = []
    for seq, kind in enumerate(kinds, start=1):
        rec = {
            "seq": seq,
            "t": SYNTH_T,
            "kind": kind,
            "data": KIND_DATA.get(kind, {}),
            "provenance": "synthesized-from-docstring",
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    out = _write_text(
        BUNDLE_DIR / "event-corpus" / "bus-kinds.jsonl",
        "\n".join(lines) + "\n",
    )
    print(f"events: {len(kinds)} kinds -> {out.relative_to(REPO_ROOT)}")
    return out


def _extract_orders() -> list[dict]:
    """Standing-order ids/labels/docs/intervals from Orders/Order_*.cs."""
    orders = []
    for path in _iter_cs_files(ORDERS_DIR):
        if not path.name.startswith("Order_"):
            continue
        text = path.read_text(encoding="utf-8")
        idm = ORDER_ID_RE.search(text)
        if not idm:
            continue
        label = ORDER_LABEL_RE.search(text)
        doc_m = ORDER_DOC_RE.search(text)
        doc = ""
        if doc_m:
            doc = "".join(
                _unescape_cs(s) for s in CS_STR_RE.findall(doc_m.group(1))
            )
        interval = ORDER_INTERVAL_RE.search(text)
        orders.append({
            "id": idm.group(1),
            "label": _unescape_cs(label.group(1)) if label else "",
            "doc": doc,
            "interval_ticks": int(interval.group(1)) if interval else None,
            "source_file": path.relative_to(REPO_ROOT).as_posix(),
        })
    orders.sort(key=lambda o: o["id"])
    return orders


def _agents_config_line() -> str:
    """The `steward: {...}` config-surface line from upstream AGENTS.md."""
    for line in AGENTS_MD.read_text(encoding="utf-8").splitlines():
        if "steward:" in line and "{" in line:
            m = re.search(r"steward:\s*\{.*\}", line)
            if m:
                return m.group(0)
    return ""


def mode_steward() -> Path:
    """T022: Steward automation surface -> automation-surface.yaml."""
    steward_rpcs = [
        r for r in extract_rpcs()
        if r["source_file"].startswith("upstream/rimagent/mod-steward/")
    ]

    def bucket(rpc):
        if rpc["name"].startswith("steward.orders"):
            return "orders"
        if rpc["name"].startswith("steward.stock"):
            return "stock"
        return "scorer"  # status/enable/pawn/explain/posture/settings/research

    def row(r):
        return {
            "name": r["name"],
            "doc": r["doc"],
            "source": f"{r['source_file']}:{r['line']}",
        }

    surface = {
        "bundle_id": BUNDLE_ID,
        "provenance": "static-extraction",
        "description": (
            "Steward (zorrobyte rimbridgesteward) deterministic automation "
            "surface: scorer/stock/standing-orders RPCs plus the config keys "
            "documented in upstream AGENTS.md. Captured offline from source; "
            "no live game required."
        ),
        "sources": {
            "rpc_attributes": "upstream/rimagent/mod-steward/Source",
            "docs": "upstream/rimagent/AGENTS.md",
        },
        "scorer": {
            "summary": (
                "Free Will port: writes work priorities for every managed "
                "colonist each tick; posture is a time-boxed colony-wide bias."
            ),
            "rpcs": [row(r) for r in steward_rpcs if bucket(r) == "scorer"],
        },
        "stock": {
            "summary": (
                "Colony Manager Redux rewrite: keeps stock jobs (forestry, "
                "foraging, hunting, mining, production, livestock) at targets "
                "by designating work."
            ),
            "rpcs": [row(r) for r in steward_rpcs if bucket(r) == "stock"],
        },
        "orders": {
            "summary": (
                "Standing orders: deterministic reflexes ticked from a "
                "MapComponent, staggered by id, honour manual-touch cooldowns."
            ),
            "rpcs": [row(r) for r in steward_rpcs if bucket(r) == "orders"],
            "standing_orders": _extract_orders(),
        },
        "config_surface": {
            "agents_md_line": _agents_config_line(),
            "keys": [
                "steward.enabled",
                "steward.scorer",
                "steward.stock",
                "steward.orders.enabled",
                "steward.orders.off",
                "steward.orders.superseded_watchers",
            ],
        },
    }
    out = _write_text(
        BUNDLE_DIR / "automation-surface.yaml", _yaml_dump(surface)
    )
    print(
        f"steward: {len(steward_rpcs)} rpcs, "
        f"{len(surface['orders']['standing_orders'])} standing orders "
        f"-> {out.relative_to(REPO_ROOT)}"
    )
    return out


def _git() -> str:
    """Locate git: PATH first, then the known Windows fallback."""
    import shutil
    git = shutil.which("git")
    if git:
        return git
    fallback = r"C:\Program Files\Git\cmd\git.exe"
    if Path(fallback).is_file():
        return fallback
    raise RuntimeError("git not found on PATH or at the standard fallback")


def _tracked_files(repo: Path) -> list[Path]:
    """git-tracked files under a repo (untracked/gitignored locals excluded)."""
    import subprocess
    out = subprocess.run(
        [_git(), "-C", str(repo), "ls-files", "-z"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8", "replace")
    return [p for p in (repo / rel for rel in out.split("\0") if rel) if p.is_file()]


def _tree_hash(root: Path) -> tuple[str, int]:
    """sha256 over the sorted `digest  relpath` list of git-tracked files.

    Covers the upstream repo and its nested mod submodule (a gitlink in the
    parent listing, so it needs its own ls-files). Untracked or gitignored
    locals (config.local.yaml, build output, editor cruft) never perturb the
    hash, keeping manifests comparable across machines (FR-009).
    """
    entries = []
    for repo in (root, root / "mod"):
        for p in _tracked_files(repo):
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            entries.append(f"{digest}  {p.relative_to(REPO_ROOT).as_posix()}")
    entries.sort()
    tree = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return tree, len(entries)


def mode_manifest() -> list[Path]:
    """T023: MANIFEST.yaml + gaps.yaml; only created_utc varies between runs."""
    tree_hash, tree_files = _tree_hash(UPSTREAM)
    created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "bundle_id": BUNDLE_ID,
        "created_utc": created_utc,
        "pins": {
            "rimagent": PIN_RIMAGENT,
            "mod": PIN_MOD,
        },
        "tree_hash": tree_hash,
        "tree_files": tree_files,
        "capture_methods": ["rpc", "events", "steward", "manifest"],
        "artifacts": {
            "rpc_inventory": "rpc-inventory.json",
            "event_corpus": "event-corpus/bus-kinds.jsonl",
            "automation_surface": "automation-surface.yaml",
            "manifest": "MANIFEST.yaml",
            "gaps": "gaps.yaml",
        },
        "tool": {
            "name": TOOL_NAME,
            "version": TOOL_VERSION,
            "python": platform.python_version(),
        },
    }
    mpath = _write_text(BUNDLE_DIR / "MANIFEST.yaml", _yaml_dump(manifest))

    gaps = {
        "bundle_id": BUNDLE_ID,
        "description": (
            "Deferred live captures and synthesized stand-ins for baseline "
            "bundle v1. Live samples land in bundle v1.1 after the first "
            "instrumented run (research.md R2); a new bundle version closes "
            "these gaps, never mutation of this one."
        ),
        "gaps": [
            {
                "id": "state.summary-live-sample",
                "artifact": "live-samples/state.summary.json",
                "provenance": (
                    "live-capture" if (BUNDLE_DIR / "live-samples" / "state.summary.json").is_file()
                    else "deferred-live"
                ),
                "reason": (
                    "requires a running RimWorld with RimBridge loaded; "
                    "Phase 0 prerequisite is toolchains, not a game session"
                ),
            },
            {
                "id": "bus-event-real-samples",
                "artifact": "live-samples/bridge-events.jsonl",
                "provenance": (
                    "live-capture" if (BUNDLE_DIR / "live-samples" / "bridge-events.jsonl").is_file()
                    else "deferred-live"
                ),
                "reason": (
                    "real runner bus events need a live upstream `rimagent play` "
                    "session (the bridge /events feed is bridge-side, not bus "
                    "kinds); bridge feed captured as bridge-events.jsonl"
                ),
            },
        ],
        "synthesized": [
            {
                "artifact": "event-corpus/bus-kinds.jsonl",
                "provenance": "synthesized-from-docstring",
                "source": "upstream/rimagent/agent/rimagent/bus.py",
                "note": (
                    "validates record format, not values; data shapes are "
                    "minimal per the bus.py docstring contract"
                ),
            },
            {
                "artifact": "automation-surface.yaml",
                "provenance": "static-extraction",
                "source": (
                    "upstream/rimagent/mod-steward/Source + "
                    "upstream/rimagent/AGENTS.md"
                ),
            },
            {
                "artifact": "rpc-inventory.json",
                "provenance": "static-extraction",
                "source": (
                    "upstream/rimagent/mod/Source + "
                    "upstream/rimagent/mod-steward/Source [Rpc] attributes"
                ),
            },
        ],
    }
    gpath = _write_text(BUNDLE_DIR / "gaps.yaml", _yaml_dump(gaps))
    print(f"manifest: tree_hash {tree_hash[:12]}... ({tree_files} files) "
          f"-> {mpath.relative_to(REPO_ROOT)}, {gpath.relative_to(REPO_ROOT)}")
    return [mpath, gpath]


def mode_live() -> list[Path]:
    """T039: live representative samples — state.summary + real event window.

    Requires RimWorld running with the zorrobyte RimBridge loaded on :8765
    (ADR-013 primary). Closes the deferred-live entries in gaps.yaml; the
    bundle manifest stays sealed — closure is recorded in gaps.yaml only.
    """
    import urllib.request

    base = "http://127.0.0.1:8765"
    out_dir = BUNDLE_DIR / "live-samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def _get(path: str):
        return json.loads(urllib.request.urlopen(base + path, timeout=10).read())

    def _rpc(method: str, params: dict | None = None):
        body = json.dumps({"method": method, "params": params or {}}).encode()
        req = urllib.request.Request(
            base + "/rpc", data=body, headers={"Content-Type": "application/json"}
        )
        return json.loads(urllib.request.urlopen(req, timeout=15).read())

    try:
        status = _rpc("game.status")
        if not (status.get("ok") and status["result"].get("state") == "playing"):
            raise RuntimeError(f"game not in playing state: {status}")
        summary = _rpc("state.summary")
        events_resp = _get("/events?since=0")
        # GET /events returns {events: [...], last_seq, head_seq, assisted} —
        # the bridge-side feed, not runner bus.py kinds (those only exist in
        # an upstream play session's own files; none captured yet).
        ev_list = events_resp.get("events", []) if isinstance(events_resp, dict) else []
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": {
                "code": "LIVE_CAPTURE_UNAVAILABLE",
                "message": str(exc),
                "details": {"bridge": base},
                "retryable": True,
            },
        }))
        return written

    sp = _write_text(
        out_dir / "state.summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    written.append(sp)
    ep = _write_text(
        out_dir / "bridge-events.jsonl",
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in ev_list),
    )
    written.append(ep)
    print(f"live: state.summary + {len(ev_list)} bridge events -> "
          f"{out_dir.relative_to(REPO_ROOT)}")
    return written


def mode_all() -> None:
    mode_rpc()
    mode_events()
    mode_steward()
    mode_manifest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="baseline_capture",
        description="Offline baseline bundle capture for pinned upstream "
                    "rimagent (US2).",
    )
    parser.add_argument(
        "mode",
        choices=["rpc", "events", "steward", "manifest", "live", "all"],
        help="capture mode",
    )
    args = parser.parse_args(argv)
    written = {
        "rpc": mode_rpc,
        "events": mode_events,
        "steward": mode_steward,
        "manifest": mode_manifest,
        "live": mode_live,
        "all": mode_all,
    }[args.mode]()
    # live exits nonzero when the bridge was unavailable (T045)
    return 1 if args.mode == "live" and not written else 0


if __name__ == "__main__":
    sys.exit(main())
