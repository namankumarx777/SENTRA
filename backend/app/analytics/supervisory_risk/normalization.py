from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.analytics.supervisory_risk.config import (
    ANOMALY_SCORE_CEILING,
    SEVERITY_WEIGHTS,
)
from app.analytics.supervisory_risk.inputs import StandardizedFinding


@dataclass
class NormalizedSignal:
    entity_id: str
    detector_id: str
    source_phase: str
    signal_name: str
    raw_value: float | int | str | None
    normalized_value: float  # Bounded strictly 0.0 to 100.0
    severity: str
    evidence_strength: str | None
    assessment_strength: str  # "Low", "Medium", "High"
    supporting_finding_ids: list[str] = field(default_factory=list)
    contributing_features: list[str] = field(default_factory=list)
    rationale: str = ""
    is_assessable: bool = True
    unassessable_reason: str | None = None


SignalNormalizer = Callable[
    [StandardizedFinding, dict[str, Any], list[StandardizedFinding]],
    NormalizedSignal,
]


def _derive_assessment_strength(evidence_strength: str | None, sample_size: int | None) -> str:
    """Explicit deterministic assessment strength rule (not statistical confidence)."""
    if evidence_strength == "High":
        return "High"
    if evidence_strength == "Medium":
        return "Medium"
    if evidence_strength == "Low":
        return "Low"
    # Fallback for Phase 5 (where evidence_strength is None) based on sample support
    if sample_size is not None and sample_size >= 10:
        return "Medium"
    return "Low"


def _unassessable(
    finding: StandardizedFinding,
    *,
    signal_name: str,
    raw_value: float | int | str | None,
    reason: str,
    supporting_finding_ids: list[str] | None = None,
    severity: str | None = None,
    evidence_strength: str | None = None,
) -> NormalizedSignal:
    """Explicit "no risk assigned" signal. Never silently fabricates a number."""
    return NormalizedSignal(
        entity_id=finding.entity_id,
        detector_id=finding.rule_id,
        source_phase=finding.source_phase,
        signal_name=signal_name,
        raw_value=raw_value,
        normalized_value=0.0,
        severity=severity or finding.severity,
        evidence_strength=evidence_strength,
        assessment_strength="Low",
        supporting_finding_ids=supporting_finding_ids or [finding.id],
        is_assessable=False,
        unassessable_reason=reason,
    )


def _prevalence_signal(
    finding: StandardizedFinding,
    by_detector: list[StandardizedFinding],
    *,
    signal_name: str,
    denominator: int,
    unassessable_reason: str,
    rationale_template: str,
) -> NormalizedSignal:
    finding_ids = [f.id for f in by_detector]
    finding_count = len(by_detector)
    if denominator == 0:
        return _unassessable(
            finding,
            signal_name=signal_name,
            raw_value=finding_count,
            reason=unassessable_reason,
            supporting_finding_ids=finding_ids,
        )
    prevalence = min(1.0, finding_count / denominator)
    norm_val = round(prevalence * 100.0, 2)
    strength = _derive_assessment_strength(None, denominator)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name=signal_name, raw_value=finding_count, normalized_value=norm_val,
        severity=finding.severity, evidence_strength=None, assessment_strength=strength,
        supporting_finding_ids=finding_ids,
        rationale=rationale_template.format(finding_count=finding_count, denominator=denominator, norm_val=norm_val),
    )


