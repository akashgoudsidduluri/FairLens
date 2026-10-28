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
Model 6 adds deterministic per-applicant Gaussian noise seeded from the noise
seed and the applicant payload; it is independent across twins, not re-drawn per
request, so a retried request returns the same score. Model 7 is income-only.
Never imported by the auditor.

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
Single Streamlit page with two tabs, **Audit** and **Certificates**.

- Header: model picker, sandbox URL, **Start Audit**, **Demo mode** (Models
  2 → 7 → 5).
- Audit tab: pipeline strip, live agent log, findings board, intersectional
  heatmap (table fallback), impact panel, mitigation slider in `@st.fragment`,
  number-checked narrative, approver name + Approve/Reject.
- Certificates tab: chain view, **Verify chain**, labelled tamper demo behind an
  explicit confirmation, reset-demo-database.
- The completed `AuditReport` and all notices live in `st.session_state` so a
  rerun (slider, button, tab switch) does not lose the report.
- Buttons use `on_click` callbacks; Approve/Reject/Verify/Tamper never rely on
  the return value of the button call itself.
- Empty, loading, and error states are explicit; an unreachable sandbox shows an
  error card, not a traceback.
- No audit and no certificate are distinct states: the certificate tab shows
  `NOT CHECKED / 0 records`, never a vacuous `CHAIN VERIFIED`.

## `ui/components.py`
Pure renderers that return HTML strings and never touch Streamlit state:

- `pipeline_strip(stages)` — plan/probe/test/challenge/translate/sign.
- `log_feed(events)` — newest first, colour-coded by `AgentEvent.kind`; Skeptic
  rejections are red.
- `finding_card(finding, verdict)` — evidence, CI, checks, `REJECTED` stamp.
- `impact_counter(estimate)` — per-10,000 value with a JS count-up.
- `chain_view(records, broken_index)` — genesis, hashes, first broken row.
- `verify_badge(state)` — `CHAIN VERIFIED`, `CHAIN BROKEN`, or `NOT CHECKED`.

## `ui/plotting.py`
One Plotly template (transparent background, accent `#5EEAD4`, Inter, no
modebar through `PLOTLY_CONFIG`). `heatmap_figure` uses a fixed 0–100 pp colour
context so cells are comparable across models. `mitigation_figure` puts fairness
gap and accuracy change on **one** percentage-point axis; a dual axis would make
the two series look falsely comparable.

## `ui/style.css` and `.streamlit/config.toml`
Dark theme, one accent colour, Inter for UI and JetBrains Mono for logs/hashes.
CSS is injected once per run. It hides Streamlit chrome, defines the card system,
and provides the pulse, stamp-slam, and glow animations. Button label colour is
forced through nested Streamlit nodes so primary text stays legible.

## `eval/run_eval.py`
Runs 7 models × 5 seeds, writes `eval/results/results.csv`,
`materiality_sensitivity.csv`, `mitigation_curves.csv`, chart PNGs, and
`eval/results/summary.md`, including false alarms before/after Skeptic, misses,
runtime, mitigation, certificate test, number-check pass rate, and materiality
sensitivity (1% / 3%). Does not alter config.yaml.

## `eval/fairlearn_baseline.py`
Demographic parity difference and equalized odds difference on the same
observational sample; writes `eval/results/fairlearn.md` and `.csv`.

## `eval/charts.py`
Pillow chart helpers (grouped bar, simple bar, line). Matplotlib's native
`ft2font` DLL is blocked on the build machine, so evaluation artifacts do not
depend on it.

## `eval/sandbox_runner.py`
`start_servers(count)` / `stop_servers(processes)`: launches real
`sandbox.serve` processes on free ports for evaluation and waits for `/health`.

## `eval/demo_smoke.py`
Headless end-to-end check: real sandbox, Models 2/7/5, 60-second budget per
audit, certificate/tamper flow, graceful failure on an unreachable API. Writes
`eval/results/phase5_demo_smoke.md`.

