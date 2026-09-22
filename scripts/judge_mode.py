"""SENTRA judge-mode demo driver.

Presents the offline demo transcript for a judge: scenario-suite disposition,
the live review queue with drill-down affordances, a real evidence tamper
demo over shipped corpus records, and the offline/air-gap attestation.

Usage:
  judge_mode.py                       full transcript (scenarios + queue + tamper + attestation)
  judge_mode.py --queue 10            top-N review queue table only
  judge_mode.py --entity CSE-011      drill into one entity: risk + findings + evidence
  judge_mode.py --tamper              tamper demo over a real shipped evidence row
  judge_mode.py --scenarios           scenario-suite disposition only
  judge_mode.py --no-scenarios        full transcript without re-running the scenario suite

Honesty notes (enforced in the output):
- Ledger is the local in-memory client (no live Fabric network in this build);
  the demo commits a REAL evidence row from ``data/processed``, not story data.
- Any claim that depends on an unverified component is printed with its
  `docs/` reference rather than asserted as fact.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
SCRIPTS = REPO_ROOT / "scripts" / "judge_scenarios"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _runner import PHASE_DIRS, REPO_ROOT as _ROOT  # noqa: E402
from app.blockchain.fabric_client import get_fabric_client  # noqa: E402
from app.blockchain.hashing import hash_evidence  # noqa: E402
from app.blockchain.models import EvidenceCommitment  # noqa: E402

PROCESSED = _ROOT / "data" / "processed"


def _load_world() -> dict[str, object]:
    from _runner import load_world
    return load_world(PROCESSED)


def _phase_order() -> list[str]:
    return ["phase5", "phase6", "phase7", "phase8"]


def _fmt_rows(rows: list[dict], max_colwidth: int = 60) -> str:
    if not rows:
        return "(no rows)"
    keys = list(rows[0].keys())
    widths = {k: max(len(k), *(len(str(r.get(k, ""))[:max_colwidth]) for r in rows)) for k in keys}
    def line(r):
        return "  ".join(str(r.get(k, ""))[:max_colwidth].ljust(widths[k]) for k in keys)
    out = [line({k: k for k in keys}), "  ".join("-" * widths[k] for k in keys)]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def table_queue(queue: pl.DataFrame, limit: int | None = None) -> None:
    print(f"\n-- Review queue ({queue.height} items) --")
    if queue.height == 0:
        print("   (empty)")
        return
    cols = ["rank", "entity_id", "record_type", "record_id", "priority", "priority_score", "evidence_strength"]
    cols = [c for c in cols if c in queue.columns]
    show = queue.select(cols)
    if limit:
        show = show.head(limit)
    print(_fmt_rows(show.to_dicts(), max_colwidth=22))


def entity_drill(entity_id: str) -> None:
    summary = _load_world()
    risk = summary["entity_risk"]
    findings = summary["findings"] or {}
    evidence = summary["evidence"] or {}

    print(f"\n-- Entity drill: {entity_id} --")
    if risk.height and "entity_id" in risk.columns:
        row = risk.filter(risk["entity_id"] == entity_id)
        if row.height:
            keep = [c for c in ["entity_id", "overall_score", "risk_band", "top_reason", "evidence_strength_summary"] if c in row.columns]
            print(_fmt_rows(row.select(keep).to_dicts()))

    total_ev = 0
    for phase in _phase_order():
        df = findings.get(phase)
        if df is None or df.height == 0:
            continue
        subset = df.filter(df["entity_id"] == entity_id) if "entity_id" in df.columns else df
        if subset.height == 0:
            continue
        counts = Counter(str(x) for x in subset["rule_id"].to_list())
        ev = evidence.get(phase)
        ev_count = int(ev.filter(ev["entity_id"] == entity_id).height) if ev is not None and "entity_id" in ev.columns else 0
        total_ev += ev_count
        print(f"  {phase}: {len(subset)} findings {dict(sorted(counts.items()))}  ({ev_count} evidence rows)")
        for f in subset.head(3).to_dicts():
            print(f"      - {f['rule_id']} {f['id']}  sev={f['severity']}  {f.get('summary', '')[:90]}")
    print(f"  total evidence rows for entity: {total_ev}")


def tamper_demo() -> None:
    print("\n-- Tamper-evidence demo (real shipped evidence records) --")
    phase_dir = PROCESSED / PHASE_DIRS["phase6"]
    evidence_path = phase_dir / "evidence.parquet"
    findings_path = phase_dir / "findings.parquet"
    if not evidence_path.is_file() or not findings_path.is_file():
        print("   ERROR: phase6 evidence/findings not present in the shipped corpus")
        return
    ev = pl.read_parquet(evidence_path)
    fd = pl.read_parquet(findings_path)

    eg002 = fd.filter(fd["rule_id"] == "EG002")
    if eg002.height == 0:
        print("   ERROR: no EG002 finding to anchor the demo")
        return
    target_finding = eg002.head(1).to_dicts()[0]
    target_finding_id = target_finding["id"]
    row = ev.filter(ev["finding_id"] == target_finding_id)

    if row.height == 0:
        print("   ERROR: evidence row for EG002 not found")
        return
    evidence_row = row.head(1).to_dicts()[0]

    entity_id = str(evidence_row.get("entity_id", "CSE-011"))
    digest = hash_evidence(evidence_row)
    record_id = f"EVD-JUDGE-{digest[:8]}"
    client = get_fabric_client()

    client.register_evidence(
        EvidenceCommitment(
            recordId=record_id,
            entityId=entity_id,
            findingId=target_finding_id,
            contentHash=digest,
            createdAt=datetime.now(timezone.utc).isoformat(),
        )
    )
    print(f"  [+] committed real evidence row {evidence_row.get('id')} of finding {target_finding_id}")
    print(f"      digest = {digest}")

    res = client.verify_record(record_id, digest)
    print(f"  [verify] {res.message}  ({res.status if hasattr(res, 'status') else ''})")

    tampered = dict(evidence_row)
    if isinstance(tampered.get("value"), (str, int, float)):
        tampered["value"] = str(tampered["value"]) + "-TAMPERED"
    else:
        tampered["reason"] = str(tampered.get("reason", "")) + "-TAMPERED"
    tangest = hash_evidence(tampered)
    res2 = client.verify_record(record_id, tangest)
    print(f"  [!] tampered local record digest = {tangest}")
    print(f"  [verify] {res2.message}")
    print(f"  caveat: ledger is local in-memory (docs/JUDGE_QA_MATRIX.md C4); " 
          f"the same byte-level digest check underpins the canonical hash path used by the API.")


def offline_attestation() -> None:
    print("\n-- Offline / air-gap attestation --")
    import re
    scan_dirs = [BACKEND / "app"]
    poison = ["requests", "urllib", "aiohttp", "httpx", "socket", "http.client"]
    hits: list[tuple[str, str]] = []
    for base in scan_dirs:
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if re.search(r"^\s*(import|from)\s+(" + "|".join(poison) + r")", text, re.M):
                hits.append((path.name, path.name))
    print(f"  outbound-network imports in backend/app: {len(hits)}")
    print("  frontend API base: http://localhost:8000 only (see docs/SECURITY.md)")
    print("  attestation evidence: docs/SECURITY.md sec 1, docs/OPERATIONS.md sec 1")


def run_scenarios() -> None:
    print("\n-- Scenario-suite disposition (fresh self-contained worlds) --")
    python = sys.executable
    result = subprocess.run(
        [python, str(SCRIPTS / "run_scenario.py"), "--all", "--no-clean"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print(f"  scenario suite exit code: {result.returncode} (scenarios are expected to PASS)")
    else:
        print("  scenario suite exit code: 0 (ALL SCENARIOS PASS)")


def main() -> None:
    parser = argparse.ArgumentParser(description="SENTRA judge-mode demo driver")
    parser.add_argument("--queue", type=int, default=None, help="print top-N review-queue items")
    parser.add_argument("--entity", type=str, default=None, help="drill into one entity")
    parser.add_argument("--tamper", action="store_true", help="run the tamper demo only")
    parser.add_argument("--scenarios", action="store_true", help="run the scenario suite only")
    parser.add_argument("--no-scenarios", action="store_true", help="skip scenario suite in the transcript")
    args = parser.parse_args()

    if args.tamper:
        tamper_demo()
        return
    if args.scenarios:
        run_scenarios()
        return
    if args.entity:
        entity_drill(args.entity)
        return
    if args.queue is not None:
        table_queue(_load_world()["review_queue"], limit=args.queue)
        return

    print("=" * 74)
    print(" SENTRA — SUPERVISORY ANALYTICS TOOL FOR SOC ASSESSMENT")
    print(" JUDGE MODE / PHASE 15 READINESS DEMO (offline, deterministic)")
    print("=" * 74)

    if not args.no_scenarios:
        run_scenarios()

    summary = _load_world()
    table_queue(summary["review_queue"], limit=20)
    entity_drill("CSE-011")
    tamper_demo()
    offline_attestation()

    print("\n" + "=" * 74)
    print(" Demo context: docs/PS_REQUIREMENT_SCORECARD.md (readiness verdict),")
    print(" docs/JUDGE_QA_MATRIX.md (known defects), docs/PS_COMPLIANCE_MATRIX.md,")
    print(" docs/MANUAL_REVIEW_VALIDATION.md, docs/PERFORMANCE.md.")
    print("=" * 74)


if __name__ == "__main__":
    main()