# PS Compliance Matrix — SAT-SA / SENTRA

**Audit phase:** Phase 15 (adversarial QA + judge-readiness)
**Source requirement catalogue:** National Critical Information Infrastructure Protection Centre (NCIIPC) *"Supervisory Analytics Tool for SOC Assessment (SAT-SA)"* problem statement (supplied in full).
**Status vocabulary (strict):**
- `IMPLEMENTED` — requirement demonstrably met with recorded evidence in this repository.
- `PARTIALLY IMPLEMENTED` — requirement met for a meaningful subset; the residual is explicitly named.
- `NOT IMPLEMENTED` — no supporting implementation or evidence exists.
- `NOT APPLICABLE` — requirement does not apply to this solution by design (recorded rationale).
- `UNVERIFIED` — implementation may exist but no evidence was produced in this audit; nothing is upgraded to PASS without evidence.

Every row cites the evidence (file path and, where possible, line/symbol) plus the reproduction that supports the status. Defects are referenced as **C-IDs** (cross-referenced in `docs/JUDGE_QA_MATRIX.md`) or documented inline.

---

## 1. Out-of-scope boundaries

| PS Reference | Requirement / Boundary | Status | Evidence |
|---|---|---|---|
| 1.i–1.vi | Must not replace/act as a CSE SOC, perform real-time monitoring, act as a SIEM, centralise SOCs, continuously collect telemetry, or act as a national cyber-monitoring platform. | `IMPLEMENTED` | SENTRA is a periodic, offline, batch analytics pipeline. No telemetry collector, listener, or real-time component exists: `backend/app/ingestion/` is batch file ingestion only; no socket/listener code (`grep` over `backend/app` finds no `socket`/`aiohttp`/`httpx`/`requests` imports). `CONTEXT.md` "Out-of-scope" records the boundary explicitly. |

## 2. Data environment

| PS Reference | Requirement | Status | Evidence |
|---|---|---|---|
| 2.i–2.vi | Periodic submissions: alert metadata, case records, investigation workflow data, escalation records, disposition/closure info, asset/system inventory where available. | `IMPLEMENTED` | Canonical datasets `alerts`, `cases`, `escalations`, `assets`, `entities` ingested to `data/processed/phase2-canonical/…`; `backend/app/ingestion/models.py` (`DATASET_NAMES`, {`alerts`,`cases`,`escalations`,`assets`,`entities`}). Investigation workflow data is represented at feature level (e.g. `investigation_minutes`, `is_escalated`, `is_remediated` in `data/processed/phase4-final/*features.parquet`). |
| 2 | Minimise dependence on raw logs, packet captures, customer information or other sensitive operational data unless clearly justified. | `IMPLEMENTED` | No raw-log/packet/customer-personal-data ingestion paths exist. Inputs are structured metadata (CSV/JSON/Parquet). No PII schemas present. |

## 3. Core supervisory problem coverage

| PS Reference | Requirement | Status | Evidence |
|---|---|---|---|
| 3.A | Execution gaps: documented capability vs operational evidence (quick closures, no escalation, superficial/template investigation, monitoring not effective, metric-gaming behaviour). | `IMPLEMENTED` | Phase 6 execution-gap detectors: `backend/app/analytics/execution_gap/evaluators.py` — EG001 (acknowledged-without-investigation), EG002 (critical case absence signal), EG003 (remediation execution gap), EG004 (unusually rapid closure). Live outputs: `data/processed/execution_gap-final/findings.parquet` (6 findings across CSE-004/006/010/011), manifest records baseline types. Phase 5 rules R001/R002/R004 cover fast closure and missing escalation. |
| 3.B | Negative space: expected evidence absent (missing telemetry, absent alert categories, missing investigations/escalations, unexpectedly low activity, monitoring blind spots, absence vs comparable peers). | `IMPLEMENTED` | Phase 7 negative-space detectors: `backend/app/analytics/negative_space/evaluators.py` NS001–NS005. Live outputs: `data/processed/negative_space-final/findings.parquet`. Cohort-based expected-category detection (NS003) uses peer prevalence (`cohort_telemetry_presence`). Self-history low-activity baseline (NS004). **Caveat (C5):** NS001/NS002 normalized risk contribution currently scales with `observed` activity rather than the gap, inverting risk direction for these two detectors — see `docs/JUDGE_QA_MATRIX.md` C5. |

## 4. Functional requirements

