from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.analytics.store import PhaseNotFoundError, PhaseStore
from app.blockchain.fabric_client import get_fabric_client
from app.blockchain.hashing import (
    hash_evidence,
    hash_finding,
    hash_submission_directory,
)
from app.blockchain.models import (
    BlockchainStatus,
    EvidenceCommitment,
    FindingCommitment,
    IntegrityState,
    LedgerHistoryEntry,
    LedgerRecord,
    RecordType,
    SubmissionCommitment,
    VerificationResponse,
)

logger = logging.getLogger("satsa.blockchain")

PHASE_DIRS = (
    ("phase5", "phase5"),
    ("phase5", "phase5-final"),
    ("phase6", "phase6"),
    ("phase6", "execution_gap"),
    ("phase6", "execution_gap-final"),
    ("phase7", "phase7"),
    ("phase7", "negative_space"),
    ("phase7", "negative_space-final"),
    ("phase8", "phase8"),
    ("phase8", "peer_anomaly"),
    ("phase8", "peer_anomaly-final"),
    ("phase9", "phase9"),
    ("phase9", "supervisory_risk"),
    ("phase9", "supervisory_risk-final"),
)


def _resolve_source_phase(finding: dict[str, Any], fallback_phase: str) -> str:
    """Resolve the finding's owning analytical phase.

    The phase is derived from the finding's own detector metadata (rule id),
    never from the store-search loop position, so a finding is attributed to
    the phase that produced it even when a search visits multiple stores.
    """
    rule_id = str(finding.get("rule_id", "") or finding.get("detector_id", ""))
    rule_phase = _rule_to_phase(rule_id)
    if rule_phase is not None:
        return rule_phase
    return fallback_phase


def _rule_to_phase(rule_id: str) -> str | None:
    """Map a detector id to its owning analytical phase (deterministic)."""
    mapping = {
        "R001": "phase5", "R002": "phase5", "R003": "phase5", "R004": "phase5", "R005": "phase5",
        "EG001": "phase6", "EG002": "phase6", "EG003": "phase6", "EG004": "phase6",
        "NS001": "phase7", "NS002": "phase7", "NS003": "phase7", "NS004": "phase7", "NS005": "phase7",
        "AN001": "phase8",
        "PB001": "phase8", "PB002": "phase8", "PB003": "phase8", "PB004": "phase8",
    }
    return mapping.get(rule_id)


