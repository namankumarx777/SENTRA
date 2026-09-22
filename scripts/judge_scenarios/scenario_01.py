"""Scenario 01 — Rapid Closure Detection.

Situation injected by generator: EXECUTION_GAP_ENTITIES (CSE-004, CSE-011)
include rapid critical-case closures (every 4th critical alert in those
entities is closed in ≤ 9 minutes). CSE-010 also appears in R004 due to
short investigation durations on high/critical cases.

Expected tool output:
- R001 fires for CSE-004/CSE-011 (rapid closure rule).
- R004 fires for CSE-004/CSE-010/CSE-011 (investigation duration proxy).
- The rapid-closure entities appear in the review queue.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=1,
    name="Rapid closure of critical alerts",
    story=(
        "CSE-004 and CSE-011 exhibit rapid critical-case closure patterns "
        "injected by the generator (closed within minutes of opening). "
        "The tool should flag R001 (rapid closure rule) for both and R004 "
        "(short investigation duration proxy) including CSE-010."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase5", rule="R001", min_count=1),
        Expectation(kind="finding_present", phase="phase5", rule="R001", entity="CSE-004"),
        Expectation(kind="finding_present", phase="phase5", rule="R001", entity="CSE-011"),
        Expectation(kind="finding_present", phase="phase5", rule="R004", min_count=1),
        Expectation(kind="finding_present", phase="phase5", rule="R004", entity="CSE-011"),
        Expectation(kind="finding_present", phase="phase5", rule="R004", entity="CSE-010"),
        Expectation(kind="queue_urgency_at_least", phase="phase9", entity="CSE-011", min_urgency=3),
    ],
)