| # | PS Reference | Requirement | Status | Evidence / Reproduction |
|---|---|---|---|---|
| FR-1 | 4.1 | Ingest structured data from multiple CSEs. | `IMPLEMENTED` | Multi-entity ingestion + canonical storage: `backend/app/ingestion/pipeline.py` (`ingest_dataset`), `backend/app/ingestion/normalizers.py`. 12-CSE synthetic corpus generated via `backend/app/data/generate_synthetic.py` and stored under `data/processed/phase2-canonical`. Ingestion API accepts multi-file uploads per CSE: `backend/app/api/ingestion.py` (`/ingestion/import`, `/ingestion/validate`). |
| FR-2 | 4.2 | Support common formats: CSV, JSON, database exports and APIs where available. | `PARTIALLY IMPLEMENTED` | CSV / JSON / Parquet supported (`backend/app/ingestion/readers.py:9` `SUPPORTED_EXTENSIONS`, readers per format). "Database exports" are supported in the form of exported CSV/JSON/Parquet files; no live DB connector and no external API client exist (by design, offline boundary). **Residual named:** direct DB connection and outbound API ingestion are `NOT IMPLEMENTED` and intentionally out of scope for an air-gapped deployment. |
| FR-3 | 4.3 | Support analysis of large datasets spanning multiple entities and time periods. | `IMPLEMENTED` | Vectorised analytics on Polars/DuckDB; per-period features exist: `data/processed/phase4-final/entity_month_features.parquet` (monthly `alert_count`/`case_count` used by NS004, `backend/app/analytics/negative_space/evaluators.py:141-160`). Multiple time periods produced by generator (e.g. monthly series in `entity_month_features`). Stress/scale verification in `docs/PERFORMANCE.md`. |
| FR-4 | 4.4 | Identify indicators of detection, investigation and escalation weaknesses. | `IMPLEMENTED` | R001/R002/R004/R005 (Phase 5), EG001–EG004 (Phase 6), NS001–NS005 (Phase 7) produce findings mapped to Investigation/Escalation/Monitoring dimensions. Dimension scores e.g. CSE-011 `investigation_score=100.0`, `escalation_score=93.0` (`data/processed/supervisory_risk-final/entity_risk.parquet`, reproduced live). |
| FR-5 | 4.5 | Detect potential execution gaps. | `IMPLEMENTED` | Phase 6 engine `backend/app/analytics/execution_gap/engine.py` + `evaluators.py` (EG001–EG004). Determinism proven by `tests/test_execution_gap_engine.py::test_execution_gap_engine_is_traceable_deterministic_and_separate` (identical SHA-256 across two runs). Manifest `data/processed/execution_gap-final/execution_gap_manifest.json`. |
| FR-6 | 4.6 | Detect potential negative space. | `IMPLEMENTED` | Phase 7 engine `backend/app/analytics/negative_space/engine.py` + `evaluators.py` (NS001–NS005). Live outputs `data/processed/negative_space-final/findings.parquet`; determinism test `tests/test_negative_space_engine.py`; manifest `negative_space_manifest.json`. Language-model of findings explicitly avoids negative claims about missing data (e.g. NS002 rationale: "No observable activity does not prove the assets are unmonitored"). |
| FR-7 | 4.7 | Identify anomalies, outliers and suspicious operational patterns. | `IMPLEMENTED` | AN001 Isolation Forest: `backend/app/analytics/peer_anomaly/anomaly.py` (`sklearn.ensemble.IsolationForest`, 11 configured features, `random_state` fixed, `n_jobs=1`). Output `data/processed/peer_anomaly-final/findings.parquet` (12 anomaly findings). **Caveat (C10):** docs (`docs/ARCHITECTURE.md:73`, `docs/PRESENTATION_SLIDES.md:50`) say "PyOD" while implementation uses scikit-learn; and marketing copy on AN001 feature count differs from the code (11 declared, 10 usable on this dataset). |
| FR-8 | 4.8 | Perform peer comparison and benchmarking across entities. | `IMPLEMENTED` | Phase 8 peer anomaly module: `backend/app/analytics/peer_anomaly/benchmarks.py` (PB001–PB004), `cohorts.py` (cohort by sector/size/criticality, minimum cohort 3), `statistics.py`. Manifest `data/processed/peer_anomaly-final/peer_anomaly_manifest.json` records `cohort_definition == ["sector","size","criticality"]`. |
| FR-9 | 4.9 | Generate entity-level supervisory risk indicators. | `IMPLEMENTED` | Phase 9 engine `backend/app/analytics/supervisory_risk/engine.py`; bounded 0–100 overall score from 6 weighted dimensions — `aggregation.py:46-52` (`overall_score` normalised over assessable weights). Live: CSE-011 = 53.22 / HIGH; all 12 entities scored (`data/processed/supervisory_risk-final/entity_risk.parquet`). **Caveat (C8, C5):** dossier generation (`dossier.py`) reads non-existent column names (`overall_risk_band`, `overall_risk_score`) and therefore always reports `0.0 / LOW` in `docs`/HTML output; NS001/NS002 direction inverted (C5). Repository's own `entity_risk.parquet` columns are `overall_score`, `risk_band`. |
| FR-10 | 4.10 | Prioritise entities, controls, processes and alert samples for manual review. | `IMPLEMENTED` | Review queue engineered and live: `data/processed/supervisory_risk-final/review_queue.parquet` — 21 items, 9 HIGH / 6 MEDIUM / 6 LOW urgency (reproduced live). Priority formula `backend/app/analytics/supervisory_risk/priority.py:57` (base + systemic/blindspot/corroboration boosts × evidence factor). Frontend review queue page `frontend/app/review-queue/page.tsx`. |
| FR-11 | 4.11 | Provide clear rationale for findings. | `IMPLEMENTED` | Every finding carries `rationale` + `summary` (detector models `backend/app/analytics/detectors/models.py`; `make_finding`/`negative_finding`/EG finding builders). Verified in live parquet (e.g. NS002 rationale text) and dossier HTML inventory. |
| FR-12 | 4.12 | Present supporting evidence. | `IMPLEMENTED` | `evidence.parquet` per phase, linked to findings via `finding_id`; e.g. `data/processed/phase5-final/evidence.parquet` (77 rows for EG, per manifest) and findings-detail API returns `{"finding":…,"evidence":[…]}` (`backend/app/analytics/store.py` `get_finding`, tested by `tests/test_phase_store.py`). |
| FR-13 | 4.13 | Support traceability and auditability of results. | `IMPLEMENTED` | Deterministic finding IDs (SHA-256 based), canonical hashing (`backend/app/blockchain/hashing.py` canonical JSON + fixed file order), ledger commitments for findings/submissions/evidence (`backend/app/blockchain/service.py`), audit history endpoints (`/blockchain/records/{id}/history`). Blockchain register+verify reproduced live (findings verify `VERIFIED`). **Caveats:** phase label recorded on ledger is wrong for some records (finding registered as `phase5` despite being phase6 — see `docs/JUDGE_QA_MATRIX.md`), and manifests embed a `generated_at` timestamp, so manifest bytes are non-deterministic across runs (C12). |
| FR-14 | 4.14 | Allow supervisors to understand why an entity or activity was flagged. | `IMPLEMENTED` | `EntityRisk.top_risk_dimension`, `top_reason`, `corroboration_summary`, `evidence_strength_summary`, risk contributions (`risk_contributions.parquet`) and per-entity dossier expose the "why". Frontend CSE page renders it. **Caveat (C7):** `build_risk_contributions` labels `participating_detectors[0]` as primary rather than the detector driving the base value (`correlation.py:172-173`), so the "Primary: X" label in dossiers can be misleading. |
| FR-15 | 4.15 | Generate supervisory dashboards and reports. | `IMPLEMENTED` | Frontend: Overview, CSEs, entity detail, review queue, data-quality, analytics, blockchain pages (`frontend/app/*`). Offline HTML administrative dossier with print/PDF (`backend/app/analytics/supervisory_risk/dossier.py` `render_entity_dossier_html`) exposed via `/analytics/supervisory-risk/entities/{id}/dossier/html`. |
| FR-16 | 4.16 | Support trend analysis across entities and time periods. | `PARTIALLY IMPLEMENTED` | Time-period data exists (`entity_month_features.parquet`, NS004 trailing-historical baseline), and Phase 8 benchmarks compare across entities. **Residual named:** no dedicated trend/time-series reporting surface (dashboard or report) plotting an entity's metrics across periods; no queryable multi-period trend endpoint found. |
| FR-17 | 4.17 | Enable drill-down from supervisory findings to underlying evidence. | `IMPLEMENTED` | Findings-detail APIs for each phase return finding + linked evidence (`findings/{id}` on rules/EG/NS/peer/supervisory-risk routers; `backend/app/analytics/store.py`). Frontend CSE page + dossier allow navigation; evidence rows carry `source_type`, `source_id`, `field`, `value`. |

