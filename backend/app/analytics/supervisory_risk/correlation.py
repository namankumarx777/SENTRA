from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.analytics.supervisory_risk.config import (
    CORRELATION_GROUPS,
    CORROBORATION_BOOST_PER_PHASE,
    MAX_CORROBORATION_BOOST,
)
from app.analytics.supervisory_risk.models import RiskContribution
from app.analytics.supervisory_risk.normalization import NormalizedSignal


@dataclass
class CorrelatedGroupSignal:
    group_id: str
    dimension: str
    entity_id: str
    base_value: float
    corroboration_boost: float
    final_value: float  # Bounded strictly 0.0 to 100.0
    corroboration_level: str  # "None", "Moderate", "Strong"
    corroborating_phases: list[str]
    participating_detectors: list[str]
    supporting_finding_ids: list[str]
    severity: str
    assessment_strength: str
    evidence_strength: str | None
    rationale: str
    primary_detector: str = ""
    primary_phase: str = ""


SEVERITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
STRENGTH_RANK = {"High": 3, "Medium": 2, "Low": 1}


def _highest_severity(severities: list[str]) -> str:
    return max(severities, key=lambda s: SEVERITY_RANK.get(s, 0), default="Medium")


def _highest_strength(strengths: list[str]) -> str:
    return max(strengths, key=lambda s: STRENGTH_RANK.get(s, 0), default="Medium")


def evaluate_correlation_groups(
    entity_id: str,
    signals: list[NormalizedSignal],
) -> list[CorrelatedGroupSignal]:
    """Aggregate individual signals into anti-double-counting correlation groups with corroboration."""
    signals_by_detector = {s.detector_id: s for s in signals}
    group_results: list[CorrelatedGroupSignal] = []

    for group_id, group_meta in CORRELATION_GROUPS.items():
        dimension = group_meta["dimension"]
        eligible_detectors = group_meta["detectors"]

        # Find signals belonging to this group that triggered for this entity
        active_signals: list[NormalizedSignal] = []
        for det_id in eligible_detectors:
            if det_id not in signals_by_detector:
                continue
            sig = signals_by_detector[det_id]
            if not sig.is_assessable or sig.normalized_value <= 0:
                continue

            # Feature-aware filtering for AN001:
            # AN001 is a global multivariate detector; it may only participate in a correlation group
            # if its contributing_features explicitly match the group's relevant_features (or home group).
            if det_id == "AN001":
                relevant_features = group_meta.get("relevant_features", [])
                if "*" not in relevant_features:
                    if not any(feat in relevant_features for feat in sig.contributing_features):
                        continue

            active_signals.append(sig)

        if not active_signals:
            continue

        # 1. Base signal: take the primary (highest) normalized signal in this correlation group
        # This prevents summing R002 + EG001 + PB001 + AN001 independently!
        primary_signal = max(active_signals, key=lambda s: s.normalized_value)
        base_value = primary_signal.normalized_value

        # 2. Corroboration model: multiple distinct phases confirming the issue add a bounded boost
        participating_phases = sorted(list({s.source_phase for s in active_signals}))
        distinct_phase_count = len(participating_phases)

        if distinct_phase_count > 1:
            boost_factor = min(
                MAX_CORROBORATION_BOOST,
                (distinct_phase_count - 1) * CORROBORATION_BOOST_PER_PHASE,
            )
            corroboration_level = "Strong" if distinct_phase_count >= 3 else "Moderate"
        else:
            boost_factor = 0.0
            corroboration_level = "Single Phase"

        final_value = min(100.0, round(base_value * (1.0 + boost_factor), 2))

        # 3. Aggregate metadata across all participating detectors
        all_finding_ids: list[str] = []
        for s in active_signals:
            all_finding_ids.extend(s.supporting_finding_ids)
        # Deduplicate while preserving order
        seen = set()
        deduped_finding_ids = [fid for fid in all_finding_ids if not (fid in seen or seen.add(fid))]

        participating_detectors = [s.detector_id for s in active_signals]
        highest_sev = _highest_severity([s.severity for s in active_signals])
        highest_str = _highest_strength([s.assessment_strength for s in active_signals])

        # Evidence strength: keep highest non-null, or None
        ev_strengths = [s.evidence_strength for s in active_signals if s.evidence_strength is not None]
        overall_ev_str = _highest_strength(ev_strengths) if ev_strengths else None

        # Build explainable rationale
        detector_details = "; ".join(
            f"{s.detector_id} ({s.source_phase}, norm={s.normalized_value:.1f})" for s in active_signals
        )
        corroboration_desc = (
            f"Corroborated across {distinct_phase_count} phases ({', '.join(participating_phases)})"
            if distinct_phase_count > 1
            else "Observed in single phase"
        )
        rationale = (
            f"Correlation Group {group_id}: Base signal {base_value:.1f} from {primary_signal.detector_id}. "
            f"{corroboration_desc} with boost +{boost_factor*100:.0f}%, resulting in final group score {final_value:.1f}. "
            f"Participating detectors: {detector_details}."
        )

        group_results.append(
            CorrelatedGroupSignal(
                group_id=group_id,
                dimension=dimension,
                entity_id=entity_id,
                base_value=base_value,
                corroboration_boost=boost_factor,
                final_value=final_value,
                corroboration_level=corroboration_level,
                corroborating_phases=participating_phases,
                participating_detectors=participating_detectors,
                supporting_finding_ids=deduped_finding_ids,
                severity=highest_sev,
                assessment_strength=highest_str,
                evidence_strength=overall_ev_str,
                rationale=rationale,
                primary_detector=primary_signal.detector_id,
                primary_phase=primary_signal.source_phase,
            )
        )

    return group_results


def build_risk_contributions(
    entity_id: str,
    group_signals: list[CorrelatedGroupSignal],
    dimension_weights: dict[str, float],
) -> list[RiskContribution]:
    """Convert correlated group signals into auditable RiskContribution records."""
    contributions: list[RiskContribution] = []

    for gs in group_signals:
        dim_weight = dimension_weights.get(gs.dimension, 0.10)
        # Weighted contribution to the overall score
        contrib_value = round(gs.final_value * dim_weight, 2)

        # Deterministic SHA-256 identifier for each contribution
        content_for_id = f"{entity_id}:{gs.group_id}:{gs.dimension}:{gs.final_value:.2f}"
        contrib_id = hashlib.sha256(content_for_id.encode("utf-8")).hexdigest()[:16]

        primary_phase = gs.primary_phase or (gs.corroborating_phases[0] if gs.corroborating_phases else "analytics")
        primary_detector = gs.primary_detector or (gs.participating_detectors[0] if gs.participating_detectors else "composite")

        contributions.append(
            RiskContribution(
                id=contrib_id,
                entity_id=entity_id,
                dimension=gs.dimension,
                source_phase=primary_phase,
                detector_id=primary_detector,
                signal_name=f"{gs.group_id} ({gs.corroboration_level} Corroboration)",
                raw_value=gs.base_value,
                normalized_value=gs.final_value,
                weight=dim_weight,
                contribution=contrib_value,
                severity=gs.severity,
                evidence_strength=gs.evidence_strength,
                assessment_strength=gs.assessment_strength,
                corroboration_group=gs.group_id,
                supporting_finding_ids=gs.supporting_finding_ids,
                rationale=gs.rationale,
            )
        )

    return sorted(contributions, key=lambda c: (c.entity_id, c.dimension, c.id))
