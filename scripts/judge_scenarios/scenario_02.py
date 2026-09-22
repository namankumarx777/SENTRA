"""Scenario 02 — Escalation Absence for Critical Alerts.

Situation injected by generator: critical/high cases in some entities are
escalated at 32% probability (execution-gap entities) versus 68%
elsewhere; immediately-closed critical alerts leave no escalation record.

Expected tool output:
- R002 (critical alert without escalation) fires broadly; at least CSE-011.
- EG001 (critical escalation execution gap) fires for entities whose
  escalation rate is materially below expectation, including CSE-010/CSE-011.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=2,
    name="Critical alerts closed without escalation",
    story=(
        "Critical cases are closed without any escalation record, and whole "
        "entities run escalation rates materially below the supervisory "
        "expectation (60%). The tool should surface R002 per case and EG001 "
        "per entity."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase5", rule="R002", min_count=1),
        Expectation(kind="finding_present", phase="phase5", rule="R002", entity="CSE-011"),
        Expectation(kind="finding_present", phase="phase6", rule="EG001", min_count=1),
        Expectation(kind="finding_present", phase="phase6", rule="EG001", entity="CSE-011"),
    ],
)