### Illustrative use cases (PS §4, bullets i–ix)

| Use case | Coverage evidence |
|---|---|
| i. High-severity alerts closed unusually quickly | R001 (`rapid_closure_minutes`), R004, EG004. |
| ii. Repeated alerts without root-cause remediation | R003 (`repeat_alert_asset_count`), EG003. |
| iii. Critical alerts closed without escalation | R002, EG001. |
| iv. Critical systems with little/no telemetry | NS002, R005, NS001. |
| v. Significant deviations from peers | Phase 8 PB001–PB004. |
| vi. Missing monitoring coverage for critical environments | R005, NS001, NS002, PB004. |
| vii. Repetitive/superficial investigation patterns | R004, EG002 (deferred EG005 for documentation quality — deferred reason documented in manifests). |
| viii. Metric-satisfying without risk reduction | EG003 (remediation vs activity), R003. |
| ix. Investigation/escalation workload inconsistent with expected activity | NS004 (own-history low activity), EG002 (absence signal), R002. |
| Additional beyond examples | AN001 multi-dimensional contextual anomaly (Cyber Resilience dimension, capped ≤25); NS003 cohort telemetry-category absence; review-queue systemic/blindspot/corroboration boosts (`priority.py`). |

## 5. Deployment requirements (PS §5)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| DR-1 | Operate fully offline (air-gapped). | `IMPLEMENTED` | No outbound network calls in `backend/app/*` (grep for `requests`/`urllib`/`aiohttp`/`httpx`/`socket`/`http.client` = none). Frontend only calls `http://localhost:8000` (`frontend/src/api.ts:16`); CSP `connect-src 'self' http://localhost:8000` (`frontend/next.config.ts:19`). All data bundled locally in `data/`. |
| DR-2 | No Internet connectivity. | `IMPLEMENTED` | Same evidence as DR-1. No external URLs referenced outside build-time lockfiles. |
| DR-3 | No dependency on cloud services. | `IMPLEMENTED` | No cloud SDKs, credentials, or endpoints in code or runtime config. |
| DR-4 | No dependency on SaaS platforms. | `IMPLEMENTED` | Runtime is local FastAPI + Next.js + Polars/DuckDB. |
| DR-5 | No dependency on externally hosted AI models or APIs. | `IMPLEMENTED` | Only local scikit-learn `IsolationForest` with fixed `random_state` (`peer_anomaly/anomaly.py`); pyod present in `requirements.txt` but not used at runtime. Offline training and inference on the local entity-feature matrix. |
| DR-6 | Support local deployment and local data processing. | `IMPLEMENTED` | Local CLI pipeline + local API + local dashboard. Run instructions in `command.txt` / README; venv at `backend/.venv`. |

