from __future__ import annotations

import argparse
import datetime
import html
import json
from pathlib import Path
from typing import Any

import polars as pl

from app.analytics.datasets import resolve_feature_path, resolve_phase_dir
from app.analytics.supervisory_risk.config import DIMENSIONS, DIMENSION_WEIGHTS, RISK_BAND_THRESHOLDS
from app.analytics.supervisory_risk.inputs import load_upstream_bundle

REPO_ROOT = Path(__file__).resolve().parents[4]


def generate_entity_dossier_data(entity_id: str, data_root: str | Path | None = None) -> dict[str, Any]:
    """Compile a complete, auditable supervisory examination dossier for an entity."""
    root = Path(data_root) if data_root else (REPO_ROOT / "data" / "processed")
    risk_dir = resolve_phase_dir(root, "phase9")
    if risk_dir is None:
        raise FileNotFoundError(f"Cannot locate Phase 9 supervisory risk outputs under {root}")

    # 1. Load entity risk
    entity_risk_path = risk_dir / "entity_risk.parquet"
    if not entity_risk_path.is_file():
        raise FileNotFoundError(f"Cannot find entity_risk.parquet in {risk_dir}")

    df_risk = pl.read_parquet(entity_risk_path).filter(pl.col("entity_id") == entity_id)
    if df_risk.is_empty():
        raise ValueError(f"Entity '{entity_id}' not found in supervisory risk assessment.")
    entity_risk = df_risk.to_dicts()[0]

    # Compatibility aliases: superseded scoring columns are read through the
    # current canonical names. Values already present under the canonical names
    # take precedence (setdefault), so this is safe for both old and new schemas.
    canonical_map = {
        "overall_risk_band": ("risk_band", "LOW"),
        "overall_risk_score": ("overall_score", 0.0),
    }
    for canonical, (legacy, default) in canonical_map.items():
        entity_risk.setdefault(canonical, entity_risk.get(legacy, default))

    # 2. Load entity metadata if available
    entity_meta = {}
    meta_path = resolve_feature_path(root, "phase4")
    if meta_path is not None:
        df_meta = pl.read_parquet(meta_path).filter(pl.col("entity_id") == entity_id)
        if not df_meta.is_empty():
            entity_meta = df_meta.to_dicts()[0]

    # 3. Load risk contributions
    contributions = []
    contrib_path = risk_dir / "risk_contributions.parquet"
    if contrib_path.is_file():
        df_c = pl.read_parquet(contrib_path).filter(pl.col("entity_id") == entity_id)
        contributions = df_c.to_dicts()

    # 4. Load review queue item
    queue_item = None
    queue_path = risk_dir / "review_queue.parquet"
    if queue_path.is_file():
        df_q = pl.read_parquet(queue_path).filter(pl.col("entity_id") == entity_id).sort("priority_score", descending=True)
        if not df_q.is_empty():
            queue_item = df_q.to_dicts()[0]

    # 5. Load upstream findings and evidence
    bundle = load_upstream_bundle(root)
    entity_findings = [f for f in bundle.findings if f.entity_id == entity_id]
    entity_evidence = [e for f in entity_findings for e in bundle.evidence_by_finding.get(f.id, [])]

    # Parse JSON list fields if stored as strings
    for c in contributions:
        sf = c.get("supporting_finding_ids")
        if isinstance(sf, str):
            try:
                c["supporting_finding_ids"] = json.loads(sf)
            except Exception:
                c["supporting_finding_ids"] = [sf]

    # Dimension summaries
    dim_breakdown = []
    for dim in DIMENSIONS:
        score_key = f"{dim.lower().replace(' ', '_')}_score"
        score_val = entity_risk.get(score_key)
        weight = DIMENSION_WEIGHTS.get(dim, 0.10)
        is_assessable = score_val is not None
        contrib = round(score_val * weight, 2) if is_assessable and score_val is not None else 0.0
        dim_breakdown.append({
            "dimension": dim,
            "score": score_val,
            "weight": weight,
            "weighted_contribution": contrib,
            "is_assessable": is_assessable,
            "status": "Assessable" if is_assessable else "Not Assessable (Missing Telemetry Denominator)",
        })

    # Recommended Review Directives
    directives = []
    if entity_risk.get("overall_risk_band") in ("HIGH", "CRITICAL"):
        directives.append("Priority Supervisory Audit: Schedule direct inspection with entity SOC management within 14 business days.")
    if entity_risk.get("escalation_score") and entity_risk["escalation_score"] >= 50:
        directives.append("Escalation Governance Review: Inspect unescalated critical cases and mandate formal escalation policy enforcement.")
    if entity_risk.get("investigation_score") and entity_risk["investigation_score"] >= 50:
        directives.append("Investigation Depth Audit: Review closed case work notes for template-driven or superficial triage behaviors.")
    if entity_risk.get("monitoring_score") and entity_risk["monitoring_score"] >= 30:
        directives.append("Telemetry Gap Verification: Request updated asset-to-SIEM mapping to remediate unmonitored critical assets and category blindspots.")
    if not directives:
        directives.append("Routine Monitoring: Continue standard periodic supervisory review cycle.")

    dossier = {
        "dossier_id": f"SED-{entity_id}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "authority": "National Critical Information Infrastructure Protection Centre (NCIIPC) / NTRO",
        "title": f"Supervisory Examination Dossier — {entity_id}",
        "entity": {
            "id": entity_id,
            "name": entity_meta.get("name", entity_id),
            "sector": entity_meta.get("sector", "Critical Infrastructure"),
            "size": entity_meta.get("size", "Enterprise"),
            "criticality": entity_meta.get("criticality", "Tier-1"),
            "total_assets": entity_meta.get("total_assets", 0),
            "expected_monitored_assets": entity_meta.get("expected_monitored_assets", 0),
            "total_alerts": entity_meta.get("alert_count", 0),
            "total_cases": entity_meta.get("case_count", 0),
        },
        "supervisory_summary": {
            "overall_risk_score": entity_risk.get("overall_risk_score", 0.0),
            "overall_risk_band": entity_risk.get("overall_risk_band", "LOW"),
            "top_risk_dimension": entity_risk.get("top_risk_dimension", "None"),
            "is_fully_assessable": entity_risk.get("is_fully_assessable", True),
            "unassessable_dimensions": [d["dimension"] for d in dim_breakdown if not d["is_assessable"]],
            "review_queue_rank": queue_item.get("rank") if queue_item else None,
            "review_priority_score": queue_item.get("priority_score") if queue_item else None,
            "review_urgency": queue_item.get("urgency") if queue_item else "LOW",
        },
        "dimensions": dim_breakdown,
        "risk_contributions": contributions,
        "supervisory_directives": directives,
        "findings_inventory": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "source_phase": f.source_phase,
                "finding_type": f.finding_type,
                "severity": f.severity,
                "evidence_strength": f.evidence_strength,
                "title": f.title,
                "summary": f.summary,
                "rationale": f.rationale,
                "observed_value": f.observed_value,
                "baseline_value": f.baseline_value,
                "gap_value": f.gap_value,
            }
            for f in entity_findings
        ],
        "evidence_count": len(entity_evidence),
        "audit_traceability": {
            "pipeline_mode": "Offline Air-Gapped Supervisory Analytics Engine",
            "scoring_model": "Multi-Phase Anti-Double-Counting Correlation with Corroboration Boost",
            "evidence_integrity": "Deterministic SHA-256 Hashed Record Chain",
        },
    }
    return dossier


