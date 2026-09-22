# SAT-SA Scorecard against the Problem Statement

This document is the judge-facing scorecard: every Problem-Statement requirement is scored `IMPLEMENTED` / `PARTIALLY IMPLEMENTED` / `NOT IMPLEMENTED` / `NOT APPLICABLE` / `UNVERIFIED`, with the evidence that supports the score and any caveat that would change a reader's confidence. A requirement is never scored `IMPLEMENTED` on the strength of a claim; the score references where the evidence is reproduced.

Score symbols: ✅ = IMPLEMENTED · ◑ = PARTIALLY IMPLEMENTED · ❌ = NOT IMPLEMENTED · ➖ = NOT APPLICABLE · ❔ = UNVERIFIED.

---

## A. Out of scope (§1)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 1 | Autonomous enforcement decisions | ✅ | No policy/enforcement logic exists; output is advisory signals only (`CONTEXT.md`). |
| 1 | SOC analyst replacement / automated triage | ✅ | No analyst-facing automation; `CONTEXT.md` boundary. |
| 1 | Live SIEM telemetry/packet analysis | ✅ | Batch ingestion only; `backend/app/ingestion/` has no live connectors. |
| 1 | Probabilistic risk / scoring-as-truth | ✅ | Scores are bounded operational indicators (0–100, non-probabilistic) and labelled as such. |

## B. Data environment (§2)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 2 | Periodic submissions: alert, case, workflow, escalation, disposition/closure, asset inventory | ✅ | Canonical five datasets built and populated (12-CSE corpus); `backend/app/ingestion/models.py`; `data/processed/phase2-canonical`. |
| 2 | Minimise dependence on raw logs / sensitive data | ✅ | Structured metadata only; no raw-log or PII ingestion path. |

## C. Core supervisory problem (§3)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 3A | Execution gaps | ✅ | EG001–EG004 live; determinism-tested. |
| 3B | Negative space | ✅ | NS001–NS005 live. Caveat C5: NS001/NS002 risk normalisation direction is inverted (⟶ High for monitoring dimension). |

## D. Functional requirements (§4)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 4.1 | Multiple CSE ingestion | ✅ | 12-CSE corpus; multi-upload API. |
| 4.2 | CSV / JSON / databases / APIs | ◑ | CSV+JSON+Parquet. DB "exports" supported only as files; live DB/API connectors NOT IMPLEMENTED by design (offline). |
| 4.3 | Large, multi-entity, multi-period datasets | ✅ | Commodity: Polars/DuckDB vectorised; `entity_month_features.parquet` multi-period; scale in `docs/PERFORMANCE.md`. |
| 4.4 | Detection/investigation/escalation indicators | ✅ | Rules + EG + NS across the three dimensions; live dimension scores. |
| 4.5 | Execution-gap detection | ✅ | Phase 6, determinism-tested. |
| 4.6 | Negative-space detection | ✅ | Phase 7, determinism-tested; caveat C5. |
| 4.7 | Anomalies / outliers | ✅ | AN001 IsolationForest; caveat C10 (docs say PyOD, sklearn used). |
| 4.8 | Peer benchmarking | ✅ | PB001–PB004, cohort statistics. |
| 4.9 | Entity-level risk indicators | ✅ | 6-dimension bounded ensemble; live (CSE-011 = 53.22 / HIGH). |
| 4.10 | Prioritisation of entities/controls/processes/samples | ✅ | 21-item review queue, 9 HIGH; formula in `priority.py`. |
| 4.11 | Clear rationale | ✅ | Every finding has `rationale`/`summary`. |
| 4.12 | Supporting evidence | ✅ | Evidence parquet per phase + `/findings/{id}` detail. |
| 4.13 | Traceability / auditability | ◑ | Deterministic finding IDs + SHA-256 ledger; but C12 (manifest timestamps) + NEW-1 (phase label) + documented ledger-phasing issues. |
| 4.14 | Explain "why flagged" | ◑ | `top_reason`, contributions, dossiers; but C7 (primary-detector label) and C8 (dossier reads wrong columns → shows 0.0/LOW). |
| 4.15 | Dashboards / reports | ✅ | Frontend (overview, CSEs, entity, review-queue, data-quality, analytics, blockchain) + printable dossier HTML. |
| 4.16 | Trend analysis | ◑ | Multi-period data (monthly) exists and is used in NS004; no dedicated trend/multi-period reporting surface found in `frontend/app`. |
| 4.17 | Drill-down to evidence | ✅ | Findings-detail APIs for all phases; frontend + dossier navigation. |

