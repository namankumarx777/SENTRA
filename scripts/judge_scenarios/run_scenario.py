"""Run the SENTRA judge scenario suite.

Usage:
  run_scenario.py --list
  run_scenario.py --scenario 1                 # build one world, run one scenario
  run_scenario.py --all                        # build one world, run all 8 scenarios
  run_scenario.py --determinism                # two identical runs -> byte-identical findings
  run_scenario.py --no-clean                   # keep the working root (temporary by default)

Every run is fully self-contained (synthetic corpus + Phases 4-9 in the
working root; the shipped ``data/processed`` corpus is never touched).
Exit code is 0 only when every executed oracle expectation passes.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from collections import Counter
from pathlib import Path

import polars as pl

from _runner import (
    DEFAULT_ALERTS,
    DEFAULT_ENTITIES,
    DEFAULT_SEED,
    PHASE_DIRS,
    build_world,
    clean,
    load_world,
)
from scenarios import evaluate, load_scenarios


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _phase_findings_digests(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for phase, dirname in PHASE_DIRS.items():
        findings = root / dirname / "findings.parquet"
        evidence = root / dirname / "evidence.parquet"
        digests[f"{phase}_findings"] = _file_digest(findings) if findings.is_file() else "MISSING"
        digests[f"{phase}_evidence"] = _file_digest(evidence) if evidence.is_file() else "MISSING"
    return digests


def check_determinism(work_root: Path, alerts: int, entities: int, seed: int) -> bool:
    first = work_root / "run-a"
    second = work_root / "run-b"
    print("-- determinism check: two identical Phase 4-9 runs --")
    build_world(first, entities=entities, alerts=alerts, seed=seed, dataset_id="determinism-a")
    build_world(second, entities=entities, alerts=alerts, seed=seed, dataset_id="determinism-b")
    a = _phase_findings_digests(first)
    b = _phase_findings_digests(second)
    ok = True
    for key in sorted(a):
        match = "MATCH" if a[key] == b[key] else "DIFFER"
        ok = ok and a[key] == b[key]
        print(f"  {key:22s} {match:6s} {a[key][:16]}...")
    if ok:
        print("RESULT: findings/evidence byte-identical across deterministically identical runs")
    else:
        print("RESULT: MISMATCH - determinism broken")
    return ok


def _print_band_summary(queue) -> str:
    if queue is None or queue.height == 0 or "priority" not in queue.columns:
        return "rows=0"
    counts = Counter(str(x) for x in queue["priority"].to_list())
    return f"rows={queue.height} by_priority={dict(sorted(counts.items()))}"


def run_all(work_root: Path, alerts: int, entities: int, seed: int, only: int | None = None) -> bool:
    scenarios = load_scenarios()
    if only is not None:
        chosen = [s for s in scenarios if s.number == only]
        if not chosen:
            print(f"no scenario numbered {only}")
            return False
        scenarios_to_run = [chosen[0]]
    else:
        scenarios_to_run = scenarios

    print(f"-- world: {entities} entities / {alerts} alerts / seed {seed} into {work_root} --")
    build_world(work_root, entities=entities, alerts=alerts, seed=seed, dataset_id=f"judge-{entities}e-{alerts}a")
    summary = load_world(work_root)

    findings = summary["findings"] or {}
    for phase in sorted(findings):
        df = findings[phase]
        if df is None or df.height == 0:
            print(f"  {phase:8s} findings=0")
            continue
        counts = Counter(str(x) for x in df["rule_id"].to_list())
        print(f"  {phase:8s} findings={df.height} evidence={len(summary['evidence'].get(phase, pl.DataFrame())) or 0}  {dict(sorted(counts.items()))}")
    print(f"  phase9   review_queue {_print_band_summary(summary['review_queue'])}")

    print("\n-- oracle disposition --")
    passed_all = True
    for scenario in scenarios_to_run:
        results = evaluate(scenario, summary)
        failures = [r for r in results if not r[1]]
        status = "PASS" if not failures else "FAIL"
        passed_all = passed_all and not failures
        print(f"\nS{scenario.number:02d} [{status}] {scenario.name}")
        for _, ok, detail in results:
            print(f"    {'ok' if ok else 'XX'}  {detail}")
        if failures:
            print(f"    reason: {'; '.join(r[2] for r in failures)}")
    print("\n" + ("ALL SCENARIOS PASS" if passed_all else "SOME SCENARIOS FAIL"))
    return passed_all


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SENTRA judge scenario runner (offline, self-contained).")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    parser.add_argument("--all", action="store_true", help="run the full scenario suite on one fresh world")
    parser.add_argument("--scenario", type=int, help="run a single scenario by number")
    parser.add_argument("--determinism", action="store_true", help="run determinism double-run check instead")
    parser.add_argument("--entities", type=int, default=DEFAULT_ENTITIES)
    parser.add_argument("--alerts", type=int, default=DEFAULT_ALERTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--root", type=Path, default=None, help="working root (default: temp dir)")
    parser.add_argument("--no-clean", action="store_true", help="keep the working root on disk")
    return parser.parse_args()


def _main() -> None:
    args = _parse_args()

    if args.list:
        for s in load_scenarios():
            print(f"S{s.number:02d}  {s.name}")
        return

    work_root = args.root or (Path(tempfile.gettempdir()) / "sentra-judge")
    ok = True
    try:
        if args.determinism:
            ok = check_determinism(work_root, args.alerts, args.entities, args.seed)
        elif args.all:
            ok = run_all(work_root, args.alerts, args.entities, args.seed)
        elif args.scenario is not None:
            ok = run_all(work_root, args.alerts, args.entities, args.seed, only=args.scenario)
        else:
            print("specify --list, --all, --scenario N, or --determinism"); raise SystemExit(2)
    finally:
        if not args.no_clean and args.root is None and work_root.exists():
            clean(work_root)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    _main()