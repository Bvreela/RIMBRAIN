#!/usr/bin/env python3
"""Contract corpus runner (quickstart.md section 5).

Usage:
    python tests/contract/corpus_runner.py validate-corpus

Validates every ``components/contracts/examples/valid/*.json`` against its
schema in ``components/contracts/schemas/**`` (must pass) and every
``examples/invalid/*.json`` (must fail with ``{ok:false,error:{code,...}}``).

Schema resolution: the filename prefix before the first ``.`` names the
primitive (``id.valid.01.json`` -> ``schemas/**/id.schema.json``).

Exit codes: 0 when every file behaves as its directory declares, 1 otherwise,
2 for usage/setup errors. Per-file PASS/FAIL summary is printed to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "components" / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"

CORPUS_DIRS = {"valid": True, "invalid": False}


def error_envelope(code: str, message: str, retryable: bool = False, details: dict | None = None) -> dict:
    """The one failure grammar shared from bridge boundary to contract validation."""
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


def schema_index() -> dict[str, Path]:
    """Map primitive name -> schema path across the schemas/ tree."""
    index: dict[str, Path] = {}
    for path in sorted(SCHEMAS_DIR.rglob("*.schema.json")):
        name = path.name[: -len(".schema.json")]
        index.setdefault(name, path)
    return index


def corpus_files(examples_dir: Path = EXAMPLES_DIR) -> Iterator[tuple[Path, bool]]:
    """Yield (example path, expected_valid) for every corpus file."""
    for dirname, expect_valid in CORPUS_DIRS.items():
        folder = examples_dir / dirname
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            yield path, expect_valid


def primitive_for(path: Path) -> str:
    """Schema name = filename prefix before the first '.'.

    Event-payload corpus cases use the ``ev__`` escape: the name between
    ``ev__`` and the ``.valid.``/``.invalid.`` marker is the dotted event type
    resolved under ``schemas/events/types/`` (e.g.
    ``ev__action.issued.valid.01.json`` -> ``action.issued.schema.json``).
    """
    name = path.name
    if name.startswith("ev__"):
        for marker in (".valid.", ".invalid."):
            if marker in name:
                return name[len("ev__"):name.index(marker)]
        return name[len("ev__"):]
    return name.split(".", 1)[0]


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_instance(schema: dict, instance: Any) -> list[str]:
    """Return sorted validation error messages; empty list means accepted."""
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '/'}: {e.message}"
        for e in validator.iter_errors(instance)
    )


def file_verdict(path: Path, index: dict[str, Path] | None = None) -> tuple[bool, dict | None]:
    """Return (accepted, error_envelope_or_none) for one corpus file."""
    index = schema_index() if index is None else index
    schema_path = index.get(primitive_for(path))
    if schema_path is None:
        return False, error_envelope(
            "corpus.schema.unresolved",
            f"No schema found for primitive '{primitive_for(path)}' under {SCHEMAS_DIR}",
            details={"file": path.name},
        )
    try:
        instance = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, error_envelope(
            "corpus.example.unparseable",
            f"Example is not parseable JSON: {exc}",
            details={"file": path.name},
        )
    errors = validate_instance(load_schema(schema_path), instance)
    if errors:
        return False, error_envelope(
            "contract.validation.failed",
            f"{primitive_for(path)} instance rejected by {schema_path.name}",
            details={"file": path.name, "errors": errors},
        )
    return True, None


def validate_corpus() -> int:
    if not EXAMPLES_DIR.is_dir():
        print(json.dumps(error_envelope("corpus.dir.missing", f"{EXAMPLES_DIR} does not exist")))
        return 2
    index = schema_index()
    total = 0
    mismatches: list[Path] = []
    for path, expect_valid in corpus_files():
        total += 1
        accepted, envelope = file_verdict(path, index)
        ok = accepted == expect_valid
        rel = path.relative_to(REPO_ROOT)
        if ok:
            note = "accepted" if accepted else "rejected"
            print(f"PASS {rel} ({note} as expected)")
        else:
            mismatches.append(path)
            note = "accepted but must reject" if accepted else "rejected but must accept"
            print(f"FAIL {rel} ({note})")
            if envelope is not None:
                print(f"     {json.dumps(envelope, ensure_ascii=False)}")
        if not accepted and expect_valid is False and envelope is not None:
            # Show the structured rejection grammar for expected failures too.
            print(f"     -> {json.dumps(envelope, ensure_ascii=False)}")
    valid_total = sum(1 for _, ev in corpus_files() if ev)
    invalid_total = total - valid_total
    print(
        f"corpus: {total} files ({valid_total} valid, {invalid_total} invalid); "
        f"{total - len(mismatches)} correct, {len(mismatches)} mismatched"
    )
    return 0 if total > 0 and not mismatches else 1


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "validate-corpus"
    if command == "validate-corpus":
        return validate_corpus()
    print(f"unknown command: {command} (expected: validate-corpus)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
