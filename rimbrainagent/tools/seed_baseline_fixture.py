"""Generate ``tests/fixtures/fix.baseline-001`` from the sealed baseline corpus (T032, FR-010).

Reads ``baselines/upstream-85cb050/event-corpus/bus-kinds.jsonl`` and writes a
fixture package per ``contracts/fixture-package.md``:

- ``input.jsonl``    — the recorded raw upstream ``{seq,t,kind,data,provenance}``
  records, canonical-serialized (RFC 8785 via contracts.canonical).
- ``expected.jsonl`` — each record wrapped through ``contracts.eventmap.wrap``
  into canonical envelopes: the observable replay output.
- ``manifest.yaml``  — sha256 of every member file, provenance tracing to the
  baseline bundle (``derivation: synthesized-from-baseline``).

Usage::

    uv run --with pyyaml,jsonschema python tools/seed_baseline_fixture.py

Regeneration is deterministic: fixed ``created_utc``, canonical serialization,
and hashes recomputed from the sealed corpus.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from contracts import canonical_text  # noqa: E402
from contracts import eventmap  # noqa: E402

CORPUS = REPO_ROOT / "baselines" / "upstream-85cb050" / "event-corpus" / "bus-kinds.jsonl"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "fix.baseline-001"
FIXTURE_ID = "fix.baseline-001"
CREATED_UTC = "2026-09-22T00:00:00Z"  # pinned: regeneration must be byte-stable


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    raw_lines = CORPUS.read_text(encoding="utf-8").splitlines()
    input_lines: list[str] = []
    expected_lines: list[str] = []
    for line in raw_lines:
        record = json.loads(line)
        if "provenance" not in record:
            raise SystemExit(f"corpus record missing provenance: {line!r}")
        input_lines.append(canonical_text(record))
        expected_lines.append(canonical_text(eventmap.wrap(record)))

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    input_bytes = ("\n".join(input_lines) + "\n").encode("utf-8")
    expected_bytes = ("\n".join(expected_lines) + "\n").encode("utf-8")
    (FIXTURE_DIR / "input.jsonl").write_bytes(input_bytes)
    (FIXTURE_DIR / "expected.jsonl").write_bytes(expected_bytes)

    manifest = {
        "schema_version": 0,
        "fixture_id": FIXTURE_ID,
        "created_utc": CREATED_UTC,
        "provenance": {
            "source": "baseline-bundle",
            "source_hash": sha256_bytes(CORPUS.read_bytes()),
            "derivation": "synthesized-from-baseline",
            "episode_id": "ep.000001",
            "notes": (
                "18-record segment regenerated from baselines/upstream-85cb050/"
                "event-corpus/bus-kinds.jsonl by tools/seed_baseline_fixture.py. "
                "input.jsonl holds the raw upstream records; expected.jsonl holds "
                "the canonical envelopes produced by contracts.eventmap.wrap."
            ),
        },
        "schema_pins": {
            "envelope_schema": "schemas/events/envelope.schema.json",
            "envelope_schema_version": 0,
            "event_map": "evtmap.upstream-bus",
            "event_map_upstream_revision": "85cb050",
        },
        "files": {
            "input.jsonl": sha256_bytes(input_bytes),
            "expected.jsonl": sha256_bytes(expected_bytes),
        },
        "expected_comparison": {"mode": "exact"},
    }
    (FIXTURE_DIR / "manifest.yaml").write_text(
        "# Fixture manifest per specs/001-fork-bootstrap-contracts/contracts/"
        "fixture-package.md\n# Generated from the sealed upstream baseline corpus; "
        "regenerate with tools/seed_baseline_fixture.py.\n"
        + yaml.safe_dump(manifest, sort_keys=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"{FIXTURE_ID}: wrote {len(input_lines)} records to {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
