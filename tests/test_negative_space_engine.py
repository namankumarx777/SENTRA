from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.analytics.features.feature_pipeline import generate_features
from app.analytics.negative_space.engine import run_negative_space
from app.config import settings
from app.main import app


def test_negative_space_engine_is_traceable_deterministic_and_queryable(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "data" / "synthetic"
    features = tmp_path / "features"
    generate_features(source, features, "phase2-canonical")
    first, second = tmp_path / "first", tmp_path / "second"
    result = run_negative_space(features, first, "phase2-canonical")
    second_result = run_negative_space(features, second, "phase2-canonical")
    assert result.findings and result.evidence
    assert len(result.findings) == len(second_result.findings)
    assert {"NS001", "NS002", "NS003", "NS005"}.issubset({item.rule_id for item in result.findings})
    assert result.observation_window.sufficient
    finding_ids = {item.id for item in result.findings}
    assert all(item.finding_id in finding_ids for item in result.evidence)
    for name in ["findings", "evidence"]:
        left, right = first / f"{name}.parquet", second / f"{name}.parquet"
        assert hashlib.sha256(left.read_bytes()).digest() == hashlib.sha256(right.read_bytes()).digest()
        assert duckdb.sql(f"select count(*) from read_parquet('{left.as_posix()}')").fetchone()[0] > 0
    manifest = json.loads((first / "negative_space_manifest.json").read_text(encoding="utf-8"))
    assert manifest["deferred_detectors"]["NS006"]
    assert not {"negative_space", "is_negative_space", "risk_score"} & set(pl.read_parquet(first / "findings.parquet").columns)


def test_negative_space_api_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    source = Path(__file__).resolve().parents[1] / "data" / "processed" / "phase4-final"
    input_dir = tmp_path / "api-input"
    shutil.copytree(source, input_dir)
    output = tmp_path / "api-output"
    client = TestClient(app)
    rules = client.get("/analytics/negative-space/rules")
    assert rules.status_code == 200 and len(rules.json()) == 6
    run = client.post("/analytics/negative-space/run", json={"input_path": str(input_dir), "output_path": str(output), "dataset_id": "api-test"})
    assert run.status_code == 200
    findings = client.get("/analytics/negative-space/findings", params={"output_path": str(output)})
    assert findings.status_code == 200 and findings.json()
    detail = client.get(f"/analytics/negative-space/findings/{findings.json()[0]['id']}", params={"output_path": str(output)})
    assert detail.status_code == 200 and detail.json()["evidence"]
