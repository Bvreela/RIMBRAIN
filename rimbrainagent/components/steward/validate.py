"""No-op validation shell for components/steward (FR-003).

Placeholder self-check: passes with no game, model, network, or secret
dependencies. Replaced by the component's real validator when the component
repository lands. Invoked by tools/validate_components.py.
"""

import sys

print("validate:steward ok (no-op shell; placeholder component)")
sys.exit(0)
