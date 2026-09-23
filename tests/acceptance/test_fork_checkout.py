"""US1 acceptance: fork checkout validation (T009; SC-001, SC-002).

Asserts the pinned upstream submodules sit at their recorded revisions, the
pinned worktree is pristine, and the upstream test commands are documented in
the quickstart (upstream parity, FR-004).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import acceptance_helpers as ah  # noqa: E402
import baseline_validate  # noqa: E402  (tools/baseline_validate.py)

REPO_ROOT = ah.REPO_ROOT
QUICKSTART = REPO_ROOT / "specs" / "001-fork-bootstrap-contracts" / "quickstart.md"
VALIDATOR = REPO_ROOT / "tools" / "baseline_validate.py"


@pytest.mark.parametrize(
    "submodule,expected",
    sorted(baseline_validate.EXPECTED_PINS.items()),
    ids=list(baseline_validate.EXPECTED_PINS),
)
def test_submodule_pin_matches_manifest(submodule: str, expected: str) -> None:
    """Each pinned submodule HEAD equals the recorded pin (SC-001)."""
    actual = ah.git_stdout("rev-parse", "HEAD", cwd=REPO_ROOT / submodule).strip()
    assert actual == expected, (
        f"{submodule} at {actual}, expected pin {expected}"
    )


def test_upstream_porcelain_clean() -> None:
    """`git status --porcelain` inside upstream/rimagent is empty (FR-002)."""
    out = ah.git_stdout("status", "--porcelain", cwd=REPO_ROOT / "upstream" / "rimagent")
    assert out.strip() == "", f"upstream/rimagent is dirty:\n{out}"


def test_baseline_validator_passes() -> None:
    """tools/baseline_validate.py exits 0 on the intact baseline (SC-006)."""
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"baseline_validate failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )


def test_upstream_test_commands_documented() -> None:
    """quickstart.md documents the unmodified upstream suites (SC-002, FR-004)."""
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "uv run pytest -q" in text, "quickstart missing upstream pytest command"
    assert "upstream/rimagent/agent" in text or "rimagent/agent" in text
    # Both dotnet suites must be documented.
    assert "mod/Tests" in text and "dotnet test" in text
    assert "mod-steward" in text
