"""Replayable fixture harness (US5: FR-010, FR-011, FR-012, SC-005).

Implements the harness semantics of
``specs/001-fork-bootstrap-contracts/contracts/fixture-package.md``:

1. Load ``manifest.yaml`` and verify the sha256 of every declared member file.
2. Parse ``input.jsonl`` into canonical records. Each line is either a
   canonical envelope (``schemas/events/envelope.schema.json`` shape) or a raw
   upstream bus record ``{seq, t, kind, data, provenance}`` which is wrapped
   through ``contracts.eventmap.wrap`` when the sibling contracts package is
   importable.
3. Corruption fails closed with a named defect code (FR-011): hash mismatch,
   missing provenance, torn/truncated tail, undeclared member files, unknown
   schema_version, malformed manifest. Torn or invalid record lines are moved
   to ``quarantine/`` while the intact prefix still loads (FR-012 analog) — but
   no partial replay is ever reported as a pass.
4. Replay is offline: inputs are normalized to canonical records and compared
   against ``expected.jsonl`` under ``expected_comparison.mode``
   (``exact`` | ``field-subset``). ``exact`` compares canonical serialized
   equality; ``field-subset`` requires every expected field to be present and
   equal (recursively) in the observed record.
5. The report is deterministic JSON (sorted keys, no wall-clock or absolute
   paths inside the compared payload), so repeated replays are byte-identical
   (SC-005).

CLI: ``python -m lab.fixtures <fixture_dir> [--mode exact|field-subset]
[--report report.json] [--quarantine-dir DIR]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

HARNESS_NAME = "rimbrainagent-lab/fixtures"
HARNESS_VERSION = "0.1.0"

# Fixture contract revisions this harness understands (fixture-package.md 0.1.0).
KNOWN_SCHEMA_VERSIONS = {0}

MANIFEST_NAME = "manifest.yaml"
INPUT_NAME = "input.jsonl"
EXPECTED_NAME = "expected.jsonl"
QUARANTINE_NAME = "quarantine"

MODES = ("exact", "field-subset")

# common/id.schema.json grammar; fixture_id must additionally use the fix. kind.
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*\.[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PROVENANCE_SOURCES = {"baseline-bundle", "live-run", "synthesized"}

# Required envelope keys per schemas/events/envelope.schema.json. Checked
# structurally so the harness works without jsonschema; when the sibling
# contracts package is importable the full envelope schema is also applied.
ENVELOPE_REQUIRED = frozenset(
    {
        "schema_version",
        "event_id",
        "episode_id",
        "sequence",
        "event_type",
        "game_tick",
        "wall_time_utc",
        "source",
        "correlation",
        "revisions",
        "payload",
        "privacy",
    }
)

UPSTREAM_REQUIRED = frozenset({"seq", "t", "kind", "data"})

_MAX_DIFF_PATHS = 100
_MAX_SCHEMA_ERRORS = 5


# ---------------------------------------------------------------------------
# defects / report primitives
# ---------------------------------------------------------------------------


def _defect(code: str, message: str, **details: Any) -> dict:
    entry: dict[str, Any] = {"code": code, "message": message}
    if details:
        entry["details"] = details
    return entry


def _sort_key_defect(d: dict) -> tuple:
    details = d.get("details") or {}
    return (d["code"], str(details.get("member", "")), int(details.get("line", 0) or 0))


def _canon(obj: Any) -> str:
    """Deterministic serialization used for exact comparison and diffs."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _same(a: Any, b: Any) -> bool:
    return _canon(a) == _canon(b)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _emit_report(report: dict) -> bytes:
    """Deterministic report bytes: sorted keys, UTF-8, LF terminator."""
    return (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# optional contracts integration
# ---------------------------------------------------------------------------

_CONTRACTS_EVENTMAP = None
_CONTRACTS_PROBE_DONE = False


def _load_eventmap():
    """Import ``contracts.eventmap`` if the sibling contracts package is found.

    In-repo layout fallback: ``components/lab/src/lab/fixtures.py`` ->
    ``components/contracts/src``. Returns None when unavailable; callers fail
    closed with ``lab.contracts.unavailable`` for paths that need it.
    """
    global _CONTRACTS_EVENTMAP, _CONTRACTS_PROBE_DONE
    if _CONTRACTS_PROBE_DONE:
        return _CONTRACTS_EVENTMAP
    _CONTRACTS_PROBE_DONE = True
    try:
        from contracts import eventmap as em  # type: ignore

        _CONTRACTS_EVENTMAP = em
        return em
    except ImportError:
        pass
    candidate = Path(__file__).resolve().parents[3] / "contracts" / "src"
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        try:
            from contracts import eventmap as em  # type: ignore

            _CONTRACTS_EVENTMAP = em
        except ImportError:
            _CONTRACTS_EVENTMAP = None
    return _CONTRACTS_EVENTMAP


# ---------------------------------------------------------------------------
# manifest loading / member verification
# ---------------------------------------------------------------------------

_MANIFEST_REQUIRED = (
    "schema_version",
    "fixture_id",
    "created_utc",
    "provenance",
    "schema_pins",
    "files",
    "expected_comparison",
)


def _load_manifest(fixture_dir: Path, defects: list[dict]) -> dict | None:
    path = fixture_dir / MANIFEST_NAME
    if not path.is_file():
        defects.append(
            _defect("fixture.manifest.missing", f"{MANIFEST_NAME} not found", member=MANIFEST_NAME)
        )
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        defects.append(
            _defect(
                "fixture.manifest.unparseable",
                f"{MANIFEST_NAME} is not valid YAML: {exc}",
                member=MANIFEST_NAME,
            )
        )
        return None
    if not isinstance(doc, dict):
        defects.append(
            _defect(
                "fixture.manifest.invalid",
                f"{MANIFEST_NAME} must be a YAML mapping",
                member=MANIFEST_NAME,
            )
        )
        return None

    for key in _MANIFEST_REQUIRED:
        if key not in doc:
            code = (
                "fixture.provenance.missing"
                if key == "provenance"
                else "fixture.manifest.invalid"
            )
            defects.append(
                _defect(code, f"{MANIFEST_NAME} is missing required field {key!r}", field=key)
            )

    version = doc.get("schema_version")
    if version is not None:
        if not isinstance(version, int) or isinstance(version, bool):
            defects.append(
                _defect(
                    "fixture.manifest.invalid",
                    "schema_version must be an integer",
                    field="schema_version",
                )
            )
        elif version not in KNOWN_SCHEMA_VERSIONS:
            defects.append(
                _defect(
                    "fixture.schema_version.unknown",
                    f"unknown fixture schema_version {version!r}",
                    schema_version=version,
                )
            )

    fixture_id = doc.get("fixture_id")
    if fixture_id is not None:
        if (
            not isinstance(fixture_id, str)
            or not fixture_id.startswith("fix.")
            or _ID_PATTERN.match(fixture_id) is None
        ):
            defects.append(
                _defect(
                    "fixture.id.invalid",
                    f"fixture_id {fixture_id!r} violates the fix.* ID grammar",
                    fixture_id=fixture_id,
                )
            )

    created = doc.get("created_utc")
    if created is not None and (not isinstance(created, str) or not created.strip()):
        defects.append(
            _defect(
                "fixture.manifest.invalid", "created_utc must be a non-empty string", field="created_utc"
            )
        )

    provenance = doc.get("provenance")
    if provenance is not None:
        if not isinstance(provenance, dict) or not isinstance(provenance.get("source"), str) or not provenance.get("source"):
            defects.append(
                _defect(
                    "fixture.provenance.invalid",
                    "provenance must be a mapping with a non-empty 'source'",
                )
            )
        elif "source_hash" not in provenance:
            defects.append(
                _defect(
                    "fixture.provenance.invalid",
                    "provenance.source_hash is required",
                )
            )

    files = doc.get("files")
    if files is not None:
        if not isinstance(files, dict):
            defects.append(
                _defect("fixture.manifest.invalid", "files must be a path->sha256 mapping", field="files")
            )
        else:
            for member, digest in files.items():
                if not isinstance(member, str) or not isinstance(digest, str) or _SHA256_PATTERN.match(digest) is None:
                    defects.append(
                        _defect(
                            "fixture.manifest.invalid",
                            f"files entry {member!r} must map to a lowercase sha256 hex digest",
                            member=str(member),
                        )
                    )

    comparison = doc.get("expected_comparison")
    if comparison is not None:
        if not isinstance(comparison, dict) or comparison.get("mode") not in MODES:
            defects.append(
                _defect(
                    "fixture.comparison.mode_unknown",
                    "expected_comparison.mode must be one of exact|field-subset",
                )
            )
    return doc


def _valid_member_path(member: str) -> bool:
    if not member or member in (".", MANIFEST_NAME):
        return False
    p = Path(member)
    if p.is_absolute() or "\\" in member:
        return False
    return all(part not in ("", ".", "..") for part in member.split("/"))


def _verify_files(fixture_dir: Path, files: dict, quarantine_dir: Path, defects: list[dict]) -> None:
    for member, expected_sha in sorted(files.items()):
        if not _valid_member_path(member):
            defects.append(
                _defect(
                    "fixture.file.invalid_path",
                    f"declared member path {member!r} is not a safe relative path",
                    member=str(member),
                )
            )
            continue
        path = fixture_dir / member
        if not path.is_file():
            defects.append(
                _defect(
                    "fixture.file.missing",
                    f"declared member {member!r} does not exist",
                    member=member,
                )
            )
            continue
        actual = _sha256_file(path)
        if actual != expected_sha:
            defects.append(
                _defect(
                    "fixture.hash.mismatch",
                    f"sha256 of {member!r} does not match manifest",
                    member=member,
                    expected=expected_sha,
                    actual=actual,
                )
            )

    # every member file must be declared (fixture-package.md); quarantine/ is
    # a load-time output dir, never a hashed input
    q_root = quarantine_dir.resolve()
    for path in sorted(fixture_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        rel = path.relative_to(fixture_dir).as_posix()
        if rel == MANIFEST_NAME or rel.split("/")[0] == QUARANTINE_NAME:
            continue
        if q_root in resolved.parents or resolved == q_root:
            continue
        if rel not in files:
            defects.append(
                _defect(
                    "fixture.file.undeclared",
                    f"member file {rel!r} is not listed in manifest files",
                    member=rel,
                )
            )


# ---------------------------------------------------------------------------
# input.jsonl parsing: canonical envelopes or raw upstream records
# ---------------------------------------------------------------------------


def _quarantine_line(
    quarantine_dir: Path,
    quarantined: list[dict],
    member: str,
    lineno: int,
    raw: bytes,
    code: str,
) -> None:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    name = f"{member}.line-{lineno:04d}.raw"
    (quarantine_dir / name).write_bytes(raw)
    quarantined.append(
        {"code": code, "file": f"{QUARANTINE_NAME}/{name}", "line": lineno, "member": member}
    )


def _classify_record(obj: Any) -> str:
    if not isinstance(obj, dict):
        return "invalid"
    if "event_type" in obj or "schema_version" in obj:
        return "envelope"
    if "kind" in obj and "seq" in obj:
        return "upstream"
    return "invalid"


def _load_records(
    path: Path,
    member: str,
    quarantine_dir: Path,
    defects: list[dict],
    quarantined: list[dict],
) -> list[dict] | None:
    """Parse a .jsonl member into canonical records.

    Returns the list of canonical records loaded (the intact prefix plus any
    individually valid later lines), or None if the member is absent. Bad lines
    are quarantined and recorded as defects; the caller fails closed on any
    defect so a salvageable load is never reported as a pass.
    """
    if not path.is_file():
        defects.append(
            _defect("fixture.file.missing", f"required member {member!r} not found", member=member)
        )
        return None

    raw = path.read_bytes()
    lines = raw.split(b"\n")
    if lines and lines[-1].strip() == b"":
        lines.pop()  # a single trailing newline ends the last record, not a new one
    last_index = len(lines) - 1

    parsed: list[tuple[int, Any]] = []
    for index, raw_line in enumerate(lines):
        lineno = index + 1
        if raw_line.strip() == b"":
            continue
        try:
            obj = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            # A truncated/garbage final line is the torn tail of FR-012; a bad
            # line earlier in the stream is an unparseable record. Either way
            # the bytes are isolated in quarantine/ and the run fails closed.
            code = (
                f"fixture.{path.stem}.torn_tail"
                if index == last_index
                else "fixture.record.unparseable"
            )
            defects.append(
                _defect(
                    code,
                    f"{member} line {lineno} is not parseable JSON",
                    member=member,
                    line=lineno,
                )
            )
            _quarantine_line(quarantine_dir, quarantined, member, lineno, raw_line, code)
            continue
        parsed.append((lineno, obj))

    if member != INPUT_NAME:
        # expected.jsonl lines are compared, not normalized; they only need to
        # be JSON objects (field-subset mode intentionally stores partials).
        records = []
        for lineno, obj in parsed:
            if not isinstance(obj, dict):
                code = "fixture.expected.record_invalid"
                defects.append(
                    _defect(
                        code,
                        f"{member} line {lineno} is not a JSON object",
                        member=member,
                        line=lineno,
                    )
                )
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
            else:
                records.append(obj)
        return records

    records = []
    previous_seq: int | None = None
    contracts_needed_reported = False
    for lineno, obj in parsed:
        shape = _classify_record(obj)
        record: dict | None = None
        if shape == "envelope":
            missing = sorted(ENVELOPE_REQUIRED - set(obj))
            if missing:
                code = "fixture.envelope.invalid"
                defects.append(
                    _defect(
                        code,
                        f"{member} line {lineno} envelope is missing keys {missing}",
                        member=member,
                        line=lineno,
                        missing=missing,
                    )
                )
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
                continue
            eventmap = _load_eventmap()
            if eventmap is not None:
                errors = eventmap.validate_envelope(obj)
                if errors:
                    code = "fixture.envelope.invalid"
                    defects.append(
                        _defect(
                            code,
                            f"{member} line {lineno} rejected by events/envelope schema",
                            member=member,
                            line=lineno,
                            errors=errors[:_MAX_SCHEMA_ERRORS],
                        )
                    )
                    _quarantine_line(
                        quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                    )
                    continue
            record = obj
        elif shape == "upstream":
            missing = sorted(UPSTREAM_REQUIRED - set(obj))
            if missing:
                code = "fixture.record.invalid"
                defects.append(
                    _defect(
                        code,
                        f"{member} line {lineno} upstream record is missing keys {missing}",
                        member=member,
                        line=lineno,
                        missing=missing,
                    )
                )
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
                continue
            if "provenance" not in obj:
                code = "fixture.record.provenance_missing"
                defects.append(
                    _defect(
                        code,
                        f"{member} line {lineno} upstream record carries no provenance",
                        member=member,
                        line=lineno,
                    )
                )
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
                continue
            eventmap = _load_eventmap()
            if eventmap is None:
                if not contracts_needed_reported:
                    contracts_needed_reported = True
                    defects.append(
                        _defect(
                            "lab.contracts.unavailable",
                            "raw upstream records require the contracts package "
                            "(components/contracts/src) on sys.path",
                            member=member,
                            line=lineno,
                        )
                    )
                code = "fixture.record.invalid"
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
                continue
            try:
                record = eventmap.wrap(obj)
            except Exception as exc:  # eventmap.EventMapError or missing fields
                code = "fixture.record.invalid"
                defects.append(
                    _defect(
                        code,
                        f"{member} line {lineno} failed canonical wrap: {exc}",
                        member=member,
                        line=lineno,
                    )
                )
                _quarantine_line(
                    quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
                )
                continue
        else:
            code = "fixture.record.invalid"
            defects.append(
                _defect(
                    code,
                    f"{member} line {lineno} is neither a canonical envelope nor "
                    "an upstream {seq,t,kind,data} record",
                    member=member,
                    line=lineno,
                )
            )
            _quarantine_line(
                quarantine_dir, quarantined, member, lineno, lines[lineno - 1], code
            )
            continue

        sequence = record.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            defects.append(
                _defect(
                    "fixture.sequence.violation",
                    f"{member} line {lineno} has no integer sequence",
                    member=member,
                    line=lineno,
                )
            )
        else:
            if previous_seq is not None and sequence != previous_seq + 1:
                defects.append(
                    _defect(
                        "fixture.sequence.violation",
                        f"{member} sequence gap/decrease {previous_seq} -> {sequence} "
                        f"at line {lineno}",
                        member=member,
                        line=lineno,
                        previous=previous_seq,
                        sequence=sequence,
                    )
                )
            previous_seq = sequence
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------


def _is_subset(expected: Any, observed: Any) -> bool:
    if isinstance(expected, dict):
        return (
            isinstance(observed, dict)
            and all(k in observed for k in expected)
            and all(_is_subset(v, observed[k]) for k, v in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(_is_subset(e, o) for e, o in zip(expected, observed))
        )
    return _same(expected, observed)


def _diff_paths(expected: Any, observed: Any, prefix: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(observed, dict):
        out: list[str] = []
        for key in sorted(set(expected) | set(observed), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in expected or key not in observed:
                out.append(path)
            else:
                out.extend(_diff_paths(expected[key], observed[key], path))
            if len(out) >= _MAX_DIFF_PATHS:
                return out
        return out
    if _same(expected, observed):
        return []
    return [prefix or "/"]


def _compare(observed: list[dict], expected: list[dict], mode: str) -> dict:
    lines = []
    counts = {"equivalent": 0, "divergent": 0, "missing_expected": 0, "missing_observed": 0}
    total = max(len(observed), len(expected))
    for index in range(total):
        obs = observed[index] if index < len(observed) else None
        exp = expected[index] if index < len(expected) else None
        record_id = None
        for side in (obs, exp):
            if isinstance(side, dict) and isinstance(side.get("event_id"), str):
                record_id = side["event_id"]
                break
        if record_id is None:
            record_id = f"line-{index + 1}"
        entry: dict[str, Any] = {"line": index + 1, "record_id": record_id}
        if obs is None:
            entry["result"] = "missing_observed"
            counts["missing_observed"] += 1
        elif exp is None:
            entry["result"] = "missing_expected"
            counts["missing_expected"] += 1
        else:
            ok = _same(obs, exp) if mode == "exact" else _is_subset(exp, obs)
            if ok:
                entry["result"] = "equivalent"
                counts["equivalent"] += 1
            else:
                entry["result"] = "divergent"
                entry["diff_paths"] = _diff_paths(exp, obs)
                counts["divergent"] += 1
        lines.append(entry)
    return {"counts": counts, "lines": lines}


# ---------------------------------------------------------------------------
# harness entry point
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_DIVERGED = 1
EXIT_FAILED = 2


def run_fixture(
    fixture_dir: Path | str,
    mode: str | None = None,
    quarantine_dir: Path | str | None = None,
) -> tuple[dict, bytes]:
    """Replay one fixture package and return ``(report, report_bytes)``.

    ``report_bytes`` is the deterministic JSON serialization written by
    ``--report``; byte-identical across replays of an unchanged fixture.
    """
    fixture_dir = Path(fixture_dir)
    q_dir = Path(quarantine_dir) if quarantine_dir else fixture_dir / QUARANTINE_NAME

    defects: list[dict] = []
    quarantined: list[dict] = []
    report: dict[str, Any] = {
        "harness": {"name": HARNESS_NAME, "version": HARNESS_VERSION},
        "fixture_id": None,
        "mode": None,
        "status": "failed",
        "defects": defects,
        "quarantine": quarantined,
        "records": {"input": 0, "expected": 0},
        "comparison": None,
    }

    if not fixture_dir.is_dir():
        defects.append(
            _defect("fixture.dir.missing", f"fixture directory {fixture_dir} not found")
        )
        defects.sort(key=_sort_key_defect)
        return report, _emit_report(report)

    manifest = _load_manifest(fixture_dir, defects)
    if manifest is not None:
        report["fixture_id"] = manifest.get("fixture_id")
        files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
        _verify_files(fixture_dir, files, q_dir, defects)
        chosen_mode = mode or (manifest.get("expected_comparison") or {}).get("mode")
        report["mode"] = chosen_mode if chosen_mode in MODES else None

        observed = _load_records(
            fixture_dir / INPUT_NAME, INPUT_NAME, q_dir, defects, quarantined
        )
        expected = _load_records(
            fixture_dir / EXPECTED_NAME, EXPECTED_NAME, q_dir, defects, quarantined
        )
        report["records"]["input"] = len(observed) if observed is not None else 0
        report["records"]["expected"] = len(expected) if expected is not None else 0

        if not defects and observed is not None and expected is not None:
            comparison = _compare(observed, expected, report["mode"])
            report["comparison"] = comparison
            divergent = (
                comparison["counts"]["divergent"]
                + comparison["counts"]["missing_expected"]
                + comparison["counts"]["missing_observed"]
            )
            report["status"] = "diverged" if divergent else "ok"

    defects.sort(key=_sort_key_defect)
    quarantined.sort(key=lambda q: (q["member"], q["line"]))
    return report, _emit_report(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lab.fixtures",
        description="Offline deterministic replay of a fixture package "
        "(contracts/fixture-package.md).",
    )
    parser.add_argument("fixture_dir", help="path to the fix.* fixture directory")
    parser.add_argument(
        "--mode",
        choices=MODES,
        default=None,
        help="comparison mode override (default: manifest expected_comparison.mode)",
    )
    parser.add_argument("--report", default=None, help="write the JSON report to this path")
    parser.add_argument(
        "--quarantine-dir",
        default=None,
        help="where torn/invalid records are isolated (default: <fixture>/quarantine)",
    )
    args = parser.parse_args(argv)

    report, blob = run_fixture(
        args.fixture_dir, mode=args.mode, quarantine_dir=args.quarantine_dir
    )
    if args.report:
        Path(args.report).write_bytes(blob)
    else:
        sys.stdout.buffer.write(blob)
    counts = (report.get("comparison") or {}).get("counts") or {}
    print(
        f"{report['fixture_id'] or args.fixture_dir}: {report['status']} "
        f"(equivalent={counts.get('equivalent', 0)} "
        f"divergent={counts.get('divergent', 0)} "
        f"defects={len(report['defects'])} quarantined={len(report['quarantine'])})",
        file=sys.stderr,
    )
    return {"ok": EXIT_OK, "diverged": EXIT_DIVERGED}.get(report["status"], EXIT_FAILED)


if __name__ == "__main__":
    raise SystemExit(main())
