from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.analytics.store import PhaseNotFoundError, PhaseStore
from app.config import settings
from app.main import app

PHASE_ROUTES = [
    "/analytics/execution-gap/findings",
    "/analytics/negative-space/findings",
    "/analytics/peer-anomaly/findings",
    "/findings",
]


def _write_fixture(output_dir: Path, with_data: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if with_data:
        pl.DataFrame(
            {
                "id": ["F-1"],
                "rule_id": ["EG001"],
                "entity_id": ["CSE-001"],
                "title": ["Fixture finding"],
            }
        ).write_parquet(output_dir / "findings.parquet")
        pl.DataFrame(
            {
                "id": ["EV-1"],
                "finding_id": ["F-1"],
                "field": ["fixture_field"],
                "value": ["fixture_value"],
            }
        ).write_parquet(output_dir / "evidence.parquet")
    return output_dir


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return TestClient(app)


def test_phase_store_missing_output_is_empty_not_error(tmp_path: Path) -> None:
    store = PhaseStore("phase6", tmp_path / "missing")
    assert store.read_findings() == []
    assert store.read_finding_count() == 0
    with pytest.raises(PhaseNotFoundError):
        store.get_finding("F-1")


def test_phase_store_reads_findings_and_evidence(tmp_path: Path) -> None:
    output_dir = _write_fixture(tmp_path / "phase6")
    store = PhaseStore("phase6", output_dir)
    assert store.read_finding_count() == 1
    findings = store.read_findings()
    assert findings[0]["id"] == "F-1"

    detail = store.get_finding("F-1")
    assert detail.finding["id"] == "F-1"
    assert detail.finding["rule_id"] == "EG001"
    assert len(detail.evidence) == 1
    assert detail.evidence[0]["finding_id"] == "F-1"


def test_phase_store_unknown_finding_raises(tmp_path: Path) -> None:
    store = PhaseStore("phase6", _write_fixture(tmp_path / "phase6"))
    with pytest.raises(PhaseNotFoundError):
        store.get_finding("F-NOPE")


def test_findings_list_empty_output_dir_returns_empty_list(client: TestClient, tmp_path: Path) -> None:
    empty_dir = _write_fixture(tmp_path / "empty", with_data=False)
    for route in PHASE_ROUTES:
        resp = client.get(route, params={"output_path": str(empty_dir)})
        assert resp.status_code == 200
        assert resp.json() == []


def test_findings_detail_missing_output_dir_returns_404(client: TestClient, tmp_path: Path) -> None:
    missing_dir = tmp_path / "does-not-exist"
    for route in PHASE_ROUTES:
        resp = client.get(f"{route}/F-1", params={"output_path": str(missing_dir)})
        assert resp.status_code == 404


def test_findings_detail_unknown_id_returns_404(client: TestClient, tmp_path: Path) -> None:
    output_dir = _write_fixture(tmp_path / "phase6")
    for route in PHASE_ROUTES:
        resp = client.get(f"{route}/F-NOPE", params={"output_path": str(output_dir)})
        assert resp.status_code == 404


def test_findings_detail_known_id_returns_finding_and_evidence(
    client: TestClient, tmp_path: Path
) -> None:
    output_dir = _write_fixture(tmp_path / "phase6")
    for route in PHASE_ROUTES:
        resp = client.get(f"{route}/F-1", params={"output_path": str(output_dir)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["finding"]["id"] == "F-1"
        assert [e["finding_id"] for e in body["evidence"]] == ["F-1"]