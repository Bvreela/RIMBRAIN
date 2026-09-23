"""Schema-drift contract test (FR-006, envelope contract §Validation).

A canonical record declaring ``schema_version`` above the strict consumer's
maximum must be rejected with the explicit shared failure grammar
``{ok:false, error:{code:"schema.version.too_new", ...}}`` — never a silent
pass or a silent misread. The split is deliberate: the envelope schema has no
``maximum`` bound (archival readers preserve newer records losslessly); the
version ceiling is consumer policy enforced by
``contracts.eventmap.consume_strict``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

CONTRACTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTRACTS_DIR.parents[1]
sys.path.insert(0, str(CONTRACTS_DIR / "src"))

from contracts import eventmap

ERROR_SCHEMA = json.loads(
    (CONTRACTS_DIR / "schemas" / "common" / "error.schema.json").read_text(
        encoding="utf-8"
    )
)
CORPUS_PATH = (
    REPO_ROOT / "baselines" / "upstream-85cb050" / "event-corpus" / "bus-kinds.jsonl"
)


def _record() -> dict:
    original = json.loads(CORPUS_PATH.read_text(encoding="utf-8").splitlines()[0])
    return eventmap.wrap(original)


def _assert_error_envelope(verdict: dict, code: str) -> None:
    assert verdict["ok"] is False
    assert verdict["error"]["code"] == code
    assert verdict["error"]["retryable"] is False
    # The failure itself must conform to common/error — machine-readable, never
    # a free-form string (FR-006).
    jsonschema.Draft202012Validator(ERROR_SCHEMA).validate(verdict)


def test_too_new_schema_version_rejected_with_named_code() -> None:
    record = _record()
    record["schema_version"] = eventmap.SCHEMA_VERSION + 1

    verdict = eventmap.consume_strict(record)

    _assert_error_envelope(verdict, "schema.version.too_new")
    assert verdict["error"]["details"] == {
        "schema_version": eventmap.SCHEMA_VERSION + 1,
        "consumer_max": eventmap.SCHEMA_VERSION,
    }


def test_too_new_record_still_validates_for_storage() -> None:
    # Store-not-execute split: the archival path has no version ceiling, so the
    # newer record is preserved losslessly while the strict consumer rejects it.
    record = _record()
    record["schema_version"] = eventmap.SCHEMA_VERSION + 1
    assert eventmap.validate_envelope(record) == []


def test_consumer_max_is_configurable() -> None:
    record = _record()
    assert eventmap.consume_strict(record, max_schema_version=5)["ok"] is True
    _assert_error_envelope(
        eventmap.consume_strict(record, max_schema_version=-1),
        "schema.version.too_new",
    )


def test_current_version_accepted() -> None:
    record = _record()
    assert record["schema_version"] == eventmap.SCHEMA_VERSION
    verdict = eventmap.consume_strict(record)
    assert verdict == {"ok": True, "result": record}


def test_missing_or_non_integer_version_rejected() -> None:
    record = _record()
    del record["schema_version"]
    _assert_error_envelope(
        eventmap.consume_strict(record), "contract.validation.failed"
    )
    record = _record()
    record["schema_version"] = "0"
    _assert_error_envelope(
        eventmap.consume_strict(record), "contract.validation.failed"
    )


def test_envelope_violations_rejected_explicitly() -> None:
    # additionalProperties: false — an unknown newer field is an explicit
    # rejection, never silent data loss (VERSIONING.md consumer rules).
    record = _record()
    record["future_field"] = {"anything": True}
    verdict = eventmap.consume_strict(record)
    _assert_error_envelope(verdict, "contract.validation.failed")
    assert "future_field" in json.dumps(verdict["error"]["details"])
