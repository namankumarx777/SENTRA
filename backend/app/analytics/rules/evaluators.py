from __future__ import annotations

from collections.abc import Callable
from typing import Any

import polars as pl

from app.analytics.rules.definitions import (
    MIN_CRITICAL_CASES,
    MIN_EXPECTED_MONITORED_ASSETS,
    MIN_MONITORING_COVERAGE,
    MIN_MONITORING_GAP_ASSETS,
    MIN_REPEATED_ALERTS,
)
from app.analytics.rules.evidence import make_evidence, make_finding
from app.analytics.rules.models import Evidence, Finding, RuleDefinition
from app.analytics.features.schemas import RAPID_CLOSURE_MINUTES

FeatureBundle = dict[str, pl.DataFrame]
Evaluator = Callable[[RuleDefinition, FeatureBundle], tuple[list[Finding], list[Evidence]]]


def evaluate_r001(rule: RuleDefinition, bundle: FeatureBundle) -> tuple[list[Finding], list[Evidence]]:
    candidates = bundle["case_features"].filter(
        (pl.col("severity") == "Critical")
        & pl.col("is_closed")
        & pl.col("investigation_minutes").is_not_null()
        & (pl.col("investigation_minutes") <= RAPID_CLOSURE_MINUTES)
    )
    findings: list[Finding] = []
    evidence: list[Evidence] = []
    for row in candidates.select(["id", "entity_id", "alert_id", "investigation_minutes", "severity"]).sort(["entity_id", "id"]).to_dicts():
        finding = make_finding(
            rule_id=rule.rule_id, entity_id=row["entity_id"], source_id=row["id"], finding_type=rule.finding_type,
            severity=rule.severity, confidence="High", title="Critical alert closed unusually quickly",
            summary=f"Critical case {row['id']} was closed in {row['investigation_minutes']:.1f} minutes.",
            rationale=f"Critical case {row['id']} had an investigation duration below the configured {RAPID_CLOSURE_MINUTES}-minute threshold. This is a potential rapid closure concern, not a confirmed failure.",
            metric_name="investigation_minutes", observed_value=row["investigation_minutes"], threshold=RAPID_CLOSURE_MINUTES,
        )
        findings.append(finding)
        evidence.extend([
            make_evidence(finding, "case_feature", row["id"], "investigation_minutes", row["investigation_minutes"], "Closed critical case duration used by R001."),
            make_evidence(finding, "case_feature", row["id"], "severity", row["severity"], "Case severity used by R001."),
            make_evidence(finding, "alert_feature", row["alert_id"], "id", row["alert_id"], "Alert associated with the case."),
        ])
    return findings, evidence


def evaluate_r002(rule: RuleDefinition, bundle: FeatureBundle) -> tuple[list[Finding], list[Evidence]]:
    guard_threshold = int(rule.thresholds.get("minimum_critical_cases", MIN_CRITICAL_CASES))
    case_candidates = bundle["case_features"].filter(
        (pl.col("severity") == "Critical") & (~pl.col("is_escalated"))
    )

    # Entity-level population guard: only flag entities with a sufficient number
    # of critical cases so that a single stray critical case does not generate a
    # noisy supervisory signal. The population is derived from the full critical
    # case volume, escalated or not.
    if "entity_features" in bundle and "critical_case_count" in bundle["entity_features"].columns:
        pop = bundle["entity_features"].select(["entity_id", "critical_case_count"])
        pop = pop.with_columns(pl.col("critical_case_count").fill_null(0).cast(pl.Int64))
        eligible = pop.filter(pl.col("critical_case_count") >= guard_threshold).get_column("entity_id")
    else:
        counts = (
            bundle["case_features"]
            .filter(pl.col("severity") == "Critical")
            .group_by("entity_id")
            .len()
            .rename({"len": "critical_case_count"})
        )
        eligible = counts.filter(pl.col("critical_case_count") >= guard_threshold).get_column("entity_id")

    candidates = case_candidates.filter(pl.col("entity_id").is_in(eligible.to_list())).sort(["entity_id", "id"])
    findings: list[Finding] = []
    evidence: list[Evidence] = []
    for row in candidates.select(["id", "entity_id", "alert_id", "severity", "is_escalated"]).sort(["entity_id", "id"]).to_dicts():
        finding = make_finding(
            rule_id=rule.rule_id, entity_id=row["entity_id"], source_id=row["id"], finding_type=rule.finding_type,
            severity=rule.severity, confidence="High", title="Critical alert without escalation",
            summary=f"Critical case {row['id']} has no associated escalation record.",
            rationale=f"Critical case {row['id']} is marked non-escalated. The rule reports the missing escalation record without asserting that escalation was required.",
            metric_name="is_escalated", observed_value=False, expected_value=True,
        )
        findings.append(finding)
        evidence.extend([
            make_evidence(finding, "case_feature", row["id"], "severity", row["severity"], "Critical case severity used by R002."),
            make_evidence(finding, "case_feature", row["id"], "is_escalated", row["is_escalated"], "Case escalation state used by R002."),
            make_evidence(finding, "alert_feature", row["alert_id"], "id", row["alert_id"], "Alert associated with the case."),
        ])
    return findings, evidence


