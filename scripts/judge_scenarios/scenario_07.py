"""Scenario 07 — Contextual Anomaly Surface and Review Queue.

Situation injected by generator: rapid-closure + short-investigation +
low-remediation patterns inside CSE-004 and CSE-011 combine into an
entity-level deviation that the Isolation Forest (AN001) picks up, and those
entities top the supervisory review queue by priority score.

Expected tool output:
- AN001 fires (contextual anomaly) on the deviating entities.
- CSE-011 (the aggregate-risk leader on the shipped corpus) is banded HIGH
  and its review-queue urgency reflects the corroborated signals.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=7,
    name="Contextual anomaly corroborates review-queue priority",
    story=(
        "An entity whose execution-gap and negative-space signals combine is "
        "flagged by the contextual anomaly detector and corroborated into a "
        "high-priority review-queue position. The tool should place CSE-011 "
        "in the HIGH band with a substantive queue priority."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase8", rule="AN001", min_count=1),
        Expectation(kind="risk_band", phase="phase9", entity="CSE-011", band="HIGH"),
        Expectation(kind="queue_urgency_at_least", phase="phase9", entity="CSE-011", min_urgency=3),
    ],
)