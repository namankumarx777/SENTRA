# SENTRA: Technical Presentation (5 Slides)
### Supervisory Analytics Tool for SOC Assessment
**National Technical Research Organisation (NTRO) / NCIIPC**

---

## Slide 1: The Core Supervisory Problem & Operational Gap

### Background & Motivation
- **The Mandate**: NCIIPC assesses the cyber resilience of Critical Sector Entities (CSEs).
- **The Failure of Compliance Audits**: Policies, self-assessments, KPI dashboards, and audit checklists consistently miss operational weaknesses.
- **The Two Hidden Failure Modes**:
  1. **Execution Gaps**: Policies say critical alerts are escalated in 15 mins; operational evidence reveals rapid closures in <2 mins without remediation or escalation.
  2. **Negative Space**: Critical assets producing zero security telemetry, missing essential alert categories (e.g. host/EDR), or orphan alerts with zero investigation cases.
- **The Supervisory Solution**: SENTRA automates the extraction of operational evidence from periodic submissions without replacing human examiners.

---

## Slide 2: High-Level Solution Architecture

### 100% Offline, Air-Gapped 6-Stage Analytical Pipeline

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   CSE PERIODIC SUBMISSIONS (CSV / JSON)                │
│    Alerts • Case Records • Asset Inventory • Escalations • Metadata     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Canonical Ingestion & Schema Normalization (Apache Parquet + DuckDB)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Deterministic Feature Engineering (Durations, Ratios, Time Windows)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ Rules Engine     │      │ Execution Gaps   │      │ Negative Space   │
│ (R001–R005)      │      │ (EG001–EG004)    │      │ (NS001–NS005)    │
└─────────┬────────┘      └─────────┬────────┘      └─────────┬────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Cohort Benchmarking (PB001–PB004) & scikit-learn Multivariate Isolation Forest │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Supervisory Risk & Triage Engine (Anti-Double-Counting + Review Queue) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Supervisor UI: National Overview • Entity Detail • SED Audit Dossier   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Slide 3: Core Supervisory & Mathematical Innovations

1. **Anti-Double-Counting Correlation Engine**:
   - Multiple detectors flagging the same issue (e.g. `R002` + `EG001` + `PB001`) are unified into one correlation group with a bounded corroboration boost (+12%/+24%), preventing artificial risk score explosion.
2. **Feature-Aware Dimension Isolation**:
   - Multivariate anomaly detector `AN001` participates in a dimension *only* when its contributing feature vector explicitly belongs to that dimension.
3. **Unassessable $\ne$ Compliant**:
   - Entities with missing telemetry denominators are flagged `is_assessable = False`; unassessable dimensions are excluded from score denominators rather than fabricating compliance.
4. **Review Urgency $\ne$ Risk Severity**:
   - Prioritizes inspector time by elevating entities with systemic execution shortfalls and blindspots at the top of the queue.

---

## Slide 4: Case Study: Auditing CSE-011 (North Grid 11 Energy)

### Live Forensic Decomposition
- **Overall Supervisory Risk**: **`53.22 / 100`** (`HIGH RISK` Band)
- **Review Priority**: **`100.0 / 100`** (`HIGH URGENCY` — Rank #1 in Review Queue)
- **Dimensional Breakdown**:
  - **Investigation**: `100.0 / 100` (Corroborated by `R004`, `EG002` [12.5 min median vs 20.0 min baseline], `PB002`, `AN001`)
  - **Escalation**: `93.00 / 100` (Unescalated critical incidents)
  - **Remediation**: `40.59 / 100` (Remediation lag)
  - **Monitoring**: `0.00 / 100` (Normal baseline)
- **Deterministic Evidence Traceability**:
  - Inspectors click any finding to view the exact source table, field, and value (e.g. `case_features.critical_median_investigation_minutes = 12.5`).
- **Supervisory Examination Dossier (SED)**:
  - One-click exportable regulatory briefing brief (PDF / JSON) with formal supervisory directives.

---

## Slide 5: Deployment, Scalability & Regulatory Compliance

### Air-Gapped Operational Readiness
- **Zero Cloud & Zero SaaS Dependency**: Runs 100% offline in NCIIPC-controlled air-gapped environments.
- **Embedded Storage Engine**: Uses Polars, DuckDB, and Apache Parquet (zero PostgreSQL/external DB requirement).
- **Sub-Second Latency & High Scalability**: Evaluates hundreds of thousands of alert records across multi-year CSE cohorts in under 2 seconds.
- **Auditable Cryptographic Integrity**:
  - SHA-256 finding and evidence IDs guarantee complete reproducibility and tamper-evident supervisory findings.
- **Validation**: 92 automated tests verifying determinism, mathematical bounds, and peer cohort statistics.
