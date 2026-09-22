"""Scenario 04 — Monitoring Coverage Gap (expected evidence absent).

Situation injected by generator: NEGATIVE_SPACE_ENTITIES (CSE-007, CSE-008)
exclude a subset of high/critical Cloud/Database assets from alert activity,
so those assets are expected-but-monitored yet silent, and generic
Cloud Security telemetry is redirected away for CSE-007/CSE-008.

Expected tool output:
- R005 (very low monitoring activity on expected-monitored assets) on
  CSE-007 and CSE-008.
- NS001 (expected-monitored asset with no activity) on CSE-007 and CSE-008.
- NS003 (missing telemetry category blindspot) on CSE-007 and CSE-008.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=4,
    name="Monitoring coverage gap (absent expected evidence)",
    story=(
        "A subset of critical Cloud/Database assets in CSE-007 and CSE-008 "
        "show no alert activity during the entire period, and Cloud Security "
        "telemetry source is suppressed for those entities. The tool should "
        "flag low monitored-asset activity (R005), silent expected-monitored "
        "assets (NS001), and the telemetry category blindspot (NS003)."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase5", rule="R005", entity="CSE-007"),
        Expectation(kind="finding_present", phase="phase5", rule="R005", entity="CSE-008"),
        Expectation(kind="finding_present", phase="phase7", rule="NS001", entity="CSE-007"),
        Expectation(kind="finding_present", phase="phase7", rule="NS001", entity="CSE-008"),
        Expectation(kind="finding_present", phase="phase7", rule="NS003", entity="CSE-008"),
    ],
)