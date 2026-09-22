from __future__ import annotations

import json
from pathlib import Path

from app.analytics.supervisory_risk.config import (
    CORRELATION_GROUPS,
    DEFERRED_DETECTORS,
    DIMENSION_METADATA,
    DIMENSION_WEIGHTS,
    DIMENSIONS,
    PRIORITY_THRESHOLDS,
    RISK_BAND_THRESHOLDS,
    SCHEMA_VERSION,
)
from app.analytics.supervisory_risk.inputs import UpstreamBundle
from app.analytics.supervisory_risk.models import SupervisoryRiskRunResult


def write_manifest(
    output_dir: str | Path,
    dataset_id: str,
    bundle: UpstreamBundle,
    result: SupervisoryRiskRunResult,
) -> dict[str, object]:
    """Generate and write the auditable Supervisory Risk manifest."""
    manifest = {
        "stage": "Phase 9 Supervisory Risk Engine + Manual Review Prioritisation",
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "input_paths": bundle.source_paths,
        "input_phase_counts": bundle.phase_counts,
        "dimensions": DIMENSIONS,
        "dimension_weights": DIMENSION_WEIGHTS,
        "dimensions_config": DIMENSION_METADATA,
        "risk_band_thresholds": {k: list(v) for k, v in RISK_BAND_THRESHOLDS.items()},
        "priority_thresholds": PRIORITY_THRESHOLDS,
        "correlation_groups": {
            k: {
                "dimension": v["dimension"],
                "detectors": v["detectors"],
                "relevant_features": v.get("relevant_features", []),
                "description": v["description"],
            }
            for k, v in CORRELATION_GROUPS.items()
        },
        "an001_configuration": {
            "maximum_influence": 25.0,
            "methodology": "Deterministic rank-based contextual signal (Rank 1 -> 18.0, Rank 2 -> 14.0, etc.) plus contributing deviation intensity (up to +7.0), bounded to 25.0 ceiling.",
            "feature_to_dimension_mapping": "Feature-aware filtering: AN001 participates in a correlation group only when its contributing_deviations explicitly cite a relevant feature for that group.",
            "contextual_nature": "AN001 is relative contextual anomaly evidence within the submitted population; it is not a probability, confidence, or compliance likelihood.",
        },
        "normalization_methods": {
            "phase5_record_findings": "Prevalence rate = count(findings) / applicable entity denominator, bounded and severity-scaled",
            "phase5_r005_denominator_handling": "Prevalence rate = observed gap / expected_monitored_assets; if expected_monitored_assets is 0 or unavailable, R005 is marked is_assessable=False with 0 assigned risk.",
            "phase6_execution_gaps": "Gap ratio = abs(gap_value) / baseline_value * 100, bounded to 100.0",
            "phase7_negative_space": "Absence ratio = observed inactive count / expected monitored population, bounded to 100.0",
            "phase8_peer_deviations": "Relative cohort deviation = absolute_gap / reference_value, scaled by cohort support",
            "phase8_anomaly_an001": "Deterministic bounded contextual anomaly signal (max 25.0 points); not interpreted as probability",
        },
        "aggregation_method": "Two-level hierarchical aggregation: Level 1 derives dimension scores from correlation groups; Level 2 computes assessable-weighted average across 6 dimensions",
        "dimension_assessability_rule": "A dimension is assessable if at least one underlying signal/group is assessable based on entity baseline telemetry. Unassessable dimensions are excluded from the Level 2 weighted average denominator.",
        "r005_denominator_handling": "When expected_monitored_assets is 0 or unavailable, R005 is marked is_assessable=False with 0 assigned risk and explicit unassessable reason, avoiding artificial risk inflation.",
        "priority_method": "Multi-factor prioritisation queue favoring systemic execution gaps, unmonitored blindspots, multi-phase corroboration, and evidence strength",
        "coverage_method": "Ratio of assessable operational dimensions evaluated for entity; missing evidence is flagged as an assessment limitation rather than zero or 100 risk",
        "detectors_consumed": result.detectors_consumed,
        "detectors_excluded": result.detectors_excluded,
        "evidence_strength_methodology": "Evidence strength reflects population sample size, deviation magnitude, and multi-phase corroboration; it is not statistical confidence.",
        "row_counts": {
            "entity_risk": len(result.entity_risks),
            "risk_contributions": len(result.risk_contributions),
            "review_queue": len(result.review_queue),
        },
    }

    manifest_path = Path(output_dir) / "supervisory_risk_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
