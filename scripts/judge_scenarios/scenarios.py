"""Scenario oracle model and registry for the SENTRA judge-suite.

Each scenario encodes a realistic supervisory situation plus the *expected*
observable signal if the tool is doing its job. Expectations are written as
detector-level assertions (rule/detector + optional entity). The oracle is
evaluated against a freshly produced world (see ``run_scenario.py``), so the
disposition is reproducible offline.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from _runner import (
    finding_count,
    finding_present,
    queue_urgency,
    risk_band,
)


@dataclass
class Expectation:
    """One oracle assertion about a rendered world."""

    kind: str  # "finding_present" | "finding_absent" | "queue_urgency_at_least" | "risk_band"
    phase: str  # phase5..phase8 for findings; phase9 for queue/risk
    rule: str = ""
    entity: str | None = None
    min_count: int = 1
    min_urgency: int = 0
    band: str = ""


@dataclass
class Scenario:
    number: int
    name: str
    story: str
    expectations: list[Expectation] = field(default_factory=list)


def evaluate(scenario: Scenario, summary: dict[str, object]) -> list[tuple[Expectation, bool, str]]:
    """Evaluate a scenario's oracle against a world summary.

    Returns (expectation, passed, detail) records for the disposition table.
    """
    results: list[tuple[Expectation, bool, str]] = []
    for exp in scenario.expectations:
        if exp.kind == "finding_present":
            n = finding_count(summary, exp.phase, exp.rule)
            entity_note = f"entity={exp.entity}" if exp.entity else "any entity"
            ok = n >= exp.min_count and (not exp.entity or finding_present(summary, exp.phase, exp.rule, exp.entity))
            detail = f"{exp.rule} present ({n} findings; {entity_note})" if ok else (
                f"{exp.rule} expected on {entity_note}; found {n} finding(s)"
            )
        elif exp.kind == "finding_absent":
            n = finding_count(summary, exp.phase, exp.rule)
            ok = n == 0
            detail = f"{exp.rule} correctly deferred/absent ({n} findings)" if ok else (
                f"{exp.rule} should be absent but produced {n} finding(s)"
            )
        elif exp.kind == "queue_urgency_at_least":
            u = queue_urgency(summary, exp.entity or "")
            ok = u is not None and u >= exp.min_urgency
            detail = f"queue urgency({exp.entity})={u} >= {exp.min_urgency}" if ok else (
                f"queue urgency({exp.entity})={u} < {exp.min_urgency}"
            )
        elif exp.kind == "risk_band":
            b = risk_band(summary, exp.entity or "")
            ok = b == exp.band
            detail = f"risk_band({exp.entity})={b} == {exp.band}" if ok else (
                f"risk_band({exp.entity})={b} expected {exp.band}"
            )
        else:
            ok, detail = False, f"unknown expectation kind {exp.kind}"
        results.append((exp, ok, detail))
    return results


def load_scenarios() -> list[Scenario]:
    """Import every scenario_0X.py in this directory and gather its Scenario."""
    here = Path(__file__).parent
    scenarios: list[Scenario] = []
    for module_path in sorted(here.glob("scenario_*.py")):
        if module_path.stem == "scenarios":
            continue
        module = importlib.import_module(module_path.stem)
        scenarios.append(module.SCENARIO)
    return sorted(scenarios, key=lambda s: s.number)