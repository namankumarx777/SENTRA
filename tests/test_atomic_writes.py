import tempfile
import os
from pathlib import Path

import polars as pl

from app.analytics.rules.engine import write_rule_outputs
from app.analytics.rules.models import RuleRunResult

def test_atomic_write_rules_engine():
    # Create an empty result
    result = RuleRunResult(findings=[], evidence=[], rules_evaluated=["R1"])
    
    with tempfile.TemporaryDirectory() as base_tmp:
        output_dir = Path(base_tmp) / "output"
        
        # Test write
        manifest = write_rule_outputs(result, output_dir, dataset_id="ds-1")
        
        # Verify the atomic rename succeeded
        assert output_dir.exists()
        assert (output_dir / "findings.parquet").exists()
        assert (output_dir / "evidence.parquet").exists()
        assert (output_dir / "rule_manifest.json").exists()
        
        # The temporary directory (starts with .tmp-rules-) should not exist
        # Because we can't easily guess the exact suffix, we check that no directory starting with .tmp exists in the parent
        parent_items = list(Path(base_tmp).iterdir())
        tmp_dirs = [item for item in parent_items if item.name.startswith(".tmp-rules-") and item.is_dir()]
        assert len(tmp_dirs) == 0