## E. Deployment (§5)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 5.1 | Fully offline | ✅ | No outbound imports in backend; frontend localhost-only. |
| 5.2 | No internet | ✅ | Same evidence. |
| 5.3 | No cloud | ✅ | No cloud SDK/endpoint. |
| 5.4 | No SaaS | ✅ | Local FastAPI + Next.js. |
| 5.5 | No external AI/APIs | ✅ | Local scikit-learn only; no external model. |
| 5.6 | Local deployment / data processing | ✅ | `command.txt`, `README`, `backend/.venv`, offline dataset. |
| AI/ML | Model architecture | ✅ | IsolationForest, deterministic. |
| AI/ML | Hardware requirements | ✅ | CPU-only; estimates in `docs/OPERATIONS.md`. |
| AI/ML | Offline training/inference | ✅ | Fit+infer at runtime; fixed `random_state`. |
| AI/ML | Update mechanism | ✅ | Retrain-on-rerun from local data. |
| AI/ML | Explainability | ✅ | `contributing_deviations`/`contributing_features`; score ceiling 25. |
| AI/ML | Auditability | ◑ | Hashed + ledgered; caveats C12/NEW-1. |

## F. Deliverables (§6), Performance (§7), Validation (§8), Success (§9)

| Ref | Requirement | Score | Evidence / Caveat |
|---|---|---|---|
| 6 | Architecture doc | ✅ | `docs/ARCHITECTURE.md`; NOTE: exceeds 2-page guideline — condense for submission. |
| 6 | Functional design / methodology / data requirements / tool / infra / validation methodology / ops estimates | ◑ | Present in repo docs; infra deployment chaincode script bug C3; live Fabric bring-up ❔ (Docker daemon unavailable at audit). |
| 7 | Performance criteria | ✅ | `docs/PERFORMANCE.md` measurements. |
| 8 | Validation vs expert manual review | ◑ | Protocol invented + harness in `scripts/judge_scenarios/`; human study itself requires NCIIPC reviewers (documented — no false claim). |
| 9 | Success criterion | ◑ | Functional success demonstrated on the 12-CSE corpus; readiness caveated by C5/C8 and ledger-phasing issues until remediated. |

---

## Overall readiness verdict

- **Functional/supervisory capability:** READY — the pipeline demonstrably analyses the corpus, ranks entities, produces a correct review queue, and exposes drill-down evidence offline.
- **Integrity/accuracy:** READY WITH CAVEATS — C8 (dossier always 0.0/LOW), C5 (NS001/NS002 inversion), C7 (primary-detector label), C12/NEW-1 (ledger phasing), C19 (evidence-id fallback) must be remediated or explicitly disclosed to a judge before the tool can be presented as fully trustworthy.
- **Security:** IMPROVE BEFORE PRODUCTION — C1 (path-sandbox bypass), C9 (stored XSS in dossier), C14/C18 (detail-leak + GET-swallowed-exceptions), C15 (chunked payload bypass) require fixes before a wider distribution; none are exploitable in the local single-operator deployment as shipped today, but they are real defects.

**Priorities for any remediation sprint (recommended order):**
1. C8 dossier column mapping (single-line fix: `overall_risk_band`→`risk_band`, `overall_risk_score`→`overall_score`).
2. C1 path containment (must use `Path.relative_to(base)` / `commonpath`, not string prefix).
3. C5/C6 normalisation direction for NS001/NS002/R005 (gap = 1 − coverage; normalise on gap, not activity).
4. C9 escape dossier HTML (html-escape any entity-derived string).
5. NEW-1/C19 ledger phasing + evidence-id validation.
6. C15 `transfer-encoding` guard; C18 remove GET-side-effect seeding; C14 avoid echoing absolute paths.
7. Docs honesty sweep for C4/C10/C2/C3 (blockchain and analytics claims), plus C12 manifest determinism if needed.

*Cross-references: `docs/PS_COMPLIANCE_MATRIX.md` (full row-level matrix), `docs/JUDGE_QA_MATRIX.md` (defect ledger), `docs/MANUAL_REVIEW_VALIDATION.md`, `docs/PERFORMANCE.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`.*