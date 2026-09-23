"""Consumer contract test (SC-003): a minimal consumer must reach identical
accept/reject verdicts on the corpus as the superproject corpus runner.

The consumer path here mimics any downstream component: load the example,
round-trip it through canonical JSON (RFC 8785) — the byte form records and
fixtures are hashed/stored in — then validate with jsonschema. The verdict is
compared 1:1 against ``tests/contract/corpus_runner.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

CONTRACTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTRACTS_DIR.parents[1]
sys.path.insert(0, str(CONTRACTS_DIR / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "contract"))

from contracts import canonical_bytes, canonical_hash

import corpus_runner


def _consumer_verdict(path: Path) -> bool:
    """Minimal consumer: canonical round-trip, then schema validation."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    instance = json.loads(canonical_bytes(raw).decode("utf-8"))
    schema_path = corpus_runner.schema_index()[corpus_runner.primitive_for(path)]
    validator = jsonschema.Draft202012Validator(corpus_runner.load_schema(schema_path))
    return not any(validator.iter_errors(instance))


def _cases():
    return sorted(
        corpus_runner.corpus_files(), key=lambda item: item[0].name
    )


@pytest.mark.parametrize(
    "path,expect_valid",
    _cases(),
    ids=[p.name for p, _ in _cases()],
)
def test_consumer_verdict_matches_runner(path: Path, expect_valid: bool) -> None:
    runner_accepted, _envelope = corpus_runner.file_verdict(path)
    consumer_accepted = _consumer_verdict(path)
    assert consumer_accepted == runner_accepted == expect_valid, (
        f"{path.name}: consumer={consumer_accepted} runner={runner_accepted} "
        f"expected={'accept' if expect_valid else 'reject'}"
    )


def test_corpus_is_nonempty() -> None:
    files = list(corpus_runner.corpus_files())
    assert any(ev for _, ev in files), "no valid examples found"
    assert any(not ev for _, ev in files), "no invalid examples found"


def test_canonical_hash_stable_per_file() -> None:
    for path, _ in corpus_runner.corpus_files():
        instance = json.loads(path.read_text(encoding="utf-8"))
        assert canonical_hash(instance) == canonical_hash(
            json.loads(canonical_bytes(instance).decode("utf-8"))
        )