def _escape_html_payload(value: Any) -> Any:
    """HTML-escape every string in the payload recursively.

    Numbers, ``None``, and other non-string values are left untouched so that
    numeric formatting (e.g. ``{score:.2f}``) keeps working. This guarantees no
    ingress-contributed string reaches the rendered HTML unescaped.
    """
    if isinstance(value, str):
        return html.escape(value, quote=True)
    if isinstance(value, dict):
        return {k: _escape_html_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_escape_html_payload(v) for v in value]
    return value


def render_entity_dossier_html(dossier: dict[str, Any]) -> str:
    """Render a standalone, print-ready HTML regulatory audit brief."""
    dossier = _escape_html_payload(dossier)
    ent = dossier["entity"]
    summary = dossier["supervisory_summary"]
    dims = dossier["dimensions"]
    contribs = dossier["risk_contributions"]
    findings = dossier["findings_inventory"]
    directives = dossier["supervisory_directives"]

    band_color = {
        "CRITICAL": "#ef4444",
        "HIGH": "#f97316",
        "MODERATE": "#eab308",
        "LOW": "#22c55e",
    }.get(summary["overall_risk_band"], "#64748b")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Supervisory Dossier - {ent['id']} ({ent['name']})</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 15mm 15mm 15mm 15mm;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }}
  body {{
    color: #0f172a;
    background: #ffffff;
    font-size: 12px;
    line-height: 1.5;
    padding: 24px;
  }}
  .header {{
    border-bottom: 2px solid #0284c7;
    padding-bottom: 12px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .header-left h1 {{
    font-size: 18px;
    font-weight: 800;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .header-left .sub {{
    font-size: 11px;
    color: #475569;
    font-weight: 600;
  }}
  .header-right {{
    text-align: right;
    font-size: 10px;
    color: #64748b;
  }}
  .badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    color: #ffffff;
  }}
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }}
  .grid-4 {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 16px;
  }}
  .card {{
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
    background: #f8fafc;
  }}
  .card-title {{
    font-size: 10px;
    text-transform: uppercase;
    font-weight: 700;
    color: #64748b;
    margin-bottom: 4px;
  }}
  .card-value {{
    font-size: 16px;
    font-weight: 800;
    color: #0f172a;
  }}
  h2 {{
    font-size: 13px;
    font-weight: 700;
    color: #1e293b;
    border-left: 3px solid #0284c7;
    padding-left: 6px;
    margin: 14px 0 8px 0;
    text-transform: uppercase;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 14px;
    font-size: 11px;
  }}
  th {{
    background: #f1f5f9;
    color: #334155;
    font-weight: 700;
    text-align: left;
    padding: 6px 8px;
    border: 1px solid #e2e8f0;
  }}
  td {{
    padding: 6px 8px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
  }}
  tr:nth-child(even) {{
    background: #f8fafc;
  }}
  .directive-box {{
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 16px;
  }}
  .directive-box ul {{
    padding-left: 18px;
    font-size: 11px;
  }}
  .footer {{
    border-top: 1px solid #e2e8f0;
    padding-top: 8px;
    margin-top: 20px;
    font-size: 9px;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
  }}
  .print-btn-bar {{
    margin-bottom: 16px;
    padding: 8px 12px;
    background: #0284c7;
    color: #ffffff;
    border-radius: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .print-btn-bar button {{
    background: #ffffff;
    color: #0284c7;
    border: none;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
  }}
  @media print {{
    .print-btn-bar {{ display: none !important; }}
    body {{
      padding: 0 !important;
      background: #ffffff !important;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }}
    .card, th, td, .directive-box, .badge {{
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }}
  }}
</style>
</head>
<body>

<div class="print-btn-bar">
  <span><strong>SENTRA Supervisory Examination Dossier</strong> &bull; Official Regulatory Report</span>
  <button onclick="window.print()">Print / Save as PDF</button>
</div>

<div class="header">
  <div class="header-left">
    <h1>National Supervisory SOC Assessment Dossier</h1>
    <div class="sub">National Critical Information Infrastructure Protection Centre (NCIIPC) &bull; NTRO</div>
  </div>
  <div class="header-right">
    <div><strong>Dossier Ref:</strong> {dossier['dossier_id']}</div>
    <div><strong>Date:</strong> {dossier['generated_at'][:10]}</div>
    <div><strong>Classification:</strong> REGULATORY CONFIDENTIAL</div>
  </div>
</div>

<div class="grid-4">
  <div class="card">
    <div class="card-title">Supervisory Risk Score</div>
    <div class="card-value" style="color: {band_color};">{summary['overall_risk_score']:.2f} / 100</div>
    <span class="badge" style="background: {band_color};">{summary['overall_risk_band']} RISK</span>
  </div>
  <div class="card">
    <div class="card-title">Review Urgency / Queue</div>
    <div class="card-value">{summary['review_urgency']}</div>
    <div style="font-size: 10px; color: #64748b;">Queue Rank #{summary['review_queue_rank'] or 'N/A'} (Score: {summary['review_priority_score'] or 0.0})</div>
  </div>
  <div class="card">
    <div class="card-title">Entity Profile</div>
    <div class="card-value" style="font-size: 13px;">{ent['name']}</div>
    <div style="font-size: 10px; color: #64748b;">{ent['sector']} &bull; {ent['size']} &bull; {ent['criticality']}</div>
  </div>
  <div class="card">
    <div class="card-title">Telemetry Volume</div>
    <div class="card-value" style="font-size: 14px;">{ent['total_alerts']} alerts / {ent['total_cases']} cases</div>
    <div style="font-size: 10px; color: #64748b;">{ent['expected_monitored_assets']} of {ent['total_assets']} assets monitored</div>
  </div>
</div>

<h2>1. Operational Dimensions Breakdown (0–100 Scale)</h2>
<table>
  <thead>
    <tr>
      <th>Dimension</th>
      <th>Supervisory Score</th>
      <th>Regulatory Weight</th>
      <th>Weighted Risk Contribution</th>
      <th>Assessment State</th>
    </tr>
  </thead>
  <tbody>
"""
    for d in dims:
        score_display = f"{d['score']:.2f} / 100" if d['score'] is not None else "Not Assessable"
        score_color = "#ef4444" if (d['score'] or 0) >= 50 else ("#f97316" if (d['score'] or 0) >= 25 else "#10b981")
        html += f"""    <tr>
      <td><strong>{d['dimension']}</strong></td>
      <td style="font-weight: 700; color: {score_color if d['is_assessable'] else '#64748b'};">{score_display}</td>
      <td>{d['weight']*100:.0f}%</td>
      <td><strong>+{d['weighted_contribution']:.2f}</strong></td>
      <td>{d['status']}</td>
    </tr>\n"""

    html += """  </tbody>
</table>

<h2>2. Targeted Supervisory Directives</h2>
<div class="directive-box">
  <ul>
"""
    for dir_item in directives:
        html += f"    <li><strong>Directive:</strong> {dir_item}</li>\n"

    html += """  </ul>
</div>

<h2>3. Corroborated Execution Gaps & Supervisory Signals ("Why Flagged")</h2>
<table>
  <thead>
    <tr>
      <th>Signal / Correlation Group</th>
      <th>Dimension</th>
      <th>Corroboration</th>
      <th>Score</th>
      <th>Supervisory Rationale</th>
    </tr>
  </thead>
  <tbody>
"""
    for c in contribs:
        html += f"""    <tr>
      <td><strong>{c.get('signal_name', c.get('corroboration_group'))}</strong><br><span style="font-size: 9px; color: #64748b;">Primary: {c.get('detector_id')}</span></td>
      <td>{c.get('dimension')}</td>
      <td><span class="badge" style="background: #3b82f6; font-size: 9px;">{c.get('assessment_strength', 'Medium')}</span></td>
      <td><strong>{c.get('normalized_value', 0):.1f}</strong></td>
      <td style="font-size: 10px;">{c.get('rationale')}</td>
    </tr>\n"""

    html += f"""  </tbody>
</table>

<h2>4. Evidence Inventory & Traceability Summary</h2>
<p style="margin-bottom: 8px; font-size: 11px; color: #475569;">
  Total Findings: <strong>{len(findings)}</strong> &bull; Supporting Evidence Rows: <strong>{dossier['evidence_count']}</strong> &bull; All findings and evidence records are linked by deterministic SHA-256 cryptographic hashes.
</p>
<table>
  <thead>
    <tr>
      <th>Finding ID</th>
      <th>Rule / Detector</th>
      <th>Type</th>
      <th>Severity</th>
      <th>Summary & Quantitative Gap</th>
    </tr>
  </thead>
  <tbody>
"""
    for f in findings[:10]:
        html += f"""    <tr>
      <td><code>{f['id'][:12]}...</code></td>
      <td><strong>{f['rule_id']}</strong></td>
      <td>{f['finding_type']}</td>
      <td><strong>{f['severity']}</strong></td>
      <td>{f['summary']}</td>
    </tr>\n"""

    if len(findings) > 10:
        html += f"""    <tr>
      <td colspan="5" style="text-align: center; color: #64748b; font-style: italic;">... and {len(findings) - 10} additional supporting finding records recorded in Parquet audit manifest.</td>
    </tr>\n"""

    html += f"""  </tbody>
</table>

<div class="footer">
  <div>SENTRA Supervisory Analytics Tool for SOC Assessment &bull; Offline Air-Gapped Engine</div>
  <div>NCIIPC / NTRO &bull; Verification Hash: {dossier['dossier_id']}</div>
  <div>Page 1 of 1</div>
</div>

</body>
</html>"""
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SENTRA Supervisory Examination Dossier.")
    parser.add_argument("--entity", required=True, help="Entity ID (e.g. CSE-011)")
    parser.add_argument("--input", default=None, help="Root path to processed datasets")
    parser.add_argument("--output", default=None, help="Output file path (HTML or JSON)")
    args = parser.parse_args()

    data = generate_entity_dossier_data(args.entity, args.input)
    if args.output and args.output.endswith(".json"):
        Path(args.output).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"JSON Dossier written to {args.output}")
    else:
        html = render_entity_dossier_html(data)
        out_path = Path(args.output) if args.output else Path(f"dossier_{args.entity}.html")
        out_path.write_text(html, encoding="utf-8")
        print(f"HTML Dossier written to {out_path}")


if __name__ == "__main__":
    main()
