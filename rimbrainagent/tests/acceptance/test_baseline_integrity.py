"""US1 acceptance: baseline integrity tamper detection (T010; SC-006).

Drops a scratch file inside the pinned ``upstream/rimagent`` worktree, asserts
``tools/baseline_validate.py`` flags it within 60 seconds with the structured
error envelope, then restores the worktree and asserts it is clean again.
The probe is removed in a finally block so the baseline is restored even if
assertions fail.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import acceptance_helpers as ah  # noqa: E402

REPO_ROOT = ah.REPO_ROOT
VALIDATOR = REPO_ROOT / "tools" / "baseline_validate.py"
PROBE = REPO_ROOT / "upstream" / "rimagent" / "__tamper_probe__.tmp"
DETECTION_BUDGET_S = 60


def run_validator(timeout: int = DETECTION_BUDGET_S) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR)],
        capture_output=True, text=True, timeout=timeout,
    )


def test_tamper_detected_then_restored() -> None:
    assert not PROBE.exists(), f"leftover probe at {PROBE}; remove it first"
    PROBE.write_text("tamper probe - not upstream content\n", encoding="utf-8")
    try:
        start = time.monotonic()
        proc = run_validator()
        elapsed = time.monotonic() - start

        assert proc.returncode != 0, (
            f"validator did not flag the probe file:\n{proc.stdout}"
        )
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        err = payload["error"]
        assert isinstance(err["code"], str) and err["code"]
        assert isinstance(err["message"], str) and err["message"]
        assert isinstance(err["details"], dict)
        assert isinstance(err["retryable"], bool)
        # The error must name the tampered worktree.
        assert "upstream/rimagent" in json.dumps(err["details"])
        assert elapsed < DETECTION_BUDGET_S, (
            f"detection took {elapsed:.1f}s, budget {DETECTION_BUDGET_S}s (SC-006)"
        )
    finally:
        PROBE.unlink(missing_ok=True)

    restored = run_validator()
    assert restored.returncode == 0, (
        f"baseline not clean after probe removal:\n{restored.stdout}"
    )
    # And git agrees the worktree is pristine again.
    assert ah.git_stdout(
        "status", "--porcelain", cwd=REPO_ROOT / "upstream" / "rimagent"
    ).strip() == ""
