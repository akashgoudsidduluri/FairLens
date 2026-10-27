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
