"""Feature 018 T009 — PARAM_SPEC argv assembly + constraint mirror."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "dashboard" / "src"))

from dashboard import paramspec  # noqa: E402

# The fair-run preset — byte-for-byte the argv `rimbrain run -y` emits
# (contracts/launch-cli.md assembled-argv order).
DEFAULT_ARGV = ["--pack", "start-mode-v0", "--mode", "run",
                "--game", "live", "--iterations", "2000",
                "--bridge", "http://127.0.0.1:8765",
                "--fair", "--live-flag", "--live-brain",
                "--live-mutate", "--feed"]


def test_defaults_match_fair_preset():
    d = paramspec.defaults()
    assert d["fair"] is True and d["live"] is True
    assert d["live_brain"] is True and d["live_mutate"] is True
    assert d["feed"] is True
    assert d["mode"] == "run" and d["game"] == "live"
    assert d["pack"] == "start-mode-v0" and d["iterations"] == 2000
    assert d["bridge"] == "http://127.0.0.1:8765"


def test_every_loop_flag_has_a_row():
    flags = {r["flag"] for r in paramspec.PARAM_SPEC}
    assert flags == {"pack", "mode", "game", "stage", "iterations",
                     "bridge", "fair", "live", "live_brain",
                     "live_mutate", "feed", "ledger", "no_store",
                     "no_hold", "scored", "fresh"}


def test_argv_defaults_equal_run_y():
    assert paramspec.argv(paramspec.defaults()) == DEFAULT_ARGV


def test_argv_emits_flags_only_when_set():
    cfg = paramspec.defaults()
    cfg.update(feed=False, live_brain=False, live_mutate=False,
               ledger=True, no_store=True, no_hold=True, scored=True,
               fresh=True, stage="plan", mode="improve")
    av = paramspec.argv(cfg)
    assert "--feed" not in av and "--live-brain" not in av
    assert "--live-mutate" not in av
    for f in ("--ledger", "--no-store", "--no-hold", "--scored",
              "--fresh"):
        assert f in av
    assert av[av.index("--stage") + 1] == "plan"


def test_dev_inverts_fair():
    cfg = paramspec.defaults()
    cfg["fair"] = False
    assert "--dev" in paramspec.argv(cfg)
    assert "--fair" not in paramspec.argv(cfg)


def test_violations_clean_default():
    assert paramspec.violations(paramspec.defaults()) == []


def test_cycle_needs_dev():
    cfg = paramspec.defaults()
    cfg["mode"] = "cycle"
    v = paramspec.violations(cfg)
    assert any("cycle" in p for p in v)
    cfg["fair"] = False
    cfg["live_mutate"] = False  # mutate is ineligible off run+live
    assert paramspec.violations(cfg) == []


def test_live_needs_confirm():
    cfg = paramspec.defaults()
    cfg["live"] = False
    v = paramspec.violations(cfg)
    assert any("live" in p for p in v)
    cfg["game"] = "sim"
    cfg["live_mutate"] = False
    assert paramspec.violations(cfg) == []


def test_live_mutate_mode_gate():
    cfg = paramspec.defaults()
    cfg["mode"] = "improve"
    cfg["game"] = "sim"
    v = paramspec.violations(cfg)
    assert any("live-mutate" in p for p in v)
    cfg["mode"] = "fastevolve"
    cfg["game"] = "live"
    assert not any("live-mutate" in p for p in paramspec.violations(cfg))


def test_fastevolve_fair_and_scored_rules():
    cfg = paramspec.defaults()
    cfg["mode"] = "fastevolve"
    cfg["fair"] = False
    assert any("fair" in p for p in paramspec.violations(cfg))
    cfg["fair"] = True
    cfg["scored"] = True
    assert any("scored" in p for p in paramspec.violations(cfg))


def test_combat_stage_needs_dev():
    cfg = paramspec.defaults()
    cfg["stage"] = "combat"
    assert any("combat" in p for p in paramspec.violations(cfg))
    cfg["fair"] = False
    assert paramspec.violations(cfg) == []


def test_dev_pack_blocked_under_fair():
    cfg = paramspec.defaults()
    cfg["pack"] = "dev-lab-v0"
    assert any("dev" in p for p in
               paramspec.violations(cfg, pack_class="dev"))
    assert paramspec.violations(cfg, pack_class="fair") == []
    cfg["fair"] = False
    assert paramspec.violations(cfg, pack_class="dev") == []


def test_enable_when_greys():
    cfg = paramspec.defaults()
    rows = {r["flag"]: r for r in paramspec.PARAM_SPEC}
    assert paramspec.enabled(rows["no_hold"], cfg)
    cfg["mode"] = "improve"
    assert not paramspec.enabled(rows["no_hold"], cfg)
    assert not paramspec.enabled(rows["game"], cfg)
    assert not paramspec.enabled(rows["live_mutate"], cfg)
    cfg["mode"] = "fastevolve"
    assert not paramspec.enabled(rows["scored"], cfg)
    assert paramspec.enabled(rows["live_mutate"], cfg)


def test_presets():
    sim = paramspec.preset("Sim test")
    assert sim["game"] == "sim" and sim["live"] is False
    dev = paramspec.preset("Dev lab")
    assert dev["fair"] is False and dev["pack"] == "dev-lab-v0"
    assert paramspec.preset("Fair run") == paramspec.defaults()