## `schemas.py` addition (v2)
`ProbeEvent`: one counterfactual twin pair observed during probing.
Fields: `probe_id`, `phase` (`single_attribute` | `intersectional` |
`matched_retest`), `pair_index`, `changed_field`, applicant summaries
`original`/`twin`, both `*_approved` decisions, running `b_running`/`c_running`/
`n_running`, `net_flip_rate_running`, `ci_low_running`/`ci_high_running`,
`ci_method` (default `normal_approximation`), `timestamp`. The running interval
is the normal approximation in `auditor.statistician.running_net_flip_ci`; the
final `Evidence` CI remains the seeded bootstrap.

## `auditor/statistician.py` addition (v2)
`running_net_flip_ci(b, c, n, level) -> (low, high)`: normal-approximation CI
for the running paired net flip rate. `Var(X) = (b+c)/n - ((b-c)/n)^2`,
`SE = sqrt(Var(X)/n)`, interval `net ± z*SE`, clipped to `[-1, 1]`. Cheap enough
to compute per pair; not used for final findings.

## `auditor/prober.py` (v2)
`Prober(..., pair_event_sink=None)`. When a sink is supplied, each probe emits
one `ProbeEvent` per pair and delivers them in batches of
`api.probe_event_batch_size`. `probe_attribute`, `probe_intersectional`, and
`probe_matched` all emit; running counts restart at each probe. Defaults are
unchanged when the sink is `None`.

## `auditor/pipeline.py` (v2)
`run_audit(..., probe_event_sink=None)` forwards the sink to `Prober`. Existing
call signatures and audit output are unchanged when the sink is omitted.

## `api/` (v2)
- `api.app.create_app(*, config=None, store=None, audit_fn=run_audit) -> FastAPI`.
  Dependency injection keeps route tests fast and avoids real sandbox runs.
- `api.storage.AuditStore` protocol + `SQLiteAuditStore`; `create_store(config)`
  is the Postgres swap point. Tables: `audits`, `audit_events`.
- `api.jobs.AuditJobManager`: `ThreadPoolExecutor`, persists agent/probe events,
  completes or fails the audit record.
- `api.schemas`: request/response and `StreamEvent` contracts.
- `api.generate_types.render_types(openapi) -> str`; `python -m api.generate_types`
  writes `web/src/api-types.ts`.
- `python -m api.serve` runs the service on `service.host:service.port` (8020),
  overridable with `FAIRLENS_SERVICE_HOST` / `FAIRLENS_SERVICE_PORT`.

