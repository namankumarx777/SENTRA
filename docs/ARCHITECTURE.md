# SENTRA Architecture Specification

**SENTRA** (Supervisory Analytics Tool for SOC Assessment) is an offline-capable supervisory analytics platform designed to evaluate periodic submissions of alerts, cases, assets, and escalations from Critical Sector Entities (CSEs).

---

## 1. High-Level Pipeline Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   CSE PERIODIC SUBMISSIONS (CSV / JSON)                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Canonical Ingestion & Schema Normalization (Parquet)          │
│ • Datetime standardization (naive-UTC) • Missing value handling        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 4: Operational Feature Engineering                               │
│ • Case rates • Escalation ratios • Remediation durations • Asset maps  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ Phase 5: Rules   │      │ Phase 6: Gaps    │      │ Phase 7: Negative│
│ • Deterministic  │      │ • Configured     │      │   Space          │
│   isolated rules │      │   supervisory    │      │ • Unmonitored    │
│   (R001–R005)    │      │   expectations   │      │   assets & blind-│
│                  │      │   (EG001–EG004)  │      │   spots (NS001-5)│
└─────────┬────────┘      └─────────┬────────┘      └─────────┬────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 8: Peer Cohort Benchmarking & Anomaly Detection                  │
│ • Structural cohorts (Sector, Size, Criticality) (PB001–PB004)         │
│ • Multivariate Isolation Forest Contextual Anomaly (AN001, max 25 pts) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 9: Supervisory Risk Engine & Manual Review Prioritization        │
│ • Level 1: Anti-double-counting correlation groups across 6 dimensions │
│ • Level 2: Assessable-weighted overall score (0–100) & risk bands      │
│ • Triage Review Queue separating Review Urgency from Risk Severity    │
│ • Full traceability chain from scores to finding IDs to evidence rows  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 10: Next.js + FastAPI Supervisory Dashboard                      │
│ • National Overview • CSE Registry • CSE Detail • Review Queue         │
│ • Visual Profiling • "Why Flagged?" • Live Evidence Inspector Drawer   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Six Operational Supervisory Dimensions

SENTRA evaluates entities across 6 weighted operational dimensions:

1. **Escalation (25%)**: Prevalence of unescalated critical cases (`R002`), critical escalation execution gaps (`EG001`), and peer deviations (`PB001`).
2. **Investigation (20%)**: Investigation duration gaps (`EG002`), rapid closure prevalence (`R001`, `EG004`), and uninvestigated alerts (`NS005`).
3. **Remediation (20%)**: Asset vulnerability remediation execution gaps (`EG003`), unremediated assets (`R003`), and cohort remediation deviations (`PB003`).
4. **Monitoring (15%)**: Unmonitored critical assets (`R005`, `NS002`) and inactive monitored infrastructure (`NS001`).
5. **Operational Discipline (10%)**: Alert triage stability and operational volatility.
6. **Cyber Resilience (10%)**: Contextual multivariate anomaly score from scikit-learn Isolation Forest (`AN001`, bounded $[0, 25.0]$).

---

## 3. Core Supervisory Principles

1. **Anti-Double-Counting Correlation**:
   When multiple detectors (`R002`, `EG001`, `PB001`, `AN001`) flag the same underlying operational weakness, SENTRA consolidates them into **one** correlation group (`CRITICAL_ESCALATION`) with a bounded corroboration boost (+12% for 2 phases, +24% for 3+ phases), preventing artificial score explosion.

2. **Feature-Aware Dimension Isolation**:
   Multivariate anomaly detector `AN001` participates in a dimension *only* when its `contributing_deviations` explicitly contain a feature relevant to that dimension.

3. **Unassessable $\ne$ Low Risk**:
   Missing telemetry or absent denominators (e.g. `expected_monitored_assets == 0`) are marked `is_assessable = False` with zero assigned risk, and the dimension's weight is excluded from the Level 2 weighted average denominator rather than fabricating compliance.

4. **Review Priority $\ne$ Risk Score**:
   Risk score measures cumulative entity mathematical severity. Review priority is a separate operational triage ranking elevating systemic execution gaps and blindspots to optimize inspector time.

---

## 4. Storage & Querying Contracts

All intermediate and final analytical outputs are stored as Apache Parquet datasets:
- Deterministic ordering and schema validation.
- Zero external database requirement (directly queried via Polars and DuckDB).
- 100% offline-capable execution.
