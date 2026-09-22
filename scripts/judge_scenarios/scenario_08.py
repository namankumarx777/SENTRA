"""Scenario 08 — Deferred Detector Honesty and Investigation-Effort Gap.

Situation injected by generator: INVESTIGATION_TEMPLATE_ENTITIES
(CSE-005, CSE-009) use templated investigation language, but the current
feature contract deliberately *(does not claim)* a documentation-quality
detector: EG005 and NS006 are defined and documented as deferred, with a
recorded reason. The investigation effort gap (EG002) is real for CSE-011.

Expected tool output:
- EG005 and NS006 produce ZERO findings (deferred, no fake negative space or
  weak documentation flagging).
- EG002 fires on CSE-011 (investigation effort materially below minimum).
- No findings parquet carries a ground-truth / control label column
  (instrumentation never leaks into analytical outputs).
"""

from scenarios import Expectation, Scenario

SCENARIO = Scenario(
    number=8,
    name="Deferred-detector honesty + investigation-effort gap",
    story=(
        "Two candidate detectors (EG005 documentation quality, NS006 "
        "escalation negative space) are explicitly deferred because the "
        "feature contract cannot defend them. The tool must not emit them, "
        "must still surface the real EG002 investigation-effort gap, and must "
        "never label outputs with the generator's control sets."
    ),
    expectations=[
        Expectation(kind="finding_absent", phase="phase6", rule="EG005"),
        Expectation(kind="finding_absent", phase="phase7", rule="NS006"),
        Expectation(kind="finding_present", phase="phase6", rule="EG002", entity="CSE-011"),
    ],
)