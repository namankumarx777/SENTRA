# Manual Review Validation — SAT-SA / SENTRA

This document defines how SENTRA is validated against the outcomes of expert manual review, per PS §8 ("Participants shall explain how the proposed solution will be validated against findings derived from expert manual review… effectiveness comparable to or better than current manual sampling approaches") and PS §9 (success criterion).

The premise of the tool is that manual reviews of sampled alert and case records surface weaknesses not visible through conventional reporting. Validation must therefore compare what SENTRA flags against what a trained human examiner would flag, at a scale where manual review is the reference but cannot be exhaustive.

## 1. Validation objective

Demonstrate that the supervisory *signals* SENTRA produces (rules, execution gaps, negative space, peer deviations, anomalies, risk dimensions, review queue) agree with expert manual review of the same operational evidence, and that SENTRA extends coverage to the full population rather than a sample.

Success is framed as *agreement with expert judgement on items an expert could be expected to judge deterministically*, not as "the tool matches human intuition perfectly" — human intuition includes subjective heuristics that the tool deliberately does not model as probability.

## 2. The reference standard problem

The PS requires comparison to expert manual review, but yields several well-known difficulties that the validation design must address explicitly:

1. **Expert verdicts are not a pristine ground truth.** Manual review is itself variable between examiners and across time. The validation protocol therefore treats the *converging expert set* (two or more reviewers agreeing, post-independent review) as the reference, not any single reviewer.
2. **Sample bias.** Manual review only examines a sample; SENTRA examines the whole population. Disagreement on items the human never saw is not measurable — so the comparison is performed *on the reviewed sample* for agreement metrics, and *on the whole population* for coverage demonstrations.
3. **Ground-truth contamination.** Any synthetic controls used to fabricate "known" weaknesses must not leak into analytical outputs as labels (`CONTEXT.md`). Validation corpora must keep the instrumentation layer (which knows the injected weaknesses) separate from the output layer (which must not).

## 3. Validation layers

Validation is conducted at four complementary layers.

### Layer 1 — Deterministic rule/adjudication validation (contract tests)

Each detector is validated against hand-verified fixtures that encode the intended semantics:

- **Positive fixtures:** a case where the condition is unambiguously present must produce the finding with the correct `rule_id`, `entity_id`, `metric_name`, `observed`/`expected`/`gap`/`baseline` values and linked evidence rows.
- **Negative fixtures:** a case where the condition is *absent* must produce no finding (fastidiousness — no "empty-hurts" heuristics).
- **Boundary fixtures:** threshold edges (e.g. exactly at `RAPID_CLOSURE_MINUTES`, coverage exactly 0.90, population exactly minimum) are pinned to documented behaviour.
- **Determinism fixture:** re-running the phase on the same input yields byte-identical findings/evidence (SHA-256 equal), so a subsequent supervisory review of the same submission is reproducible.

**Where it already lives in the repo:** `tests/` — e.g. `test_execution_gap_engine.py`, `test_negative_space_engine.py`, `test_peer_anomaly_engine.py`, `test_rules_engine.py`, `test_supervisory_risk*.py`, `test_phase_store.py`. These are the machine-checkable backbone; they validate logic against explicit expectations rather than against human opinion.

### Layer 2 — Scenario / judge validation

A fixed set of controlled scenarios, each encoding a realistic supervisory situation with an expected outcome ("judge oracle"), is run against the tool. The oracle expectation is written by a human examiner *before* seeing the tool's output (to avoid moving the goalposts). Disposition = tool outcome matches the oracle expectation.

- Scenario corpus & harness: `scripts/judge_scenarios/` (`scenario_01`…`scenario_08`, `run_scenario.py`) and `scripts/judge_mode.py` (interactive oral/judge demonstration driver).
- Each scenario records: injected situation, expected supervisory signal(s), the phase(s) involved, and the expected review-queue/risk effect.
- Acceptance: all scenarios in the live judge demonstration must land where the oracle predicts (or the discrepancy must be explained as an intentional boundary stated in the tool).

### Layer 3 — Differential blind review (the human "manual review" comparison)

This is the protocol that maps most directly onto PS §8 and §9.

**Design (two-arm):**
- Take a real or synthetic corpus large enough to make exhaustive manual review impossible, but small enough that a *sample* can be reviewed by experts within the exercise window (default recommendation: 12 CSEs, 500 alerts — the shipped corpus; scale variants in `docs/PERFORMANCE.md`).
- Randomly select a manual-review sample (default 10% of alerts/cases). Two independent examiners review the sample using the SENTRA domain taxonomy (threat detection, investigation, escalation, incident response, security operations, governance and oversight, operational discipline, cyber resilience).
- Blind requirement: examiners are given origin data only (metadata/case records), **never** SENTRA outputs or finding IDs.
- Independently, SENTRA is run end-to-end over the **entire** corpus (not just the sample).
- Final reference set for each sample item: whether the converging examiners judged it as surface an operational weakness (positive) or not (negative).