def _find_finding_in_stores(finding_id: str, output_path: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Search for finding across phases 5-9."""
    if output_path:
        base = Path(output_path)
        for phase, dirname in PHASE_DIRS:
            store = PhaseStore(phase, base / dirname if (base / dirname).exists() else base)
            try:
                detail = store.get_finding(finding_id)
                return detail.finding, detail.evidence, phase
            except (PhaseNotFoundError, ValueError):
                continue
    # Default search locations (supports running from repo root or backend/)
    data_dir_candidates = [
        Path("data/processed"),
        Path("../data/processed"),
        Path(__file__).resolve().parents[3] / "data/processed",
    ]
    data_dir = next((p for p in data_dir_candidates if p.is_dir()), Path("data/processed"))

    for phase, dirname in PHASE_DIRS:
        store = PhaseStore(phase, data_dir / dirname)
        try:
            detail = store.get_finding(finding_id)
            return detail.finding, detail.evidence, phase
        except (PhaseNotFoundError, ValueError):
            continue
    raise PhaseNotFoundError(f"Finding {finding_id} not found in any phase dataset")


class BlockchainIntegrityService:
    def __init__(self):
        self.client = get_fabric_client()

    def get_status(self) -> BlockchainStatus:
        return self.client.get_status()

    def register_submission_commitment(
        self,
        submission_id: str,
        entity_id: str,
        period: str,
        data_directory: Path | str,
    ) -> tuple[LedgerRecord, str]:
        hashes = hash_submission_directory(data_directory)
        commitment = SubmissionCommitment(
            recordId=submission_id,
            entityId=entity_id,
            period=period,
            contentHash=hashes["content_hash"],
            manifestHash=hashes["manifest_hash"],
            createdAt=datetime.now(timezone.utc).isoformat(),
            registeredBy="SENTRA",
        )
        return self.client.register_submission(commitment)

    def register_finding_commitment(
        self,
        finding_id: str,
        output_path: str | None = None,
    ) -> tuple[LedgerRecord, str]:
        finding, _, phase = _find_finding_in_stores(finding_id, output_path)
        source_phase = _resolve_source_phase(finding, phase)
        digest = hash_finding(finding)
        commitment = FindingCommitment(
            recordId=finding_id,
            entityId=str(finding.get("entity_id", "")),
            findingHash=digest,
            sourcePhase=source_phase,
            detectorId=str(finding.get("rule_id", "")),
            createdAt=datetime.now(timezone.utc).isoformat(),
            registeredBy="SENTRA",
        )
        return self.client.register_finding(commitment)

    def register_evidence_commitment(
        self,
        evidence_id: str,
        finding_id: str,
        output_path: str | None = None,
    ) -> tuple[LedgerRecord, str]:
        _, evidence_list, _ = _find_finding_in_stores(finding_id, output_path)
        target_ev = next(
            (
                ev
                for ev in evidence_list
                if str(ev.get("id") or ev.get("evidence_id")) == evidence_id
                or str(ev.get("source_id")) == evidence_id
            ),
            None,
        )
        if not target_ev:
            raise PhaseNotFoundError(
                f"Evidence {evidence_id} not found for finding {finding_id}"
            )

        digest = hash_evidence(target_ev)
        commitment = EvidenceCommitment(
            recordId=evidence_id,
            entityId=str(target_ev.get("entity_id", "")),
            findingId=finding_id,
            contentHash=digest,
            createdAt=datetime.now(timezone.utc).isoformat(),
            registeredBy="SENTRA",
        )
        return self.client.register_evidence(commitment)

    def verify_record_live(
        self,
        record_id: str,
        expected_hash: str | None = None,
    ) -> VerificationResponse:
        """Verify record against ledger.
        
        If expected_hash is not provided, computes live local hash from storage.
        """
        if not self.client.is_connected():
            return VerificationResponse(
                recordId=record_id,
                status=IntegrityState.UNAVAILABLE,
                localHash=expected_hash or "",
                ledgerHash=None,
                message="Hyperledger Fabric ledger is unavailable",
            )

        # If hash not explicitly provided, try to find and compute from stored finding/evidence
        computed_hash = expected_hash
        if not computed_hash:
            try:
                finding, _, _ = _find_finding_in_stores(record_id)
                computed_hash = hash_finding(finding)
            except PhaseNotFoundError:
                computed_hash = ""

        return self.client.verify_record(record_id, computed_hash)

    def seed_initial_commitments(self) -> int:
        count = 0
        data_dir_candidates = [
            Path("data/processed"),
            Path("../data/processed"),
            Path(__file__).resolve().parents[3] / "data/processed",
        ]
        data_dir = next((p for p in data_dir_candidates if p.is_dir()), None)
        if not data_dir:
            return 0

        # Seed Phase 5 - 9 findings
        for phase, dirname in PHASE_DIRS:
            store_dir = data_dir / dirname
            if not store_dir.is_dir():
                continue
            store = PhaseStore(phase, store_dir)
            try:
                findings = store.read_findings()
                for f in findings:
                    fid = str(f.get("id") or f.get("finding_id", ""))
                    if fid and not self.client.get_record(fid):
                        try:
                            self.register_finding_commitment(fid, output_path=str(store_dir))
                            count += 1
                        except Exception as exc:
                            logger.warning("Seeding finding %s failed: %s", fid, exc)
            except Exception as exc:
                logger.warning("Seeding phase store %s failed: %s", dirname, exc)

        # Also seed sample submissions if available
        for entity_id in ["CSE-A", "CSE-B", "CSE-011", "CSE-012", "CSE-014"]:
            sub_id = f"SUB-{entity_id}-2026-Q1"
            if not self.client.get_record(sub_id):
                try:
                    self.register_submission_commitment(
                        submission_id=sub_id,
                        entity_id=entity_id,
                        period="2026-Q1",
                        data_directory=data_dir,
                    )
                    count += 1
                except Exception as exc:
                    logger.warning("Seeding submission %s failed: %s", sub_id, exc)

        return count

    def list_records(self) -> list[LedgerRecord]:
        # Read-only: never seed records as a side effect of a query.
        return self.client.list_records()

    def get_all_history(self) -> list[LedgerHistoryEntry]:
        # Read-only: never seed records as a side effect of a query.
        return self.client.get_all_history()

    def get_record(self, record_id: str) -> LedgerRecord | None:
        return self.client.get_record(record_id)

    def get_history(self, record_id: str) -> list[LedgerHistoryEntry]:
        return self.client.get_history(record_id)


integrity_service = BlockchainIntegrityService()