def _norm_r001(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    denominator = int(entity_metadata.get("critical_closed_case_count", 0))
    if denominator == 0:
        denominator = int(entity_metadata.get("closed_case_count", 0))
    return _prevalence_signal(
        finding, by_detector,
        signal_name="Critical Rapid Closure Prevalence",
        denominator=denominator,
        unassessable_reason="No closed cases observed for entity.",
        rationale_template="{finding_count} critical rapid closure findings observed across {denominator} closed cases ({norm_val:.1f}% prevalence).",
    )


def _norm_r002(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    denominator = int(entity_metadata.get("critical_case_count", 0))
    return _prevalence_signal(
        finding, by_detector,
        signal_name="Unescalated Critical Case Prevalence",
        denominator=denominator,
        unassessable_reason="No critical cases observed for entity.",
        rationale_template="{finding_count} unescalated critical cases out of {denominator} critical cases ({norm_val:.1f}% prevalence).",
    )


def _norm_r003(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    finding_ids = [f.id for f in by_detector]
    finding_count = len(by_detector)
    denominator = int(entity_metadata.get("total_assets", 0))
    if denominator == 0:
        return _unassessable(
            finding,
            signal_name="Unremediated Repeated Alert Asset Prevalence",
            raw_value=finding_count,
            reason="No asset inventory available.",
            supporting_finding_ids=finding_ids,
        )
    prevalence = min(1.0, finding_count / denominator)
    # Scaling asset prevalence: even 10% of assets with repeated unremediated alerts is significant
    norm_val = min(100.0, round(prevalence * 300.0, 2))
    strength = _derive_assessment_strength(None, denominator)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name="Unremediated Repeated Alert Asset Prevalence", raw_value=finding_count,
        normalized_value=norm_val, severity=finding.severity, evidence_strength=None,
        assessment_strength=strength, supporting_finding_ids=finding_ids,
        rationale=f"{finding_count} assets with repeated unremediated alerts across {denominator} total assets.",
    )


def _norm_r004(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    denominator = int(entity_metadata.get("case_count", 0))
    return _prevalence_signal(
        finding, by_detector,
        signal_name="Short Investigation Duration Prevalence",
        denominator=denominator,
        unassessable_reason="No cases observed for entity.",
        rationale_template="{finding_count} short investigation cases out of {denominator} total cases ({norm_val:.1f}% prevalence).",
    )


def _norm_r005(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    denominator = int(entity_metadata.get("expected_monitored_assets", 0))
    if denominator == 0:
        return _unassessable(
            finding,
            signal_name="Monitoring Coverage Gap",
            raw_value=finding.observed_value,
            reason="No expected-monitored assets defined.",
        )
    observed_gap = finding.observed_value
    if not isinstance(observed_gap, (int, float)):
        return _unassessable(
            finding,
            signal_name="Monitoring Coverage Gap",
            raw_value=observed_gap,
            reason="Observed monitoring gap is not numeric and cannot be normalized.",
        )
    norm_val = min(100.0, round((float(observed_gap) / denominator) * 100.0, 2))
    strength = _derive_assessment_strength(None, denominator)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name="Monitoring Coverage Gap", raw_value=observed_gap,
        normalized_value=norm_val, severity=finding.severity, evidence_strength=None,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        rationale=f"Observed monitoring gap on expected-monitored assets: {observed_gap} gap assets out of {denominator}.",
    )


def _norm_phase6_ratio(
    finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding],
    *, baseline_divider: float | None = None,
) -> NormalizedSignal:
    gap = float(finding.gap_value) if finding.gap_value is not None else 0.0
    baseline = float(finding.baseline_value) if finding.baseline_value is not None else 1.0
    if baseline <= 0:
        baseline = 1.0
    divider = baseline_divider if baseline_divider is not None else baseline
    if divider <= 0:
        divider = 1.0
    norm_val = min(100.0, round((gap / divider) * 100.0, 2))
    strength = _derive_assessment_strength(finding.evidence_strength, finding.population_size)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name=finding.title, raw_value=gap, normalized_value=norm_val,
        severity=finding.severity, evidence_strength=finding.evidence_strength,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        rationale=f"Execution gap of {gap:.3g} against configured baseline {baseline:.3g} ({finding.rationale})",
    )


def _norm_eg001(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_phase6_ratio(finding, entity_metadata, by_detector)


def _norm_eg002(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_phase6_ratio(finding, entity_metadata, by_detector)


def _norm_eg003(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_phase6_ratio(finding, entity_metadata, by_detector)


def _norm_eg004(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_phase6_ratio(finding, entity_metadata, by_detector, baseline_divider=0.40)


def _norm_ns_ratio(
    finding: StandardizedFinding, entity_metadata: dict[str, Any],
    *, denominator_key: str,
) -> NormalizedSignal:
    obs = float(finding.observed_value) if finding.observed_value is not None else 0.0
    denom = int(entity_metadata.get(denominator_key, 1))
    norm_val = min(100.0, round((obs / max(denom, 1)) * 100.0, 2))
    strength = _derive_assessment_strength(finding.evidence_strength, finding.population_size)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name=finding.title, raw_value=obs, normalized_value=norm_val,
        severity=finding.severity, evidence_strength=finding.evidence_strength,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        rationale=finding.rationale,
    )


def _norm_ns_gap(finding: StandardizedFinding, entity_metadata: dict[str, Any]) -> NormalizedSignal:
    obs = float(finding.observed_value) if finding.observed_value is not None else 0.0
    gap = float(finding.gap_value) if finding.gap_value is not None else 0.5
    norm_val = min(100.0, round(gap * 100.0, 2))
    strength = _derive_assessment_strength(finding.evidence_strength, finding.population_size)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name=finding.title, raw_value=obs, normalized_value=norm_val,
        severity=finding.severity, evidence_strength=finding.evidence_strength,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        rationale=finding.rationale,
    )


def _norm_ns001(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    # NS001 observed_value is the count of assets WITH alert activity; the risk
    # grows with the GAP (1 - coverage_rate), not with observed activity. Use the
    # gap-based normalizer so higher absence of expected evidence maps to higher risk.
    return _norm_ns_gap(finding, entity_metadata)


def _norm_ns002(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    # NS002 observed_value counts critical assets WITH activity; the risk grows
    # with the share of INACTIVE critical assets (gap_value). Gap-based scoring is
    # correct here too.
    return _norm_ns_gap(finding, entity_metadata)


def _norm_ns003(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_ns_gap(finding, entity_metadata)


def _norm_ns004(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_ns_gap(finding, entity_metadata)


def _norm_ns005(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    return _norm_ns_ratio(finding, entity_metadata, denominator_key="critical_alert_count")


def _norm_an001(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    # Strict Non-Probability Anomaly Score Handling:
    # AN001 Isolation Forest score is non-linear and relative within the population.
    # Bounded strictly to ANOMALY_SCORE_CEILING (25.0) to ensure it acts strictly as contextual evidence.
    rank = int(finding.anomaly_rank) if finding.anomaly_rank is not None else 1
    contributions = finding.contributing_deviations or []
    contributing_features = [
        item["feature"] for item in contributions if isinstance(item, dict) and "feature" in item
    ]
    avg_rel_dev = 0.0
    if contributions:
        valid_devs = [float(item.get("relative_deviation", 0.0)) for item in contributions if isinstance(item, dict)]
        avg_rel_dev = sum(valid_devs) / len(valid_devs) if valid_devs else 0.0

    # Rank-based base contextual signal (Rank 1 -> 18.0, Rank 2 -> 14.0, Rank 3 -> 10.0, etc.)
    base_rank_score = max(5.0, 18.0 - (rank - 1) * 4.0)
    # Deviation intensity component (bounded up to +7.0)
    dev_intensity = min(7.0, round(avg_rel_dev * 8.0, 2))
    norm_val = min(ANOMALY_SCORE_CEILING, round(base_rank_score + dev_intensity, 2))

    strength = _derive_assessment_strength(finding.evidence_strength, finding.population_size)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name="Unusual Operational Profile (Contextual Anomaly)", raw_value=finding.anomaly_score,
        normalized_value=norm_val, severity=finding.severity, evidence_strength=finding.evidence_strength,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        contributing_features=contributing_features,
        rationale=f"Contextual relative anomaly signal (rank {rank}, avg dev {avg_rel_dev:.2f}) from Isolation Forest; not a probability of compromise or compliance violation.",
    )


def _norm_peer(finding: StandardizedFinding, entity_metadata: dict[str, Any], by_detector: list[StandardizedFinding]) -> NormalizedSignal:
    # Peer deviations: PB001 - PB004
    abs_gap = float(finding.absolute_gap) if finding.absolute_gap is not None else 0.0
    ref_val = float(finding.reference_value) if finding.reference_value is not None else 1.0
    rel_dev = abs_gap / max(abs(ref_val), 1e-6)
    norm_val = min(100.0, round(rel_dev * 60.0, 2))
    strength = _derive_assessment_strength(finding.evidence_strength, finding.population_size)
    return NormalizedSignal(
        entity_id=finding.entity_id, detector_id=finding.rule_id, source_phase=finding.source_phase,
        signal_name=finding.title, raw_value=abs_gap, normalized_value=norm_val,
        severity=finding.severity, evidence_strength=finding.evidence_strength,
        assessment_strength=strength, supporting_finding_ids=[finding.id],
        rationale=finding.rationale,
    )


# Explicit per-detector normalization registry. No implicit fallbacks exist:
# a detector not listed here produces an explicit unassessable signal.
NORMALIZERS: dict[str, SignalNormalizer] = {
    "R001": _norm_r001,
    "R002": _norm_r002,
    "R003": _norm_r003,
    "R004": _norm_r004,
    "R005": _norm_r005,
    "EG001": _norm_eg001,
    "EG002": _norm_eg002,
    "EG003": _norm_eg003,
    "EG004": _norm_eg004,
    "NS001": _norm_ns001,
    "NS002": _norm_ns002,
    "NS003": _norm_ns003,
    "NS004": _norm_ns004,
    "NS005": _norm_ns005,
    "AN001": _norm_an001,
    "PB001": _norm_peer,
    "PB002": _norm_peer,
    "PB003": _norm_peer,
    "PB004": _norm_peer,
}


def normalize_finding_signal(
    finding: StandardizedFinding,
    entity_metadata: dict[str, Any],
    all_entity_findings_for_detector: list[StandardizedFinding],
) -> NormalizedSignal:
    """Transform an individual or aggregated finding into a normalized supervisory signal.

    Normalization is always explicit: every registered detector has a
    deterministic rule, and any unregistered detector id yields an explicit
    unassessable signal instead of a silent default value.
    """
    normalizer = NORMALIZERS.get(finding.rule_id)
    if normalizer is None:
        return _unassessable(
            finding,
            signal_name=finding.title,
            raw_value=finding.observed_value,
            reason=f"No normalization rule registered for detector {finding.rule_id}.",
            evidence_strength=finding.evidence_strength,
        )
    return normalizer(finding, entity_metadata, all_entity_findings_for_detector)