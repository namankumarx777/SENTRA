"""Scenario 06 — Peer Benchmarking and Deviation.

Situation injected by generator: PEER_DEVIATION_ENTITIES (CSE-003, CSE-010)
get short investigation minutes and reduced escalation probability for
high/critical cases, and CSE-010/CSE-011 carry coverage or volume patterns
that deviate from structural peers. Cohorts are formed on
sector + size + criticality with a minimum of 3 peers.

Expected tool output:
- At least one PB* (peer benchmark) finding, and PB001/PB002/PB003
  specifically on the deviating entities (CSE-010, CSE-011, CSE-012).
- A nonzero cohort count recorded in the manifest.
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=6,
    name="Peer benchmarking flags deviating entities",
    story=(
        "Two entities deviate structurally from their peer cohorts on "
        "investigation duration, escalation behaviour, or monitoring metrics. "
        "The tool's Phase 8 peer benchmarks (PB001-PB003) should surface the "
        "deviating entities against sector/size/criticality cohorts."
    ),
    expectations=[
        Expectation(kind="finding_present", phase="phase8", rule="PB001", min_count=1),
        Expectation(kind="finding_present", phase="phase8", rule="PB002", min_count=1),
        Expectation(kind="finding_present", phase="phase8", rule="PB003", min_count=1),
        Expectation(kind="finding_present", phase="phase8", rule="PB001", entity="CSE-010"),
    ],
)