def evaluate_r003(rule: RuleDefinition, bundle: FeatureBundle) -> tuple[list[Finding], list[Evidence]]:
    alerts = bundle["alert_features"].select(["id", "asset_id", "entity_id", "asset_alert_count"])
    cases = bundle["case_features"].select(["id", "alert_id", "is_remediated"])
    asset_case_stats = (
        alerts.join(cases, left_on="id", right_on="alert_id", how="inner")
        .group_by(["asset_id", "entity_id"])
        .agg([
            pl.len().alias("case_count"),
            pl.col("is_remediated").sum().alias("remediated_case_count"),
            pl.col("id_right").sort().alias("case_ids"),
        ])
    )
    candidates = (
        bundle["asset_features"].select(["id", "entity_id", "alert_count", "case_count"])
        .filter((pl.col("alert_count") >= MIN_REPEATED_ALERTS) & (pl.col("case_count") > 0))
        .join(asset_case_stats, left_on=["id", "entity_id"], right_on=["asset_id", "entity_id"], how="inner")
        .filter(pl.col("remediated_case_count") == 0)
        .sort(["entity_id", "id"])
    )
    findings: list[Finding] = []
    evidence: list[Evidence] = []
    for row in candidates.to_dicts():
        finding = make_finding(
            rule_id=rule.rule_id, entity_id=row["entity_id"], source_id=row["id"], finding_type=rule.finding_type,
            severity=rule.severity, confidence="High", title="Repeated alert activity without recorded remediation",
            summary=f"Asset {row['id']} has {row['alert_count']} alerts and {row['case_count']} associated cases without recorded remediation.",
            rationale=f"Asset {row['id']} meets the minimum repeated-activity threshold of {MIN_REPEATED_ALERTS} alerts, while its associated cases contain no recorded remediation. This is an operational signal, not a confirmed incident.",
            metric_name="alert_count", observed_value=row["alert_count"], threshold=MIN_REPEATED_ALERTS, population_size=row["case_count"],
        )
        findings.append(finding)
        evidence.extend([
            make_evidence(finding, "asset_feature", row["id"], "alert_count", row["alert_count"], "Repeated alert count used by R003."),
            make_evidence(finding, "asset_feature", row["id"], "case_count", row["case_count"], "Associated case count used by R003."),
            make_evidence(finding, "asset_feature", row["id"], "remediated_case_count", row["remediated_case_count"], "No associated case has recorded remediation."),
        ])
        for case_id in row["case_ids"]:
            evidence.append(make_evidence(finding, "case_feature", case_id, "is_remediated", False, "Associated case has no recorded remediation."))
    return findings, evidence