Endpoints:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service, version}` |
| POST | `/audits` | Validate, persist `queued`, submit background job, return `202` with `id`, `events_url`, `result_url` |
| GET | `/audits/{id}` | Status/record; includes `result`, `event_count`, `last_seq`, `decision` |
| GET | `/audits/{id}/events` | SSE: `agent`, `probe`, `done`; `id:` is the monotonic sequence; `data:` is `{seq, kind, data}` |
| POST | `/audits/{id}/decision` | Named approver + approve/reject; `409` unless completed and undecided; issues certificate |
| GET | `/certificates` | `{records, count}` |
| POST | `/certificates/verify` | `{verified, first_broken, records}` |
| POST | `/certificates/tamper-demo` | Requires `confirm: true`; corrupts one record and returns before/after + verification |

## `web/src/api-types.ts` (v2)
Generated from `app.openapi()`. Contains `AgentEvent`, `ProbeEvent`,
`StreamEvent`, all request/response models, and `AuditReport`. Regenerate with
`python -m api.generate_types`; `tests/test_v2_types.py` fails if stale.

## `targets/` (v2 R2)
Black-box target adapters. No module imports `sandbox.models` or `sandbox.api`.

- `targets.base.TargetAdapter`: abstract contract with `name`, `probe_cap`,
  `probes_used`, `reset()`, `health()`, and `score_batch(applicants) ->
  list[ModelResponse]`. `TargetError` is the base failure; `ProbeCapExceeded`
  is raised before any request that would exceed the hard cap.
- `targets.http.HTTPTargetAdapter`: declarative YAML adapter.
  - `base_url` supports `${VAR}` / `${VAR:-default}`.
  - `auth.type` is `none`, `header`, `bearer`, or `query`; `token_env` names the
    environment variable, never a literal secret.
  - `request.applicant_map` maps canonical fields; `request.body` expands
    `${applicants}` to the mapped list; `request.query`/`headers` are templates.
  - `response.items` is a dotted path (`$`, `$.results`, `results`);
    `response.approved`/`score` are dotted paths per item. `approved_true` lists
    truthy values; `approval_threshold` derives approval from the score if set.
  - `limits`: `probe_cap` (hard, 0 disables), `rate_limit_per_second`
    (monotonic spacing), `max_retries` (5xx/transport only), `backoff_seconds`
    (exponential), `timeout_seconds`.
- `targets.sandbox.load_sandbox_target(model_id, ...)`: loads
  `targets/sandbox/model-N.yaml`; `targets.sandbox._sandbox.yaml` holds the
  shared request/response mapping. The seven files are the validation suite.
- `targets.build_target(reference, config, ...)`: resolves `sandbox:N` or a
  repository-relative YAML path. Paths outside the repository are rejected.
- `config.yaml` adds `targets.probe_cap` and `targets.sandbox_dir`.

## Sequential stopping (v2 R2)
`auditor.statistician.sequential_stopping_decision(b, c, n, materiality,
min_pairs, max_pairs, level)` returns a dict with `action`, `n`,
`net_flip_rate`, `ci_low`, `ci_high`, `materiality`, and `reason`. Actions:
`continue`, `stop_material_harm`, `stop_no_material_harm`, `max_pairs`.

`config.yaml` pre-registers:

```yaml
audit:
  sequential:
    enabled: false
    min_pairs: 1000
    check_every: 200
