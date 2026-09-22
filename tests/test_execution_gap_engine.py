from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.analytics.execution_gap.engine import run_execution_gap
from app.analytics.execution_gap.definitions import DETECTORS
from app.analytics.features.feature_pipeline import generate_features
from app.config import settings
from app.main import app


def test_execution_gap_engine_is_traceable_deterministic_and_separate(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "data" / "synthetic"
    features = tmp_path / "features"
    generate_features(source, features, "phase2-canonical")
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = run_execution_gap(features, first, "phase2-canonical")
    second_result = run_execution_gap(features, second, "phase2-canonical")
    assert result.findings
    assert len(result.findings) == len(second_result.findings)
    assert {item.rule_id for item in result.findings} <= {"EG001", "EG002", "EG003", "EG004"}
    assert all(item.absolute_gap is not None and item.baseline_method for item in result.findings)
    finding_ids = {item.id for item in result.findings}
    assert all(item.finding_id in finding_ids for item in result.evidence)
    for name in ["findings", "evidence"]:
        left = first / f"{name}.parquet"; right = second / f"{name}.parquet"
        assert hashlib.sha256(left.read_bytes()).digest() == hashlib.sha256(right.read_bytes()).digest()
        assert duckdb.sql(f"select count(*) from read_parquet('{left.as_posix()}')").fetchone()[0] > 0
    manifest = json.loads((first / "execution_gap_manifest.json").read_text(encoding="utf-8"))
    assert manifest["deferred_detectors"]["EG005"] == DETECTORS["EG005"].deferred_reason
    assert manifest["baseline_types"]["EG002"] == "configured_expectation"
    assert manifest["baseline_methods"]["EG003"] == "configured_minimum"
    assert "not statistical confidence" in manifest["evidence_strength_methodology"]


def test_execution_gap_api_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    source = Path(__file__).resolve().parents[1] / "data" / "processed" / "phase4-final"
    input_dir = tmp_path / "api-input"
    shutil.copytree(source, input_dir)
    output = tmp_path / "api-output"
    client = TestClient(app)
    rules = client.get("/analytics/execution-gap/rules")
    assert rules.status_code == 200 and len(rules.json()) == 5
    run = client.post("/analytics/execution-gap/run", json={"input_path": str(input_dir), "output_path": str(output), "dataset_id": "api-test"})
    assert run.status_code == 200 and run.json()["finding_count"] >= 0
    findings = client.get("/analytics/execution-gap/findings", params={"output_path": str(output)})
    assert findings.status_code == 200
    if findings.json():
        detail = client.get(f"/analytics/execution-gap/findings/{findings.json()[0]['id']}", params={"output_path": str(output)})
        assert detail.status_code == 200 and detail.json()["evidence"]
