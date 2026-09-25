"""Fixture harness tests (US5: FR-010, FR-011, FR-012, SC-005).

Covers contracts/fixture-package.md harness semantics:
- SC-005: five consecutive replays of fix.seed-001 produce byte-identical
  reports.
- FR-011: fix.corrupt-001 fails closed naming structural defects
  (fixture.input.torn_tail, fixture.hash.mismatch); no partial replay.
- FR-012: the torn tail is moved to quarantine/ while the intact record
  prefix still loads.
- Missing manifest provenance is rejected with fixture.provenance.missing.
- fix.max-001 exercises blobs/ member hashing + field-subset mode;
  fix.baseline-001 exercises raw upstream records wrapped through
  contracts.eventmap (T032).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS_DIR = Path(__file__).resolve().parent
LAB_DIR = TESTS_DIR.parent
REPO_ROOT = LAB_DIR.parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
LAB_SRC = LAB_DIR / "src"
CONTRACTS_SRC = LAB_DIR.parent / "contracts" / "src"

from lab import fixtures  # noqa: E402


def _copy_fixture(fixture_id: str, dest_dir: Path) -> Path:
    dest = dest_dir / fixture_id
    shutil.copytree(FIXTURES_DIR / fixture_id, dest)
    return dest


def _defect_codes(report: dict) -> list[str]:
    return [d["code"] for d in report["defects"]]


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------


def test_seed_001_replays_ok():
    report, blob = fixtures.run_fixture(FIXTURES_DIR / "fix.seed-001")
    assert report["status"] == "ok"
    assert report["fixture_id"] == "fix.seed-001"
    assert report["mode"] == "exact"
    assert report["defects"] == []
    assert report["quarantine"] == []
    assert report["records"] == {"input": 1, "expected": 1}
    assert report["comparison"]["counts"]["equivalent"] == 1
    assert json.loads(blob) == report


def test_determinism_five_runs_byte_identical(tmp_path):
    """SC-005: 5 consecutive replays produce byte-identical reports."""
    blobs = []
    for run in range(5):
        _, blob = fixtures.run_fixture(FIXTURES_DIR / "fix.seed-001")
        blobs.append(blob)
    assert len(set(blobs)) == 1, "reports diverged across identical replays"
    # and identical again when written through the CLI report path
    for run in range(2):
        out = tmp_path / f"report-{run}.json"
        rc = fixtures.main([str(FIXTURES_DIR / "fix.seed-001"), "--report", str(out)])
        assert rc == fixtures.EXIT_OK
        assert out.read_bytes() == blobs[0]


def test_max_001_blobs_and_field_subset():
    report, _ = fixtures.run_fixture(FIXTURES_DIR / "fix.max-001")
    assert report["status"] == "ok"
    assert report["mode"] == "field-subset"
    assert report["records"] == {"input": 3, "expected": 3}
    assert report["comparison"]["counts"]["equivalent"] == 3


def test_max_001_tampered_blob_fails_closed(tmp_path):
    dest = _copy_fixture("fix.max-001", tmp_path)
    (dest / "blobs" / "situation-packet.txt").write_bytes(b"tampered\n")
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    assert "fixture.hash.mismatch" in _defect_codes(report)
    assert report["comparison"] is None  # fail closed: no partial replay


def test_baseline_001_replays_corpus():
    """T032: raw upstream records wrap to canonical envelopes, exact compare."""
    report, _ = fixtures.run_fixture(FIXTURES_DIR / "fix.baseline-001")
    assert report["status"] == "ok"
    assert report["records"] == {"input": 18, "expected": 18}
    assert report["comparison"]["counts"]["equivalent"] == 18
    manifest = yaml.safe_load(
        (FIXTURES_DIR / "fix.baseline-001" / "manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["provenance"]["derivation"] == "synthesized-from-baseline"
    assert manifest["provenance"]["source"] == "baseline-bundle"


# ---------------------------------------------------------------------------
# fail-closed corruption handling (FR-011 / FR-012)
# ---------------------------------------------------------------------------


def test_corrupt_001_fails_closed_named_defects(tmp_path):
    dest = _copy_fixture("fix.corrupt-001", tmp_path)
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    codes = _defect_codes(report)
    assert "fixture.hash.mismatch" in codes
    assert "fixture.input.torn_tail" in codes
    # fail closed: corruption means no comparison result at all
    assert report["comparison"] is None
    # hash defect names the offending member
    mismatch = next(d for d in report["defects"] if d["code"] == "fixture.hash.mismatch")
    assert mismatch["details"]["member"] == "blobs/note.txt"


def test_corrupt_001_quarantine_salvage(tmp_path):
    """FR-012: torn tail isolated in quarantine/, intact prefix still loads."""
    dest = _copy_fixture("fix.corrupt-001", tmp_path)
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    # intact prefix parsed: two valid records survived the torn tail
    assert report["records"]["input"] == 2
    assert report["records"]["expected"] == 2
    # torn tail quarantined with a named defect and recoverable bytes
    assert len(report["quarantine"]) == 1
    entry = report["quarantine"][0]
    assert entry["code"] == "fixture.input.torn_tail"
    assert entry["member"] == "input.jsonl"
    assert entry["line"] == 3
    qfile = dest / entry["file"]
    assert qfile.is_file()
    salvaged = qfile.read_bytes()
    assert salvaged.startswith(b'{"correlation":null')
    with pytest.raises(json.JSONDecodeError):
        json.loads(salvaged)


def test_missing_provenance_rejected(tmp_path):
    """Manifest without provenance is refused before any replay."""
    dest = _copy_fixture("fix.seed-001", tmp_path)
    manifest_path = dest / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    del manifest["provenance"]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    assert "fixture.provenance.missing" in _defect_codes(report)
    assert report["comparison"] is None


def test_record_missing_provenance_rejected(tmp_path):
    """Raw upstream records without a provenance marker are refused."""
    dest = tmp_path / "fix.noprov-001"
    dest.mkdir()
    record = {"seq": 1, "t": 1790035200.0, "kind": "log", "data": {"text": "x"}}
    (dest / "input.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (dest / "expected.jsonl").write_text("{}\n", encoding="utf-8")
    import hashlib

    files = {
        name: hashlib.sha256((dest / name).read_bytes()).hexdigest()
        for name in ("input.jsonl", "expected.jsonl")
    }
    (dest / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 0,
                "fixture_id": "fix.noprov-001",
                "created_utc": "2026-09-22T00:00:00Z",
                "provenance": {"source": "synthesized", "source_hash": files["input.jsonl"]},
                "schema_pins": {"envelope_schema_version": 0},
                "files": files,
                "expected_comparison": {"mode": "exact"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    assert "fixture.record.provenance_missing" in _defect_codes(report)


def test_divergence_reported_not_failed(tmp_path):
    """A clean fixture whose replay differs from expected -> diverged, exit 1."""
    dest = _copy_fixture("fix.seed-001", tmp_path)
    expected_path = dest / "expected.jsonl"
    expected = json.loads(expected_path.read_text(encoding="utf-8").strip())
    expected["payload"]["phase"] = "finished"
    new_bytes = (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    expected_path.write_bytes(new_bytes)
    import hashlib

    manifest_path = dest / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["expected.jsonl"] = hashlib.sha256(new_bytes).hexdigest()
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "diverged"
    line = report["comparison"]["lines"][0]
    assert line["result"] == "divergent"
    assert "payload.phase" in line["diff_paths"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_writes_report_and_exit_codes(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(LAB_SRC) + os.pathsep + str(CONTRACTS_SRC)
    report_path = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "lab.fixtures",
            str(FIXTURES_DIR / "fix.seed-001"),
            "--report",
            str(report_path),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    report = json.loads(report_path.read_bytes())
    assert report["status"] == "ok"

    corrupt = _copy_fixture("fix.corrupt-001", tmp_path / "cli")
    proc = subprocess.run(
        [sys.executable, "-m", "lab.fixtures", str(corrupt)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == fixtures.EXIT_FAILED
    assert "fixture.input.torn_tail" in proc.stdout


def test_undeclared_member_file_rejected(tmp_path):
    dest = _copy_fixture("fix.seed-001", tmp_path)
    (dest / "stray.txt").write_text("undeclared\n", encoding="utf-8")
    report, _ = fixtures.run_fixture(dest)
    assert report["status"] == "failed"
    assert "fixture.file.undeclared" in _defect_codes(report)
