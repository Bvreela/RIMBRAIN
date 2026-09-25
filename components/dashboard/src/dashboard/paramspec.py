"""Declarative launch-parameter spec (feature 018; FR-002/004).

One table drives the Setup screen's widget generation, argv assembly,
and the fail-closed constraint mirror — the same checks
``runtime.loop.main`` runs at launch, evaluated live so an invalid
combination is blocked or flagged before GO, never a surprise at spawn.

Pure module: no Tk, no I/O — widget glue lives in overlay.py.
"""

from __future__ import annotations

# {flag, label, kind: check|radio|spin|text|choice, default, group, hint,
#  enable_when/block_when: {field, eq|ne|in, value}}
# enable_when greys the control; violations() mirrors loop.main's
# fail-closed checks verbatim (they evolve together by convention).
PARAM_SPEC = [
    {"flag": "mode", "label": "Run mode", "kind": "radio",
     "choices": ["run", "fastevolve", "cycle", "improve"],
     "default": "run", "group": "Run",
     "hint": "run = unified phase loop; fastevolve = daily failure retry "
             "(unscored, fair only); cycle = checkpoint harness (needs "
             "dev); improve = evidence-only pass"},
    {"flag": "game", "label": "Game backend", "kind": "radio",
     "choices": ["live", "sim"], "default": "live", "group": "Run",
     "enable_when": {"field": "mode", "ne": "improve"},
     "hint": "live = real bridge (needs live confirm); sim = "
             "deterministic SimGame, zero network"},
    {"flag": "stage", "label": "Stage", "kind": "choice",
     "choices": ["", "plan", "reflect", "combat"], "default": "",
     "group": "Run",
     "enable_when": {"field": "mode", "eq": "run"},
     "hint": "debug entry — drive only one stage; combat is a scripted "
             "dev harness"},
    {"flag": "pack", "label": "Pack", "kind": "choice",
     "choices": [], "default": "start-mode-v0", "group": "Run",
     "hint": "policy pack id — bound to the pack list below"},
    {"flag": "iterations", "label": "Iterations", "kind": "spin",
     "default": 2000, "min": 1, "max": 100000, "group": "Run",
     "hint": "poll count bound for the run"},
    {"flag": "bridge", "label": "Bridge URL", "kind": "text",
     "default": "http://127.0.0.1:8765", "group": "Run",
     "enable_when": {"field": "mode", "in": ["run", "cycle", "fastevolve"]},
     "hint": "RimBridge HTTP endpoint (live game only)"},
    {"flag": "fair", "label": "Fair run", "kind": "check",
     "default": True, "group": "Flags",
     "hint": "default on — refuses dev.* + save/load dispatches and "
             "dev-class packs; off = --dev (testing only)"},
    {"flag": "live", "label": "Live confirm", "kind": "check",
     "default": True, "group": "Flags",
     "hint": "operator confirmation required for live game / cycle mode"},
    {"flag": "live_brain", "label": "Live brain", "kind": "check",
     "default": True, "group": "Flags",
     "hint": "honor brain-reset requests: pack swap/reload mid-run "
             "(never for scored runs)"},
    {"flag": "live_mutate", "label": "Live mutate", "kind": "check",
     "default": True, "group": "Flags",
     "enable_when": {"field": "mode", "in": ["run", "fastevolve"]},
     "hint": "in-run reflection passes promote candidate packs at the "
             "next boundary; only run+live or fastevolve"},
    {"flag": "feed", "label": "Feed", "kind": "check",
     "default": True, "group": "Flags",
     "hint": "narrate every emitted event into state/feed.md"},
    {"flag": "ledger", "label": "Ledger", "kind": "check",
     "default": False, "group": "Flags",
     "hint": "reconcile the task ledger before attend each poll"},
    {"flag": "no_store", "label": "No store", "kind": "check",
     "default": False, "group": "Flags",
     "hint": "do not persist events to state/events.jsonl"},
    {"flag": "no_hold", "label": "No hold", "kind": "check",
     "default": False, "group": "Flags",
     "enable_when": {"field": "mode", "eq": "run"},
     "hint": "run: stop at init completion instead of holding under "
             "standing goals"},
    {"flag": "scored", "label": "Scored", "kind": "check",
     "default": False, "group": "Flags",
     "enable_when": {"field": "mode", "ne": "fastevolve"},
     "hint": "declare a scored episode — play-only modes refused"},
    {"flag": "fresh", "label": "Fresh", "kind": "check",
     "default": False, "group": "Flags",
     "hint": "wipe session-scoped state before starting (keeps canonical "
             "events + mutation lineage)"},
]

