# Operations — SAT-SA / SENTRA (deployment & runtime guidance)

## 1. Deployment model

- **Local, offline, single-operator workstation.** Backend = FastAPI (Python 3.14.4, venv `backend\.venv`). Frontend = Next.js (static build for offline). All data and artefacts under `.\data\`.
- **No cloud, no internet, no SaaS.** Verified: backend imports none of `requests`/`urllib`/`aiohttp`/`httpx`/`socket`/`http.client` (`docs/SECURITY.md` §1). Frontend targets `http://localhost:8000` only.
- **Recommended bind:** API on `127.0.0.1`. Do NOT expose on a shared NIC as shipped (no auth; see Security §4).

## 2. Bring-up

```
# backend
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (offline build, then serve statics)
cd frontend
npm ci          # package-lock pins versions; registry contact needed ONCE at build time
npm run build
npm run start   # or serve .next static output behind any static server
```

The frontend build step is the **only** step that requires network (module downloads at install/build). Once built, everything runs offline. An air-gapped machine must pre-stage `node_modules` (via `npm ci` on an online builder) and copy the artifacts.

## 3. Data operations

- Ingest: CSV / JSON / Parquet per CSE via `backend/app/ingestion` (`/ingestion/validate`, `/ingestion/import`) or file-drop into `data\raw` then run the CLI pipeline.
- Canonical store: `data\processed\phase2-canonical` → feature store `data\processed\phase4-final` → phase outputs per engine.
- Re-runs are deterministic for findings/evidence (same input → same SHA-256 findings); manifests embed a `generated_at` timestamp so **manifest bytes differ** between runs (documented limitation C12).
- Storage footprint is small (current corpus ≈ MB-scale). No retention policy required today; a data directory backup is the primary DR control.

## 4. Ledger / blockchain operation

Two modes:

1. **Local in-memory ledger (default, exercised in the demo).** `LocalLedgerClient` (blockchain in-memory dict). `/blockchain/status` reports `connected/local-permissioned` regardless of any Fabric network because `_is_online` defaults to True — treat that status string as *cosmetic*.
2. **Hyperledger Fabric via `blockchain/network/docker-compose-test-net.yaml`.** Not exercised during the Phase 15 audit because the Docker daemon was unavailable. **Status: UNVERIFIED (not "pass").** Before it can be claimed, the harness must start, install the chaincode, and `docker ps` must show the peers.

**Known blockers for Fabric mode (from code audit):**
- `blockchain/scripts/start.ps1` / `start.sh` reference chaincode dir `SENTRA-integrity`; the actual directory is `chaincode\sat-sa-integrity` (C3). Fix the scripts before attempting bring-up.
- No fabric-gateway client exists in `backend/app/blockchain` (C4); there is currently no code path that talks to the compose network. Implementing one is required before mode 2 is real.

## 5. Admin & review operations

- Review queue: `data\processed\supervisory_risk-final\review_queue.parquet` + `/review-queue` page (21 items / 9 HIGH at audit time) / `/analytics/supervisory-risk/...`.
- Per-entity dossiers: `/analytics/supervisory-risk/entities/{id}/dossier/html` — **C8 caveat:** currently shows 0.0 / LOW for every entity because it reads the wrong column names; use the JSON API (`entity_risk.parquet` `overall_score` / `risk_band`) for accurate numbers until fixed.
- Simulated tamper demo: register → verify → edit → verify again (MISMATCH) works against the local ledger.

## 6. Maintenance

- **Recompute:** re-run the phase pipeline on refreshed canonical data (mechanism for model retraining — the IsolationForest refits from local features each run).
- **Tests:** `.\backend\.venv\Scripts\pytest.exe -q tests` currently 115 passed.
- **Backup:** copy `.\data` + `docs`. There is no DB to dump; parquet files ARE the DB.

## 7. Operational risk register

| Item | Status | Mitigation |
|---|---|---|
| Fabric path unverified | `UNVERIFIED` | Use local ledger for any judge demo until a real Fabric bring-up is proven. |
| Chaincode dir mismatch (C3) | Known bug | Fix scripts or don't claim Fabric mode. |
| Dossier wrong columns (C8) | Known bug | Documented; fixed in next sprint. |
| Manifest non-determinism (C12) | Accepted | Determinism story is on findings/evidence parquet, not manifests. |
| Local API unauthenticated | Accepted (air-gap) | Keep bound to 127.0.0.1. |

*Cross-refs: `docs/SECURITY.md`, `docs/PERFORMANCE.md`, `docs/JUDGE_QA_MATRIX.md`.*