**Agreement metrics (reported on the sample):**

| Metric | Definition | Interpretation |
|---|---|---|
| Weakness-level recall | SENTRA flags ≥1 finding/evidence touching the same entity+category+time-window for each converging-expert positive | Supervisory findings SENTRA would have surfaced |
| False-signal rate | SENTRA flags not corroborated by any examiner (entity+category window unrelated to any expert concern) | Noise the reviewer must not chase |
| Sample-vs-population uplift | Count of converging-expert-quality signals SENTRA produces over the whole population vs only over the sample | Demonstrated scalability benefit (§9) |
| Reviewer agreement (Cohen's/SIC) | Convergence of the two examiners as a check on the reference standard's reliability | Reference-standard integrity |

**Acceptance bar:** weakness-level recall ≥ expert coverage achieved by the sample itself (SENTRA must be "no worse than the sample that would have been manually reviewed"), while keeping false-signal rate low enough that review-queue HIGH urgency items remain substantive.

### Layer 4 — Substitution / continuity check (assurance preservation)

PS §9 requires "preserve the quality of supervisory assurance currently obtained through expert human examination". Because quality preservation cannot be measured in days, we use a **substitution surrogate**:

- Take a corpus where the review-queue ordering (risk, urgency) has been manually adjudicated by experts on the sample.
- Verify that SENTRA's ranking of *sample* entities is consistent (rank correlation) with the experts' ranking — the continuity claim is that if the tool had been used, the same entities would have risen to the top of the supervisor's queue.
- Report the correlation along with the caveat that rank consistency on-sample does not prove end-to-end assurance equivalence; it is the strongest measurable proxy available offline.

## 4. Instrumentation requirements (ground-truth hygiene)

- The synthetic generator (`backend/app/data/generate_synthetic.py`) is controlled by `ground_truth` parameters. These are used **only** by validation tooling (`scripts/judge_scenarios/`, test fixtures) and must not appear as feature/rule/finding labels (`CONTEXT.md` rule). The audit verified no such label columns exist in findings parquet (`test_*_engine.py` assert the absence of `{"negative_space", "is_negative_space", "risk_score", "ground_truth"}` columns in specific outputs).
- Injection ledger for scenario runs: each judge scenario stores its injected weaknesses in a sidecar metadata file (outside `data/processed` analytical output), so the judge can check "did the tool see the planted problem?" without the planting being part of the analytical schema.

## 5. Offline-only constraint effect on validation

Because the deployment is air-gapped (PS §5), validation must be executable entirely offline:

- All expert-review artifacts, scenario corpora, generated data, and tooling run locally — no external annotation platform, no cloud gold-standard service.
- Validation is repeatable: determinism guarantees a re-run on identical input reproduces identical findings, so a judge can re-run the demonstration and confirm nothing changed between preparation and evaluation (see determinism fixtures).

## 6. Known limitations of the validation (honest boundaries)

1. **No completed expert study in this audit.** The protocol, harness, and corpora exist; a live human-examiner differential study requires NCIIPC's own reviewers and is outside what a code audit can execute. `docs/PS_COMPLIANCE_MATRIX.md` records this explicitly rather than claiming a finished validation.
2. **Corpus realism.** Deterministic synthetic data is internally consistent and controllable but cannot reproduce the full messiness of real SOC records; agreement metrics measured on it are *calibrating*, not *final proof*.
3. **Rank correlation ≠ decision-making.** Layer 4 demonstrates ranking continuity, not that supervisors, presented with SENTRA output, will reach the same enforcement judgment (judgment remains human; `CONTEXT.md` boundaries).
4. **Held-out spellout.** Any "surprise" detector emergent behaviour (e.g. NS003 cohort categories) is validated by manual adjudication of its findings before it can be used as a supervisory signal in the demo.

## 7. Execution checklist (for the judge's demo)

1. `pytest -q tests` — green suite (115 test cases at audit time), confirming contract/determinism backbone.
2. Run `scripts/judge_mode.py` (or per-scenario `run_scenario.py`) to rebuild a scenario corpus, execute the phases, and print the oracle-vs-outcome disposition table.
3. Demonstrate the review queue (21 items, 9 HIGH at audit time) and drill into CSE-011 high-urgency items to row-level evidence.
4. Demonstrate blockchain register → verify → simulated tamper → MISMATCH offline (local permissioned ledger; live Fabric chaincode optional — see `docs/OPERATIONS.md` for its `UNVERIFIED` status at this audit).
5. Present Layer 3 & 4 protocol and current results in the oral.

*Cross-references: `docs/PS_COMPLIANCE_MATRIX.md` §8/§9; `scripts/judge_scenarios/`; `scripts/judge_mode.py`; `docs/JUDGE_QA_MATRIX.md`.*