### AI/ML disclosure (PS §5, where AI proposed)

| Item | Status | Disclosure |
|---|---|---|
| Model architecture | `IMPLEMENTED` | scikit-learn `IsolationForest` (anomaly.py), `n_estimators`/`contamination`/`random_state` from `peer_anomaly/definitions.py`. Deterministic tree ensemble over the entity-feature matrix (11 candidate features; 10 usable on current corpus). Score is a non-probability relative deviation, deliberately branded as contextual evidence, not confidence (see `anomaly.py` rationale string). |
| Hardware requirements | `IMPLEMENTED` | CPU-only, single-process; Polars/DuckDB vectorised. Measured runs in `docs/PERFORMANCE.md`. No GPU required. |
| Offline training and inference | `IMPLEMENTED` | Fit + predict on the local dataset at Phase 8 run time; `random_state` fixed for reproducibility (determinism proven by hash-stable findings test). |
| Model update mechanism | `IMPLEMENTED` | Retrain-on-next-run: re-running Phase 8 on refreshed entity features recomputes the model from local data; no external weight updates. |
| Explainability controls | `IMPLEMENTED` | `contributing_deviations` (anomaly.py) drives `contributing_features` into risk contributions; AN001 participates in a dimension only when its feature vector matches the group's relevance (`correlation.py:70-74`); score capped at `ANOMALY_SCORE_CEILING=25`. |
| Auditability controls | `IMPLEMENTED` | Findings recorded in parquet with deterministic IDs + evidence rows; digest registration on ledger (`hashing.py`, `service.py`) and verify endpoints. **Caveat:** ledger phase-label miscue noted under FR-13. |

## 6. Deliverables (PS §6)

