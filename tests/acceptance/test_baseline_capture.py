"""T019 acceptance test for tools/baseline_capture.py (US2).

Asserts the static [Rpc] extraction produces the 115-method inventory
(97 RimBridge + 18 Steward) with FR-013 traceability fields, and that two
consecutive manifest captures are byte-identical modulo created_utc (FR-009).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "baseline_capture.py"
BUNDLE = REPO / "baselines" / "upstream-85cb050"


def _run(mode: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), mode],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def _strip_created_utc(raw: bytes) -> bytes:
    """Drop the created_utc line — the only field allowed to differ (FR-009)."""
    return b"\n".join(
        line for line in raw.split(b"\n") if not line.startswith(b"created_utc:")
    )


def test_rpc_inventory_115_methods_with_traceability():
    result = _run("rpc")
    assert result.returncode == 0, result.stderr

    inventory_path = BUNDLE / "rpc-inventory.json"
    assert inventory_path.is_file()
    rows = json.loads(inventory_path.read_text(encoding="utf-8"))

    assert len(rows) == 115, f"expected 115 RPC methods, got {len(rows)}"

    bridge = [r for r in rows if r["source_file"].startswith("upstream/rimagent/mod/")]
    steward = [
        r for r in rows if r["source_file"].startswith("upstream/rimagent/mod-steward/")
    ]
    assert len(bridge) == 97
    assert len(steward) == 18

    for row in rows:
        # FR-013: every row traces back to an upstream origin.
        assert row["name"], row
        assert row["group"] == row["name"].split(".", 1)[0]
        assert isinstance(row["doc"], str)
        assert row["source_file"].endswith(".cs"), row
        assert (REPO / row["source_file"]).is_file(), row["source_file"]
        assert isinstance(row["line"], int) and row["line"] > 0, row


def test_manifest_deterministic_across_runs():
    first = _run("manifest")
    assert first.returncode == 0, first.stderr
    manifest_1 = (BUNDLE / "MANIFEST.yaml").read_bytes()
    gaps_1 = (BUNDLE / "gaps.yaml").read_bytes()

    second = _run("manifest")
    assert second.returncode == 0, second.stderr
    manifest_2 = (BUNDLE / "MANIFEST.yaml").read_bytes()
    gaps_2 = (BUNDLE / "gaps.yaml").read_bytes()

    assert b"created_utc:" in manifest_1
    assert _strip_created_utc(manifest_1) == _strip_created_utc(manifest_2)
    assert gaps_1 == gaps_2
