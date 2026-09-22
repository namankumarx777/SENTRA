"""Shared pipeline mechanics for SENTRA judge scenarios.

A ``world`` is produced by regenerating a synthetic corpus inside a working
root directory and running the full Phase 4-9 engine stack into that root,
fully self-contained (no writes to the shipped ``data/processed`` corpus).
The scenario oracle is then evaluated against the world's outputs.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.data.generate_synthetic import generate_dataset
from app.analytics.features.feature_pipeline import generate_features
from app.analytics.rules.engine import run_rules
from app.analytics.execution_gap.engine import run_execution_gap
from app.analytics.negative_space.engine import run_negative_space
from app.analytics.peer_anomaly.engine import run_peer_anomaly
from app.analytics.supervisory_risk.engine import run_supervisory_risk

CANONICAL_DIR = "phase2-canonical"
PHASE4 = "phase4-final"
PHASE5 = "phase5-final"
PHASE6 = "execution_gap-final"
PHASE7 = "negative_space-final"
PHASE8 = "peer_anomaly-final"
PHASE9 = "supervisory_risk-final"

PHASE_DIRS = {
    "phase5": PHASE5,
    "phase6": PHASE6,
    "phase7": PHASE7,
    "phase8": PHASE8,
}

DEFAULT_ENTITIES = 12
DEFAULT_ALERTS = 10_000
DEFAULT_SEED = 42


def build_world(root: str | Path, entities: int, alerts: int, seed: int, dataset_id: str) -> Path:
    """Generate a corpus and run Phases 4-9 into ``root``. Returns root."""
    root = Path(root)
    clean(root)
    root.mkdir(parents=True, exist_ok=True)

    canonical = root / CANONICAL_DIR
    generate_dataset(entities, alerts, seed=seed, output_dir=canonical)
    generate_features(canonical, root / PHASE4, dataset_id)
    run_rules(root / PHASE4, root / PHASE5, dataset_id)
    run_execution_gap(root / PHASE4, root / PHASE6, dataset_id)
    run_negative_space(root / PHASE4, root / PHASE7, dataset_id)
    run_peer_anomaly(root / PHASE4, root / PHASE8, dataset_id)
    run_supervisory_risk(root, root / PHASE9, dataset_id)
    return root


def _read_findings(path: Path) -> pl.DataFrame:
    findings = path / "findings.parquet"
    if not findings.is_file():
        return pl.DataFrame()
    return pl.read_parquet(findings)


def load_world(root: str | Path) -> dict[str, object]:
    """Load all phase findings/evidence and Phase 9 outputs into a summary dict."""
    root = Path(root)
    summary: dict[str, object] = {"root": root}
    findings: dict[str, pl.DataFrame] = {}
    evidence: dict[str, pl.DataFrame] = {}
    for phase, dirname in PHASE_DIRS.items():
        phase_dir = root / dirname
        findings[phase] = _read_findings(phase_dir)
        evidence_path = phase_dir / "evidence.parquet"
        evidence[phase] = pl.read_parquet(evidence_path) if evidence_path.is_file() else pl.DataFrame()
    summary["findings"] = findings
    summary["evidence"] = evidence
    risk = root / PHASE9 / "entity_risk.parquet"
    queue = root / PHASE9 / "review_queue.parquet"
    summary["entity_risk"] = pl.read_parquet(risk) if risk.is_file() else pl.DataFrame()
    summary["review_queue"] = pl.read_parquet(queue) if queue.is_file() else pl.DataFrame()
    return summary


def finding_present(summary: dict[str, object], phase: str, rule: str, entity: str | None = None) -> bool:
    df = summary["findings"].get(phase) if isinstance(summary["findings"], dict) else pl.DataFrame()  # type: ignore[union-attr]
    if df is None or df.height == 0 or "rule_id" not in df.columns:
        return False
    mask = df["rule_id"] == rule
    if entity is not None:
        mask &= df["entity_id"] == entity
    return bool(df.filter(mask).height > 0)


def finding_count(summary: dict[str, object], phase: str, rule: str) -> int:
    df = summary["findings"].get(phase) if isinstance(summary["findings"], dict) else pl.DataFrame()  # type: ignore[union-attr]
    if df is None or "rule_id" not in df.columns:
        return 0
    return int(df.filter(df["rule_id"] == rule).height)


def queue_urgency(summary: dict[str, object], entity: str) -> int | None:
    """Return a numeric urgency level (3=HIGH, 2=MEDIUM, 1=LOW) for an entity's
    top queue item, or None if the entity has no queue item."""
    queue = summary["review_queue"]
    if queue is None or queue.height == 0 or "entity_id" not in queue.columns or "priority" not in queue.columns:
        return None
    rows = queue.filter(queue["entity_id"] == entity)
    if rows.height == 0:
        return None
    priority = rows["priority"].to_list()[0]
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(str(priority).upper())


def risk_band(summary: dict[str, object], entity: str) -> str | None:
    risk = summary["entity_risk"]
    if risk.height == 0 or "entity_id" not in risk.columns or "risk_band" not in risk.columns:
        return None
    rows = risk.filter(risk["entity_id"] == entity)
    if rows.height == 0:
        return None
    return str(rows["risk_band"].to_list()[0])


def clean(work_root: Path) -> None:
    """Remove a scenario working root entirely."""
    if work_root.exists():
        shutil.rmtree(work_root, ignore_errors=True)