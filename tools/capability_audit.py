#!/usr/bin/env python3
"""Capability coverage audit (feature 014; FR-1203, UR-BRN-016).

Diffs the bridge RPC surface against the capability catalog:

- default: sealed baseline ``baselines/upstream-85cb050/rpc-inventory.json``
- ``--live``: queries ``bridge.methods`` on the running bridge and reports
  drift (methods present live but absent from the baseline)

Every surface method MUST be mapped by a catalog entry — unmapped surface
fails the audit (exit 1) unless ``--allow-gaps`` is passed (report-only).
Catalog ``gap`` entries are honest inventory, not failures.

Usage:
    python tools/capability_audit.py [--live [BRIDGE_URL]] [--allow-gaps]
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "baselines" / "upstream-85cb050" / "rpc-inventory.json"
CATALOG = REPO / "components" / "rimbrain" / "capability-catalog.yaml"


def _load_catalog() -> dict:
    import yaml  # noqa: PLC0415
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


def _baseline_methods() -> list[str]:
    inv = json.loads(BASELINE.read_text(encoding="utf-8"))
    return sorted(i["name"] for i in inv)


def _live_methods(url: str) -> list[str]:
    body = json.dumps({"method": "bridge.methods", "params": {}}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/rpc", data=body,
        headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=8).read())
    return sorted(m["method"] for m in (res.get("result") or []))


def main(argv: list[str]) -> int:
    live_url = None
    allow_gaps = "--allow-gaps" in argv
    if "--live" in argv:
        i = argv.index("--live")
        live_url = argv[i + 1] if i + 1 < len(argv) \
            and not argv[i + 1].startswith("-") \
            else "http://127.0.0.1:8765"

    cat = _load_catalog()
    mapped: dict[str, list[str]] = {}
    gaps: list[dict] = []
    for e in cat.get("entries") or []:
        for m in e.get("bridge_methods") or []:
            mapped.setdefault(m, []).append(e["id"])
        if e.get("status") == "gap":
            gaps.append(e)

    baseline = _baseline_methods()
    unmapped = [m for m in baseline if m not in mapped]

    print(f"catalog v{cat.get('catalog_version')}: "
          f"{len(cat.get('entries') or [])} entries, "
          f"{len(cat.get('domains') or [])} domains")
    print(f"baseline surface: {len(baseline)} methods, "
          f"{len(baseline) - len(unmapped)} mapped")
    if unmapped:
        print("\nUNMAPPED baseline methods (must be catalogued):")
        for m in unmapped:
            print(f"  - {m}")

    if gaps:
        print(f"\nknown gaps ({len(gaps)}):")
        for e in gaps:
            ms = ", ".join(e.get("bridge_methods") or ["-"])
            print(f"  - {e['id']} [{', '.join(e.get('domains') or [])}]"
                  f" via {ms}")

    # per-domain coverage
    print("\nper-domain coverage:")
    for d in cat.get("domains") or []:
        es = [e for e in cat["entries"] if d in (e.get("domains") or [])]
        impl = sum(1 for e in es if e.get("status") == "implemented")
        print(f"  {d}: {impl}/{len(es)} implemented")

    drift = []
    if live_url:
        try:
            live = _live_methods(live_url)
        except Exception as ex:  # noqa: BLE001 — audit must report, not crash
            print(f"\nlive query failed: {ex}")
            return 2
        drift = [m for m in live if m not in baseline]
        gone = [m for m in baseline if m not in live]
        print(f"\nlive surface: {len(live)} methods")
        if drift:
            print("DRIFT — live methods absent from baseline "
                  "(need catalog entries):")
            for m in drift:
                print(f"  + {m}")
        if gone:
            print("baseline methods absent live:")
            for m in gone:
                print(f"  - {m}")

    if unmapped and not allow_gaps:
        return 1
    if drift and not allow_gaps:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