def evaluate_r004(rule: RuleDefinition, bundle: FeatureBundle) -> tuple[list[Finding], list[Evidence]]:
    candidates = bundle["case_features"].filter(
        pl.col("severity").is_in(["High", "Critical"])
        & pl.col("investigation_minutes").is_not_null()
        & (pl.col("investigation_minutes") < RAPID_CLOSURE_MINUTES)
    )
    findings: list[Finding] = []
    evidence: list[Evidence] = []
    for row in candidates.select(["id", "entity_id", "alert_id", "severity", "investigation_minutes"]).sort(["entity_id", "id"]).to_dicts():
        finding = make_finding(
            rule_id=rule.rule_id, entity_id=row["entity_id"], source_id=row["id"], finding_type=rule.finding_type,
            severity=rule.severity, confidence="Medium", title="Potentially shallow investigation",
            summary=f"{row['severity']} case {row['id']} was investigated for {row['investigation_minutes']:.1f} minutes.",
            rationale=f"The investigation duration is below the configured {RAPID_CLOSURE_MINUTES}-minute proxy threshold for high or critical cases. This is a potentially shallow investigation signal, not a definitive assessment.",
            metric_name="investigation_minutes", observed_value=row["investigation_minutes"], threshold=RAPID_CLOSURE_MINUTES,
        )
        findings.append(finding)
        evidence.extend([
            make_evidence(finding, "case_feature", row["id"], "severity", row["severity"], "Case severity used by R004."),
            make_evidence(finding, "case_feature", row["id"], "investigation_minutes", row["investigation_minutes"], "Investigation duration used by R004."),
            make_evidence(finding, "alert_feature", row["alert_id"], "id", row["alert_id"], "Alert associated with the case."),
        ])
    return findings, evidence


def evaluate_r005(rule: RuleDefinition, bundle: FeatureBundle) -> tuple[list[Finding], list[Evidence]]:
    candidates = bundle["entity_features"].filter(
        (pl.col("expected_monitored_assets") >= MIN_EXPECTED_MONITORED_ASSETS)
        & (pl.col("expected_monitored_assets_without_activity") >= MIN_MONITORING_GAP_ASSETS)
        & pl.col("monitoring_coverage_rate").is_not_null()
        & (pl.col("monitoring_coverage_rate") < MIN_MONITORING_COVERAGE)
    ).sort("entity_id")
    findings: list[Finding] = []
    evidence: list[Evidence] = []
    fields = ["expected_monitored_assets", "assets_with_alert_activity", "expected_monitored_assets_with_activity", "expected_monitored_assets_without_activity", "monitoring_coverage_rate"]
    for row in candidates.to_dicts():
        finding = make_finding(
            rule_id=rule.rule_id, entity_id=row["entity_id"], source_id=row["entity_id"], finding_type=rule.finding_type,
            severity=rule.severity, confidence="High", title="Potential monitoring coverage gap",
            summary=f"Entity {row['entity_id']} has {row['expected_monitored_assets_without_activity']} expected-monitored assets without alert activity.",
            rationale=f"Observed monitoring coverage is {row['monitoring_coverage_rate']:.3f}, below the configured {MIN_MONITORING_COVERAGE:.2f} threshold, with at least {MIN_MONITORING_GAP_ASSETS} expected-monitored assets without activity. This is a potential coverage gap, not confirmed telemetry loss.",
            metric_name="monitoring_coverage_rate", observed_value=row["monitoring_coverage_rate"], expected_value=MIN_MONITORING_COVERAGE,
            threshold=MIN_MONITORING_COVERAGE, population_size=row["expected_monitored_assets"],
        )
        findings.append(finding)
        for field in fields:
            evidence.append(make_evidence(finding, "entity_feature", row["entity_id"], field, row[field], f"Entity monitoring feature used by R005: {field}."))
    return findings, evidence


EVALUATORS: dict[str, Evaluator] = {
    "R001": evaluate_r001,
    "R002": evaluate_r002,
    "R003": evaluate_r003,
    "R004": evaluate_r004,
    "R005": evaluate_r005,
}
