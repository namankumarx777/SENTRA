"""Scenario 05 — Critical Asset Negative Space.

Situation injected by generator: within NEGATIVE_SPACE_ENTITIES, high- and
critical-criticality Cloud Resource / Database assets (and assets whose last
id digit is 0-2) are never chosen by alert generation. CSE-008 still owns
e.g. AST-000444 (critical, expected-monitored) with zero alerts, and 2+
such critical silent assets trigger NS002's high-severity absence signal.

Expected tool output:
- NS002 (critical asset with no security activity, severity High) for CSE-008
  with strong evidence strength.
- The silent critical asset appears as drill-down evidence.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=5,
    name="Critical assets with no security activity",
    story=(
        "Critical assets in CSE-008 record no security-alert activity for the "
        "whole six-month period. The corpus deliberately silences a set of "
        "high/critical Cloud and Database assets. The tool should emit NS002 "
        "(High) and expose the silent asset row as evidence."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase7", rule="NS002", entity="CSE-008"),
    ],
)