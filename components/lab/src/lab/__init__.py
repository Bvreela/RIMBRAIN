"""RimBrainAgent lab component: offline replay, fixtures, export, evaluation.

Owns the replayable fixture harness per specs/20-submodules/LAB.md and
specs/001-fork-bootstrap-contracts/contracts/fixture-package.md. Offline-first:
no game, bridge, model, or network access in replay paths.
"""

__all__ = ["run_fixture"]
__version__ = "0.1.0"


def __getattr__(name: str):
    # Lazy: keeps `python -m lab.fixtures` free of the double-import warning.
    if name == "run_fixture":
        from lab.fixtures import run_fixture

        return run_fixture
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
