# SPEC.md — module contracts

All paths are relative to the repository root. Shared data contracts are in
`schemas.py`. Config is loaded by `config_loader.py`.

## `schemas.py`
Pydantic v2 contracts: `Applicant`, `ModelResponse`, `TwinPair`, `Evidence`,
`Finding`, `Check`, `SkepticVerdict`, `AgentEvent`, `ImpactEstimate`,
`AuditReport`, `CertificatePayload`, `Certificate`. Utilities:
`canonical_json`, `sha256_canonical`, `to_jsonable`, `utc_now_iso`.

## `sandbox/generator.py`
- `generate_applicants(n: int, seed: int) -> tuple[list[Applicant], list[bool]]`
  Returns applicants and hidden `true_repay` labels. Uses lognormal income with
  deliberate group differences, credit 300–900, age 21–65, 12 synthetic
  pincodes, and synthetic name pools keyed by (name_group, gender).
- `make_twin(applicant, attribute, target_value=None, rng=None) -> Applicant`
  Changes exactly one signal: `gender`, `pincode_group`, or `name_group`.
- `PINCODE_TABLE`, `NAME_POOLS`, `NAME_TO_GROUP`, `PINCODE_TO_GROUP`.
- `income_band(income, config) -> int` quintile helper.

## `sandbox/models.py`
Private. Seven scoring functions with documented base formula and planted
penalties from config. `score_applicant(model_id, applicant, config) -> ModelResponse`.
Model 6 adds per-request seeded noise. Model 7 is income-only. Never imported by
the auditor.

## `sandbox/api.py`
FastAPI app. `GET /health`; `POST /score?model=N`; `POST /score_batch?model=N`.
No endpoint reveals which model is biased.

## `auditor/prober.py`
`Prober(api_url, config)` with async `score_many`, `probe_attribute`,
`probe_intersectional`, `matched_retest`, `observational_sample`. Builds valid
twins, batches requests, retries with timeouts, and emits `AgentEvent`s.

## `auditor/statistician.py`
- `mcnemar_exact(b, c) -> float` exact two-sided binomial test.
- `paired_net_flip(b, c, n, seed) -> Evidence` point estimate + bootstrap CI.
- `holm_adjust(pvalues) -> list[float]`.
- `wilson_interval(k, n)`, `newcombe_gap_ci(...)`.
- `observational_rates(applicants, responses) -> dict`.
- `single_attribute_finding(...)`, `intersectional_findings(...)`.
Formulas are in docstrings.

## `auditor/skeptic.py`
`review(finding, config, matched_evidence=None, min_pairs=...) -> SkepticVerdict`.
Rule checks: minimum sample, Holm significance, materiality, directional
consistency/symmetric noise, income-matched persistence, confounding
(observational gap with no counterfactual effect). Rules only; no LLM.

## `auditor/pipeline.py`
`run_audit(model_id, api_url, config, seed=42) -> Generator[AgentEvent, None, AuditReport]`
Yields agent events and returns the report (findings, impact, mitigation,
narrative). Deterministic given seed.

## `impact/impact.py`
`impact_per_10k(finding) -> ImpactEstimate`. Formula:
`max(net_flip_rate, 0) × 10,000`; CI bounds converted identically.

## `impact/mitigate.py`
`build_curve(model_id, api_url, attribute, target_group, config, seed) -> list[dict]`
Sweeps score offsets for the target group, recomputes approval with the same
threshold, and records `(offset, fairness_gap, accuracy, accuracy_loss)`.
`recommend(curve, max_accuracy_loss) -> dict` picks the smallest gap subject to
the loss budget, breaking ties toward the smaller offset.

## `trust/certificate.py`
`init_db(path)`, `issue(payload, approver, decision, db_path)`,
`verify(db_path) -> tuple[bool, int | None]`, `list_records(db_path)`,
`tamper_for_demo(index, db_path) -> dict`. Hash chain:
`record_hash = sha256(prev_hash + canonical_json(payload))`.

## `report/reporter.py`
`build_payload(report, events) -> dict`; `generate_narrative(payload, config) -> dict`
(Anthropic call with template fallback); `template_narrative(payload) -> str`.

## `report/number_check.py`
`allowed_numbers(payload) -> set[str]`; `extract_numbers(text) -> list[str]`;
`check_numbers(text, payload) -> dict` with `passed`, `unknown`, `checked`.

## `ui/app.py`
Single Streamlit page: sidebar API/model/audit; live agent log; findings table;
subgroup heatmap with table fallback; impact panel; mitigation slider; report
with number-check badge; approver approve/reject; certificate verify/tamper tab.

## `eval/run_eval.py`
Runs 7 models × 5 seeds, writes `eval/results/results.csv` and
`eval/results/summary.md`, including false alarms before/after Skeptic, misses,
runtime, mitigation, certificate test, number-check pass rate, and materiality
sensitivity (1% / 3%). Does not alter config.yaml.

## `eval/fairlearn_baseline.py`
Demographic parity difference and equalized odds difference on the same
observational sample; writes `eval/results/fairlearn.md`.
