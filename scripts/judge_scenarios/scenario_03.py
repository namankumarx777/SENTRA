"""Scenario 03 — Repeated Alerts Without Remediation.

Situation injected by generator: execution-gap entities record remediation
for 45% of closed cases (versus 72% elsewhere), and assets accumulate
repeated alerts whose cases have no recorded remediation.

Expected tool output:
- R003 (repeated alerts without remediation) fires for the relevant assets.
- EG003 (remediation execution gap) fires where the closed-case remediation
  rate drops below the 75% expectation, i.e. CSE-004 and CSE-011.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=3,
    name="Repeated alerts with no remediation",
    story=(
        "Assets accumulate repeated detections whose cases record no "
        "remediation, and the closed-case remediation rate in two entities "
        "sits far below the 75% supervisory minimum. The tool should expose "
        "the repeat-activity pattern (R003) and the entity remediation gap "
        "(EG003)."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase5", rule="R003", min_count=1),
        Expectation(kind="finding_present", phase="phase5", rule="R003", entity="CSE-004"),
        Expectation(kind="finding_present", phase="phase6", rule="EG003", min_count=1),
        Expectation(kind="finding_present", phase="phase6", rule="EG003", entity="CSE-004"),
        Expectation(kind="finding_present", phase="phase6", rule="EG003", entity="CSE-011"),
    ],
)