```

`Prober(..., sequential=...)` overrides the config flag per audit.
`probe_attribute` scores in `check_every` chunks, continues the running
`ProbeEvent` stream across chunks, and returns a `ProbeResult` with
`requested_n`, `stopped_early`, and `stop_reason`. The pipeline emits an extra
`statistician` event on a stop. `run_audit(..., target=..., sequential=...)`
forwards both. Intersectional probes remain fixed-sample; final `Evidence` always
uses the observed pairs.

## Real-data targets (R3a)
The seven sandbox models remain the validation suite. R3a adds two targets whose
behaviour nobody planted, trained on public UCI data.

- `targets/real/datasets.py`: downloads `uci_credit_default` (UCI 350) and
  `adult_income` (UCI 2) from `archive.ics.uci.edu`, caches archives under
  `data/real/raw/` (git-ignored), and writes canonical CSVs under `data/real/`
  (committed). `DatasetUnavailable` names the exact URL, archive path, and
  extraction layout when offline; it never synthesises rows. `dataset_summary`
  records rows, licence, citation, DOI, URL, cache path, and sha256.
- `targets/real/features.py`: one mapping from `Applicant` to dataset columns,
  used by both serving and feasibility. Numeric fields use a monotone empirical
  quantile transform into the training distribution recorded in
  `metrics.json`; columns without a canonical source are documented training
  constants. `validate_row` checks training ranges and vocabularies.
  `validate_pair` also requires a gender twin to change exactly `sex` (names are
  not model inputs). `probe_capabilities` returns supported and unsupported
  probes with reasons.
- `targets/real/train.py`: seed 42, stratified 80/20 holdout. Logistic regression
  for credit default; histogram gradient boosting for Adult. The protected
  attribute `sex` is a natural feature in both (D-019). Saves joblib artifacts
  plus `<model>.metrics.json` with holdout accuracy/AUC/approval rate, Fairlearn
  demographic-parity and equalized-odds differences on the same holdout, ranges,
  quantile grids, categories, and dataset metadata. Approval rule fixed before
  auditing: `P(favourable) >= 0.5`, score `P*1000`.
- `targets/real/models.py`: artifact loading, `score_applicants`, and
  `RealModelUnavailable` / `InfeasibleApplicant`.
- `targets/real/serve.py`: FastAPI service, default `127.0.0.1:8030`,
  `GET /health`, `GET /models`, `POST /score_batch?model=...`. Same
  `[{approved, score}]` shape as the sandbox.
- `targets/real/adapter.py`: `RealTargetAdapter(HTTPTargetAdapter)` with
  dataset-aware `validate_pair`, `supports_mitigation = False`.
- `targets/real/*.yaml`: `family: real` adapters for both models, resolved by
  `targets.build_target` (`_adapter_class` dispatches on `family`). The generic
  YAML path is unchanged.

### Capability-aware probing
`TargetAdapter` gains `supported_probes` (defaults to all four),
`unsupported_details`, `supports_mitigation`, and `validate_pair`. The pipeline
builds the audit plan from `supported_probes`, emits one `planner` event per
skipped probe with the target's stated reason, restricts observations and
findings to supported attributes, records `supported_probes`/`skipped_probes` in
`report.observational`, skips the intersectional scan when undefined, and skips
mitigation when the target does not support it. `Prober._build_pairs` drops
infeasible pairs and emits a `prober` event with counts and reasons; the
denominator is the number of feasible pairs, and `ProbeResult.requested_n`
keeps the pre-filter request.

### Dataset mapping and unsupported fields
- `uci_credit_default`: `income -> LIMIT_BAL`, `gender -> SEX`,
  `age -> AGE`, `credit_score -> EDUCATION` and the payment-delay columns,
  `loan_amount -> BILL_AMT1..6`, `income/12 -> PAY_AMT1..6`. `MARRIAGE` is a
  constant. `employment_years`, pincode, name, and urban/rural are unused.
- `adult_income`: `age`, `gender -> sex`, `credit_score ->
  education/education_num`, `employment_years -> hours_per_week`. Race,
  workclass, marital status, occupation, relationship, native country,
  capital gain/loss, and `fnlwgt` are documented training constants. `income`
  and `loan_amount` are unused.
- Both datasets lack a name and a pincode/region column, so `pincode_group`,
  `name_group`, and the intersectional scan are declared unsupported. They are
  skipped and reported, never faked. Race exists in Adult but not in the
  canonical contract: it is held at the training mode when serving and measured
  only by the Fairlearn holdout baseline.
- Full source, licence, citation, and mapping: `targets/real/README.md`.

## Real-target evaluation (R3b)
`eval/run_real_eval.py` (`.venv\Scripts\python -m eval.run_real_eval`) starts
`targets.real.serve` on a free port, then audits both models on the seeds in
`config.yaml` (1-5) using the frozen v1 thresholds and `include_mitigation=False`.
It writes:

- `eval/results/real_models.csv`: one row per model × seed with runtime, probes
  used, supported/skipped probes, kept/rejected/immaterial counts, maximum
  candidate impact per 10,000, holdout accuracy/AUC, Fairlearn sex/age/race DP
  and EO, and the full finding details with reasons.
- `eval/results/real_models.md`: protocol, headline table, per-seed table,
  every candidate finding with b/c/net/CI/Holm p/status/reason, a plain
  statement of what could and could not be tested, and limitations.

Impact is `max(net_flip_rate, 0) * 10,000` for every candidate; only kept
findings are audit conclusions. The result statement distinguishes a true null
from an inconclusive null: if no pair is discordant (`b = c = 0`), the report
says the probe had no power rather than claiming the model is fair.

`expected_findings.md` contains the pre-registration committed before the
evaluation: "No expected finding. Report whatever is found, including no material
bias." for both models. No threshold, feature, mapping, or model was changed
after the results were seen.

Observed result (seeds 1-5): the Adult model produced a significant but
immaterial gender effect, net flip +0.0050 to +0.0120, in every seed; the credit
model produced zero discordant pairs in 10,000 twins, so its result is an
inconclusive null. Neither model produced a kept finding.
