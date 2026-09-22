from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl

from app.analytics.features.feature_pipeline import generate_features
from app.analytics.rules.engine import evaluate_all_rules, run_rules
from app.analytics.rules.evaluators import evaluate_r001, evaluate_r002, evaluate_r003, evaluate_r004, evaluate_r005
from app.analytics.rules.models import RuleDefinition


def _rule(rule_id: str, finding_type: str, severity: str = "Medium") -> RuleDefinition:
    return RuleDefinition(rule_id=rule_id, name=rule_id, description=rule_id, finding_type=finding_type, severity=severity, thresholds={"threshold": 10})


def _case_bundle(*, severity: str = "Critical", duration: float | None = 5.0, escalated: bool = False) -> dict[str, pl.DataFrame]:
    return {
        "case_features": pl.DataFrame({
            "id": ["CASE-1"], "entity_id": ["CSE-001"], "alert_id": ["ALT-1"], "severity": [severity],
            "is_closed": [duration is not None], "investigation_minutes": [duration], "is_escalated": [escalated],
            "is_remediated": [False], "opened_at": [datetime(2025, 1, 1)],
        }),
        "alert_features": pl.DataFrame({"id": ["ALT-1"], "entity_id": ["CSE-001"], "asset_id": ["AST-1"], "asset_alert_count": [1]}),
    }


def test_r001_rapid_critical_closure_and_guards() -> None:
    findings, evidence = evaluate_r001(_rule("R001", "Rapid Closure"), _case_bundle())
    assert len(findings) == 1 and findings[0].rule_id == "R001" and findings[0].entity_id == "CSE-001"
    assert findings[0].severity == "Medium" and findings[0].rationale and evidence
    assert not evaluate_r001(_rule("R001", "Rapid Closure"), _case_bundle(duration=20))[0]
    assert not evaluate_r001(_rule("R001", "Rapid Closure"), _case_bundle(severity="Low"))[0]


def test_r002_critical_without_escalation() -> None:
    bundle = {
        "case_features": pl.DataFrame({
            "id": ["CASE-1"], "entity_id": ["CSE-001"], "alert_id": ["ALT-1"], "severity": ["Critical"],
            "is_closed": [True], "investigation_minutes": [5.0], "is_escalated": [False],
            "is_remediated": [False], "opened_at": [datetime(2025, 1, 1)],
        }),
        "entity_features": pl.DataFrame({
            "entity_id": ["CSE-001"], "critical_case_count": [10],
        }),
    }
    # Threshold comes from the rule; the test rule has no minimum_critical_cases, so MIN_CRITICAL_CASES=5 is used.
    findings, evidence = evaluate_r002(_rule("R002", "Escalation", "High"), bundle)
    assert len(findings) == 1 and findings[0].severity == "High" and evidence
    assert not evaluate_r002(_rule("R002", "Escalation", "High"), {
        "case_features": bundle["case_features"],
        "entity_features": bundle["entity_features"].with_columns(pl.col("critical_case_count").replace(10, 4)),
    })[0]
    assert not evaluate_r002(_rule("R002", "Escalation", "High"), {
        "case_features": bundle["case_features"].with_columns(pl.col("is_escalated").replace(False, True)),
        "entity_features": bundle["entity_features"],
    })[0]


def test_r003_repeated_alerts_without_remediation() -> None:
    bundle = {
        "alert_features": pl.DataFrame({"id": ["A1", "A2", "A3"], "entity_id": ["E1"] * 3, "asset_id": ["AS1"] * 3, "asset_alert_count": [3] * 3}),
        "case_features": pl.DataFrame({"id": ["C1", "C2", "C3"], "alert_id": ["A1", "A2", "A3"], "is_remediated": [False] * 3}),
        "asset_features": pl.DataFrame({"id": ["AS1"], "entity_id": ["E1"], "alert_count": [3], "case_count": [3]}),
    }
    findings, evidence = evaluate_r003(_rule("R003", "Repeated Activity"), bundle)
    assert len(findings) == 1 and findings[0].entity_id == "E1" and evidence
    bundle["asset_features"] = bundle["asset_features"].with_columns(pl.lit(2).alias("alert_count"))
    assert not evaluate_r003(_rule("R003", "Repeated Activity"), bundle)[0]


def test_r004_short_high_investigation_only() -> None:
    findings, evidence = evaluate_r004(_rule("R004", "Investigation"), _case_bundle(severity="High"))
    assert len(findings) == 1 and findings[0].finding_type == "Investigation" and evidence
    assert not evaluate_r004(_rule("R004", "Investigation"), _case_bundle(severity="Low"))[0]
    assert not evaluate_r004(_rule("R004", "Investigation"), _case_bundle(severity="High", duration=20))[0]


def test_r005_monitoring_gap_guards() -> None:
    entity = pl.DataFrame({
        "entity_id": ["E1", "E2"], "expected_monitored_assets": [10, 9],
        "expected_monitored_assets_without_activity": [5, 5], "assets_with_alert_activity": [5, 4],
        "expected_monitored_assets_with_activity": [5, 4], "monitoring_coverage_rate": [0.5, 0.444],
    })
    findings, evidence = evaluate_r005(_rule("R005", "Monitoring Coverage"), {"entity_features": entity})
    assert len(findings) == 1 and findings[0].entity_id == "E1" and evidence


def test_all_rules_have_traceable_evidence_and_outputs_are_queryable(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "data" / "synthetic"
    feature_dir = tmp_path / "features"
    generate_features(source, feature_dir, "phase2-canonical")
    output = tmp_path / "findings"
    result = run_rules(feature_dir, output, "phase2-canonical")
    assert result.findings
    assert result.evidence
    assert {finding.rule_id for finding in result.findings} == {"R001", "R002", "R003", "R004", "R005"}
    finding_ids = {finding.id for finding in result.findings}
    assert all(item.finding_id in finding_ids for item in result.evidence)
    assert all(any(item.finding_id == finding.id and item.entity_id == finding.entity_id for item in result.evidence) for finding in result.findings)
    assert duckdb.sql(f"select count(*) from read_parquet('{(output / 'findings.parquet').as_posix()}')").fetchone()[0] == len(result.findings)
    assert duckdb.sql(f"select count(*) from read_parquet('{(output / 'evidence.parquet').as_posix()}')").fetchone()[0] == len(result.evidence)
    forbidden = {"risk_score", "is_bad_entity", "execution_gap", "negative_space", "peer_deviation"}
    assert not forbidden & set(pl.read_parquet(output / "findings.parquet").columns)