| Deliverable | Status | Evidence |
|---|---|---|
| Solution architecture | `IMPLEMENTED` | `docs/ARCHITECTURE.md` (note: exceeds the 2-page guideline; consolidation recommended before submission). |
| Functional design | `IMPLEMENTED` | `design.md`, `CONTEXT.md`, detector definition files under `backend/app/analytics/*/definitions.py`. |
| Analytics methodology | `IMPLEMENTED` | Phase manifests (`execution_gap_manifest.json`, `negative_space_manifest.json`, `peer_anomaly_manifest.json`, `supervisory_risk_manifest.json`) plus `docs/PRESENTATION_SLIDES.md` methodology slides. |
| Data requirements | `IMPLEMENTED` | `backend/app/ingestion/models.py` schemas; README data dictionary; generator `backend/app/data/generate_synthetic.py`. |
| Tool / prototype | `IMPLEMENTED` | Full backend + frontend + CLI pipeline in this repo; validated by 115 passing tests (`.\backend\.venv\Scripts\pytest.exe -q tests`). |
| Infrastructure requirements | `PARTIALLY IMPLEMENTED` | `docs/OPERATIONS.md` (produced in this phase) covers deployment; blockchain network compose exists (`blockchain/network/docker-compose-test-net.yaml`). Blockchain start scripts reference an incorrect chaincode dir (`SENTRA-integrity` vs actual `sat-sa-integrity`) — **C3**, corrected/noted in `docs/OPERATIONS.md`. |
| Validation methodology | `IMPLEMENTED` | This file, `docs/JUDGE_QA_MATRIX.md`, `docs/MANUAL_REVIEW_VALIDATION.md`, judge scenario tooling `scripts/judge_scenarios/`. |
| Estimated deployment and operational requirements | `PARTIALLY IMPLEMENTED` | `docs/OPERATIONS.md` provides estimates; live chaincode/Fabric bring-up unverified this phase because the Docker daemon was not running during the audit (**reported as UNVERIFIED**, not converted to PASS). |

## 7. Performance criteria (PS §7)

| Criterion | Assessment | Supporting evidence |
|---|---|---|
| Ability to support supervisory assessment | `IMPLEMENTED` | 12-CSE risk assessments, review queue, per-entity dossiers reproduced live from `data/processed`. |
| Detection of execution gaps | `IMPLEMENTED` | EG001–EG004 live outputs; determinism test. |
| Detection of negative space | `IMPLEMENTED` | NS001–NS005 live outputs; NS002/CSE-008 case verified with asset `AST-000444` (critical, 0 alerts). **Caveat C5** for NS001/NS002 normalisation direction. |
| Explainability and auditability | `IMPLEMENTED` (with caveats) | Findings rationale/evidence, deterministic IDs, SHA-256 ledger commitments. Caveats C7, C8, C12, phased-label miscue. |
| Scalability and performance | `IMPLEMENTED` | `docs/PERFORMANCE.md` (stress measurements). Architecture is vectorised in-memory parquet (Polars/DuckDB). |
| Innovation and additional supervisory insights | `IMPLEMENTED` | AN001 contextual anomaly, cross-phase corroboration groups with anti-double-counting, cohort telemetry-category absence (NS003), review-queue urgency synthesis — all beyond the illustrative list. |

## 8. Validation requirement (PS §8)

| Requirement | Status | Evidence |
|---|---|---|
| Explain validation against expert manual-review findings. | `IMPLEMENTED` | `docs/MANUAL_REVIEW_VALIDATION.md` (produced this phase) defines the validation protocol: scenario-based differential review, ground-truth-style controlled corpora, human-examiner blind spot-sampling protocol, precision/recall-style agreement measures, and the repeated-on-audience invariance rule. Judge scenario harness: `scripts/judge_scenarios/`. **Caveat:** ground-truth controls used by synthetic generation remain outside analytical outputs (per `CONTEXT.md`); no end-to-end human-expert agreement study was executable inside this audit and is therefore stated as methodology + harness, not a completed result. |

## 9. Success criterion (PS §9)

**Status: `IMPLEMENTED` (functionally); readiness subject to caveats C5/C7/C8 and blockchain C2/C3/C4 — see verdict in `docs/PS_REQUIREMENT_SCORECARD.md`.**

The pipeline is demonstrably able to analyse a 12-CSE, 500-alert multi-phase corpus, rank entities by supervisory risk, prioritise 21 review items (9 HIGH urgency), and expose per-finding evidence down to asset/alert/case rows in an offline, auditable manner. The audit confirms the capability exists and is exercised; it also documents defects that must be remediated before framing the tool as judge-ready without caveats.

---

*Generated during Phase 15 adversarial QA. Evidence reproductions recorded under `data/` and referenced `tests/`. Cross-reference: `docs/JUDGE_QA_MATRIX.md` (defects/verification), `docs/PS_REQUIREMENT_SCORECARD.md` (scoring), `docs/PERFORMANCE.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`, `docs/MANUAL_REVIEW_VALIDATION.md`.*