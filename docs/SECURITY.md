# Security — SAT-SA / SENTRA (Phase 15 adversarial audit)

Scope: a local, operator-run, offline application. The attacker model is therefore **any person present at the operating machine** (or able to submit to the local API over localhost / the local LAN) with access to read or submit data — not a remote Internet threat (there is no Internet exposure). Security claims below are measured against this model.

## 1. Security posture summary

| Area | Result |
|---|---|
| Network exposure | API binds localhost; no outbound network capability in `backend/app/*` (grep: `requests`/`urllib`/`aiohttp`/`httpx`/`socket`/`http.client` = none). Frontend calls `http://localhost:8000` only. |
| App attack surface | FastAPI REST (blockchain/admin/analytics/ingestion routers), static cohort/feature endpoints, HTML dossier renderer, file ingestion. |
| Building blocks | No database; canonical parquet + in-memory ledger. No ORM/ORM-injection surface. |
| Biggest gaps | Path-sandbox bypass (C1), stored-XSS dossier (C9), payload-limit bypass (C15), debug-style exception detail (C14), ledger fakery weaknesses (C18/C19/NEW-1). |

## 2. Verified behaviours — what works today

- **Path sandbox exists** at the API layer (`backend/app/api/security.py:22` `safe_resolve_path`) and is applied to the phase-4 trust boundary and the blockchain data-directory parameter. It blocks straightforward `..` traversal and plain absolute OS paths *that don't start with the base string*.
- **CSP is set** (`frontend/next.config.ts:19`: `connect-src 'self' http://localhost:8000`, `script-src 'self'`, `style-src 'unsafe-inline'`). No external CDNs.
- **No secrets in repo**; no cloud credentials; no outbound analytics.
- **Tests**: `tests/test_api_security.py` (path traversal refusal, payload limit), `tests/test_atomic_writes.py` (no partial parquet writes), plus ingress auth-free local interface (by design — operator machine).

## 3. Defects found (see `docs/JUDGE_QA_MATRIX.md` for reproductions)

| ID | Defect | Severity (this deployment) | Implication |
|---|---|---|---|
| C1 | Path-sandbox **prefix bypass**: base `O:\sat-sa\data` accepts `O:\sat-sa\data_evil\...` and any absolute path that starts with the base string. | High | A local caller can reach sibling directories whose names begin with `data`, or any path under a mounting point matching the prefix. Fix: real containment (`Path.relative_to(base)` after resolve, or `os.path.commonpath`). |
| C9 | Stored XSS in rendered HTML dossier: entity-controlled strings interpolated unescaped. | Medium–High | Any pipeline-produced text (entity/sector names, directive, rationale, finding summary) is rendered verbatim; a crafted name would execute if the dossier is opened in a browser with JS enabled. Fix: HTML-escape at the template boundary. |
| C14 | API `detail` echoes absolute host paths (`NotADirectoryError` with `O:\sat-sa\data\data\processed\...`). | Medium | Information disclosure of the host layout to anyone calling the API. Fix: log full error server-side, return a stable error code/token. |
| C15 | Payload-size middleware keys on `Content-Length` only; chunked/header-less uploads bypass the cap. | Medium | 100 MB upload cap not enforced for all transports. Fix: also reject `transfer-encoding: chunked` or stream-count bytes. |
| C18 | `seed_initial_commitments` swallows all exceptions (`except Exception: pass`) **and** runs inside read endpoints (`list_records`, `get_all_history`). | Medium | Silent ledger inconsistency + read endpoints with write side-effects; seeded state can silently mismatch disk state. |
| C19 | `register_evidence_commitment` silently maps an unknown `evidence_id` to `evidence_list[0]` and records it under the asked-for id. | Medium | Integrity mislabelling: a commitment "for EV-X" can actually commit EV-Y's digest. Fix: validate presence; fail closed. |
| NEW-1 | `_find_finding_in_stores` labels `sourcePhase` by loop position, so an EG002 (phase 6) finding was committed with `sourcePhase=phase5`. | Medium | Ledger provenance phase is wrong for cross-directory findings; breaks phase-trace audit. |
| C2 | Blockchain default data-directory resolves to non-existent `settings.data_dir/"data/processed"` (`…\data\data\processed`); falls back to the whole `data` dir. | High | What gets committed as "the submission" is not what is intended. Fix: `settings.data_dir / "processed"`. |
| C4 | In-memory `LocalLedgerClient` reports `connected/local-permissioned` with no Fabric network behind it. | High for claim-honesty | `/blockchain/status` is cosmetic; there is no cryptographic immutability over-the-wire today. See `docs/OPERATIONS.md` for live-chaincode path. |
| C3 | Blockchain start scripts reference `chaincode/SENTRA-integrity`; the actual directory is `chaincode/sat-sa-integrity`. | Medium (ops) | `docker-compose` chaincode install fails out-of-the-box. Fix in scripts. |
| C5/C6 | Negative-space and R005 normalisation direction bugs (monitoring dimension). | Medium (analytics accuracy, see Scorecard) | These are analytics-correctness defects, not spoofing vectors, but they change risk output for real entities. |
| C8 | Dossier always shows score 0.0 / LOW (wrong column names). | High (credibility) | Any judge opening a dossier sees the wrong band; fix the two `.get()` keys. |

## 4. Residual risk register (accepted)

| Item | Accepted? | Rationale |
|---|---|---|
| In-memory ledger without Fabric network | Yes, for demo | Documented; local data remains unforgeable only by file-hash + parquet read-back, protected by the operator's own workstation controls. |
| XSS dossier | No — must fix | Single-user click-through into a locally-served page still counts as an information disclosure for real entity names. |
| No authentication on local API | Yes (deployment) | Air-gapped, bind-to-localhost operator deployment; auth would add an offline key-distribution burden with no remote threat. Note for lateral-moving malware: no creds to steal helps, but C1/C9 fixes still matter. |
| Content-Length bypass | No — must fix | Trivially fixable. |

## 5. Recommended fixes (ordered)

1. C1 — path containment via `relative_to`.
2. C8 — dossier column mapping.
3. C9 — HTML-escape dossier rendering.
4. C2 — `data/processed` prefix correction in `blockchain.py`.
5. NEW-1 / C19 — fail closed on evidence-id validation; fix phase-naming by directory.
6. C15 — chunked transfer guard.
7. C18 — remove GET-side-effect seeding; log (not swallow) seed failures.
8. C14 — stop echoing absolute paths in `detail`.
9. C3 / C4 / C10 — doc + script honesty pass.

*Reproduced evidence for every C-id lives in `docs/JUDGE_QA_MATRIX.md`.*