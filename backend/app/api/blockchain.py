from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.security import safe_resolve_path
from app.config import settings

logger = logging.getLogger("satsa.api.blockchain")

from app.analytics.store import PhaseNotFoundError
from app.blockchain.models import (
    BlockchainStatus,
    IntegrityState,
    LedgerHistoryEntry,
    LedgerRecord,
    VerificationResponse,
)
from app.blockchain.service import integrity_service

router = APIRouter(prefix="/blockchain", tags=["blockchain"])


class SubmissionRegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}
    entity_id: str = Field(..., max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    period: str = Field(..., max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    data_directory: str | None = Field(default=None, description="Path to data directory")


class FindingRegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}
    output_path: str | None = Field(default=None, description="Path to finding dataset")


class EvidenceRegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}
    finding_id: str = Field(..., max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    output_path: str | None = Field(default=None, description="Path to evidence dataset")


class VerifyRecordRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_hash: str | None = Field(default=None, max_length=128)


@router.get("/status", response_model=BlockchainStatus)
def get_blockchain_status() -> BlockchainStatus:
    """Retrieve current Hyperledger Fabric status, channel, and connectivity info."""
    return integrity_service.get_status()


@router.post("/submissions/{submission_id}/register")
def register_submission_endpoint(
    submission_id: str,
    request: SubmissionRegisterRequest,
) -> dict[str, Any]:
    """Register cryptographic commitment for a submission dataset on the Fabric ledger."""
    try:
        if request.data_directory:
            p = Path(request.data_directory)
            if p.is_dir():
                data_dir = p
            else:
                data_dir = safe_resolve_path(settings.data_dir, request.data_directory)
        else:
            # Resolve the canonical submission directory under the configured data
            # root. settings.data_dir already points at the repository's data dir,
            # so join only the child directory name (no duplicate "data" segment).
            default_processed = settings.data_dir / "processed"
            if default_processed.is_dir():
                data_dir = default_processed
            elif (settings.data_dir / "synthetic").is_dir():
                data_dir = settings.data_dir / "synthetic"
            else:
                data_dir = settings.data_dir

        record, tx_id = integrity_service.register_submission_commitment(
            submission_id=submission_id,
            entity_id=request.entity_id,
            period=request.period,
            data_directory=data_dir,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        # Do not echo the filesystem path in the response; log it server-side only.
        logger.warning("Submission registration failed for %s: %s", submission_id, exc)
        raise HTTPException(
            status_code=400,
            detail="Submission data directory is not available under the configured data root.",
        ) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "status": "registered",
        "tx_id": tx_id,
        "record": record.model_dump(by_alias=True),
    }


@router.post("/findings/{finding_id}/register")
def register_finding_endpoint(
    finding_id: str,
    request: FindingRegisterRequest | None = None,
) -> dict[str, Any]:
    """Register cryptographic commitment for an analytical finding on the Fabric ledger."""
    try:
        if request and request.output_path:
            p = Path(request.output_path)
            if p.is_dir() or p.is_file() or p.exists():
                out_path = str(p)
            else:
                out_path = str(safe_resolve_path(settings.data_dir, request.output_path))
        else:
            out_path = None

        record, tx_id = integrity_service.register_finding_commitment(
            finding_id=finding_id,
            output_path=out_path,
        )
    except PhaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "status": "registered",
        "tx_id": tx_id,
        "record": record.model_dump(by_alias=True),
    }


@router.post("/evidence/{evidence_id}/register")
def register_evidence_endpoint(
    evidence_id: str,
    request: EvidenceRegisterRequest,
) -> dict[str, Any]:
    """Register cryptographic commitment for an evidence item on the Fabric ledger."""
    try:
        if request.output_path:
            p = Path(request.output_path)
            if p.is_dir() or p.is_file() or p.exists():
                out_path = str(p)
            else:
                out_path = str(safe_resolve_path(settings.data_dir, request.output_path))
        else:
            out_path = None

        record, tx_id = integrity_service.register_evidence_commitment(
            evidence_id=evidence_id,
            finding_id=request.finding_id,
            output_path=out_path,
        )
    except PhaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "status": "registered",
        "tx_id": tx_id,
        "record": record.model_dump(by_alias=True),
    }


@router.get("/records", response_model=list[LedgerRecord])
def list_ledger_records_endpoint() -> list[LedgerRecord]:
    """List all registered world state records on the Fabric ledger."""
    return integrity_service.list_records()


@router.get("/history", response_model=list[LedgerHistoryEntry])
def list_all_history_endpoint() -> list[LedgerHistoryEntry]:
    """List entire transaction history and block audit sequence."""
    return integrity_service.get_all_history()


@router.post("/seed")
def seed_ledger_endpoint() -> dict[str, Any]:
    """Seed baseline findings and submissions into the ledger."""
    count = integrity_service.seed_initial_commitments()
    return {"status": "success", "seeded_count": count, "total_records": len(integrity_service.list_records())}


@router.get("/records/{record_id}", response_model=LedgerRecord)
def get_ledger_record_endpoint(record_id: str) -> LedgerRecord:
    """Retrieve world state record directly from the Fabric ledger."""
    record = integrity_service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found on ledger")
    return record


@router.post("/records/{record_id}/verify", response_model=VerificationResponse)
def verify_record_endpoint(
    record_id: str,
    request: VerifyRecordRequest | None = None,
) -> VerificationResponse:
    """Verify local/submitted digest against on-chain Fabric commitment."""
    expected_hash = request.expected_hash if request else None
    return integrity_service.verify_record_live(record_id=record_id, expected_hash=expected_hash)


@router.get("/records/{record_id}/history", response_model=list[LedgerHistoryEntry])
def get_ledger_history_endpoint(record_id: str) -> list[LedgerHistoryEntry]:
    """Retrieve full audit trail of ledger modifications and versions for a record."""
    return integrity_service.get_history(record_id)

