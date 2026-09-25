"""Validation entry point for components/lab (FR-003).

Runs the real fixture-harness suite via uv when available (isolated env from
this component's pyproject), else falls back to `python -m pytest`. Offline:
no game, model, network, or secrets. Invoked by tools/validate_components.py.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

if not (HERE / "tests").is_dir():
    print("validate:lab ok (no tests dir)")
    sys.exit(0)

if shutil.which("uv"):
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = (
        f"{HERE / 'src'};{REPO_ROOT / 'components' / 'contracts' / 'src'}"
        + ";" + env.get("PYTHONPATH", "")
    )
    rc = subprocess.run(
        ["uv", "run", "--with", "pytest,pyyaml,jsonschema", "pytest", "tests", "-q"],
        cwd=HERE, env=env,
    ).returncode
else:
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"], cwd=HERE
    ).returncode

print(f"validate:lab {'ok' if rc == 0 else 'FAIL'}")
sys.exit(rc)