_PRESETS = {
    "Fair run": {},
    "Sim test": {"mode": "run", "game": "sim", "live": False,
                 "live_brain": False, "live_mutate": False,
                 "iterations": 50},
    "Dev lab": {"fair": False, "live": True, "live_brain": True,
                "live_mutate": False, "pack": "dev-lab-v0",
                "mode": "run", "game": "live"},
}


def defaults() -> dict:
    """The fair-run preset (FR-003) — equals `rimbrain run -y`."""
    return {row["flag"]: row["default"] for row in PARAM_SPEC}


def preset(name: str) -> dict:
    """Named preset applied over defaults()."""
    cfg = defaults()
    cfg.update(_PRESETS.get(name, {}))
    return cfg


def presets() -> list[str]:
    return list(_PRESETS)


def _match(cond: dict, cfg: dict) -> bool:
    v = cfg.get(cond["field"])
    if "in" in cond:
        return v in cond["in"]
    if "eq" in cond:
        return v == cond["eq"]
    if "ne" in cond:
        return v != cond["ne"]
    return True


def enabled(row: dict, cfg: dict) -> bool:
    """Grey-out rule for one row against the current configuration."""
    cond = row.get("enable_when")
    return True if cond is None else _match(cond, cfg)


def argv(cfg: dict) -> list[str]:
    """Assembled flag list appended after RIMBRAIN_LOOP_CMD
    (contracts/launch-cli.md). Order-stable; flag args emitted only
    when set."""
    out = ["--pack", str(cfg["pack"]),
           "--mode", str(cfg["mode"]),
           "--game", str(cfg["game"]),
           "--iterations", str(int(cfg["iterations"])),
           "--bridge", str(cfg["bridge"])]
    if cfg.get("stage"):
        out += ["--stage", str(cfg["stage"])]
    out.append("--fair" if cfg.get("fair") else "--dev")
    for key, flag in (("live", "--live-flag"),
                      ("live_brain", "--live-brain"),
                      ("live_mutate", "--live-mutate"),
                      ("feed", "--feed"), ("ledger", "--ledger"),
                      ("no_store", "--no-store"),
                      ("no_hold", "--no-hold"), ("scored", "--scored"),
                      ("fresh", "--fresh")):
        if cfg.get(key):
            out.append(flag)
    return out


def violations(cfg: dict, pack_class: str | None = None) -> list[str]:
    """Fail-closed mirror of loop.main's launch checks (FR-004) plus
    pack-class gating (FR-012). Empty list => GO enabled."""
    out: list[str] = []
    mode, game = cfg.get("mode"), cfg.get("game")
    if (game == "live" or mode == "cycle") \
            and mode != "improve" and not cfg.get("live"):
        out.append("--game live / --mode cycle needs live confirm "
                   "(operator smoke only)")
    if mode == "cycle" and cfg.get("fair"):
        out.append("cycle mode is a checkpoint save/load harness; "
                   "it needs fair off (--dev)")
    if cfg.get("stage") == "combat" and cfg.get("fair"):
        out.append("stage combat executes dev.* tooling; it needs "
                   "fair off (--dev)")
    if mode == "fastevolve" and cfg.get("scored"):
        out.append("fast-evolve is an unscored play mode; scored "
                   "episodes refuse it")
    if mode == "fastevolve" and not cfg.get("fair"):
        out.append("fastevolve requires fair protections (save/load is "
                   "scoped-granted; dev.* stays refused)")
    if cfg.get("live_mutate") and not (
            (mode == "run" and game == "live") or mode == "fastevolve"):
        out.append("live-mutate only applies to run+live or fastevolve")
    if pack_class == "dev" and cfg.get("fair"):
        out.append("dev-class pack refused while fair is on")
    return out
