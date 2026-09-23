"""Path setup for lab tests: lab + sibling contracts sources on sys.path."""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
LAB_DIR = TESTS_DIR.parent  # components/lab
COMPONENTS_DIR = LAB_DIR.parent
REPO_ROOT = COMPONENTS_DIR.parent

for path in (LAB_DIR / "src", COMPONENTS_DIR / "contracts" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
