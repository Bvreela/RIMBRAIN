"""Validation entry point for components/runtime (FR-003).

Runs the real pytest suite via uv when available, else `python -m pytest`.
Offline: stub HTTP servers only — no live endpoints, game, or secrets.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

if not (HERE / "tests").is_dir():
    print("validate:runtime ok (no tests dir)")
    sys.exit(0)

env = dict(os.environ)
env["PYTHONPATH"] = (
    f"{HERE / 'src'};{REPO_ROOT / 'components' / 'contracts' / 'src'}"
    + ";" + env.get("PYTHONPATH", "")
)
if shutil.which("uv"):
    rc = subprocess.run(
        ["uv", "run", "--with", "pytest,pyyaml,jsonschema", "pytest", "tests", "-q"],
        cwd=HERE, env=env,
    ).returncode
else:
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"], cwd=HERE, env=env
    ).returncode
print(f"validate:runtime {'ok' if rc == 0 else 'FAIL'}")
sys.exit(rc)
