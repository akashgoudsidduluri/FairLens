# FairLens India — decision log

Decisions are recorded here as they are made. Once an audit has run, audit
thresholds and planted penalties are frozen; later entries may document
implementation fixes but must not tune those values.

## D-001 (Phase 0) Python and dependencies
- Python 3.11 in a local `.venv`; FastAPI + Uvicorn for the sandbox, Streamlit
  for the dashboard, pytest for tests.
- The sandbox and auditor run as separate processes. The auditor talks to the
  sandbox only over HTTP and imports only `schemas.py` and the applicant
  generator.

## D-002 (Phase 0) Pre-registration
- `config.yaml` and `expected_findings.md` were committed before any audit.
- alpha = 0.05, Holm correction, materiality = 0.02 net flip rate, minimum 1,000
  pairs, minimum cell size 200, 2,000 natural pairs per single attribute,
  4,000 observational applicants, 500 pairs per intersectional cell.
- Seeds 1–5 are reserved for evaluation. The demo uses seed 42.

## D-003 (Phase 0) Paired statistics
- b = original approved, twin rejected; c = original rejected, twin approved.
- Net flip rate = (b − c) / n, oriented toward harm to the target group
  (original is from the comparison group, twin is from the target group).
- Exact two-sided McNemar test = two-sided binomial test of b successes in
  b + c trials at p = 0.5. The docstring states this and a test cross-checks it
  against `statsmodels.stats.contingency_tables.mcnemar`.
- 95% CI: **seeded percentile bootstrap** over the paired outcomes
  {harm, benefit, neither}, 4,000 resamples, seed derived from the finding id.
  Chosen because it needs no normal approximation and handles small discordant
  counts; a test checks it is close to the analytic Wald paired-difference CI
  for large samples.
- Holm adjustment is applied within each family: three single-attribute tests,
  then the 12 intersectional cell tests.
- Observational rate CIs use Wilson intervals; the gap CI uses the Newcombe
  hybrid score interval, cross-checked against `statsmodels`.

## D-004 (Phase 0) Target-group orientation
- For each single attribute, the target group is the group with the lowest
  observational approval rate; the comparison group is the highest. Twins flip
  from the comparison group to the target group. This makes positive net flip
  rate mean harm to the disadvantaged group.
- Any negative/contrary counterfactual effect is reported as-is; no flipping of
  signs after the fact.

## D-005 (Phase 0) Model 5 population design
- Female 50%, age 45+ 20%, rural 20%, independent; hotspot share ≈ 2.0%.
- Penalty 240 points in the hotspot. Expected cell net flip ≈ 0.6, so the
  diluted single-attribute gender net flip ≈ 0.02 × 0.6 = 0.012, below the
  0.02 materiality threshold. The intersectional scanner samples 500 pairs per
  cell (12 cells) so the rare cell still has power. Full arithmetic is in
  `expected_findings.md`.
- The pincode table has 12 synthetic pincodes: P1 and P2 each have 3 urban and
  1 rural; P3 has 4 urban. Weighted rural share = 0.5×0.25 + 0.3×0.25 + 0.2×0
  = 0.20.

## D-006 (Phase 0) Model 7 confounding
- Model 7's score is a monotone function of income only. A twin that changes
  gender, pincode, or name while income is fixed therefore gets the identical
  decision, so b = c = 0. Observational gaps arise because the generator gives
  P2, N2, and women lower mean income on purpose.

## D-007 (Phase 0) Honesty rules
- The LLM never computes numbers; it rewrites computed JSON. Number checking
  runs on every narrative and a deterministic template is the fallback.
- Rejected candidates remain in the report. No threshold, penalty, or model is
  changed after seeing audit output.

## D-008 (Phase 1) Demo port 8010
- Port 8000 was already occupied by an unrelated local service on the build
  machine, so the sandbox and dashboard defaults use 8010. This is an
  operational choice, not an audit parameter. `run.sh`, `run.ps1`, the UI
  default, and `config.yaml` agree.

## D-009 (Phase 2) Model 5 expectation miss — reported, not retuned
- First audit (seed 42) found the Model 5 hotspot at net flip 0.632 (kept), as
  expected. It also kept the single-attribute gender finding at net 0.0265,
  above the 0.02 materiality threshold, whereas `expected_findings.md` predicted
  ~0.012 and "immaterial".
- Cause: the pre-registration arithmetic multiplied the hotspot's 2% share of
  the whole population by the 50% female share, but the single-attribute probe
  samples male originals only. Among male-origin pairs, 4% are in the hotspot,
  so the expected diluted rate is 0.04 × 0.63 ≈ 0.025, not 0.012. The
  prediction was wrong, not the threshold.
- No threshold, penalty, population mix, or model was changed after seeing this.
  The miss is carried into Phase 6 and the final checklist. The hotspot remains
  the dominant finding (0.632 vs 0.0265).

## D-010 (Phase 3) Mitigation curve
- Group-wise offset is added to the returned score only for the affected
  segment; the configured approval threshold is re-applied. Fairness gap is the
  absolute difference between segment and comparison approval rates, so
  over-correction is visible (the gap rises again past the optimum).
- Accuracy is agreement with the generator's hidden true_repay on the mitigation
  sample. Recommended point = smallest gap among offsets with accuracy loss
  within the user's budget; ties go to the smaller offset.
- Rare intersectional segments use a stratified sample (1,000 segment + up to
  2,000 natural comparison applicants) so the slider is measurable. The curve
  records that sampling mode.

## D-011 (Phase 3) Certificate trust boundary
- Hash rule is exactly `sha256(prev_hash + canonical_json(payload))`, with a
  64-zero genesis hash. Verification also checks index order, prev-hash links,
  payload hashes, and that the duplicated `created_at` column matches the
  payload timestamp.
- A hash chain detects modification and reordering, not authorship: an attacker
  who can rewrite every row can recompute the chain. Signing (e.g. Ed25519) is
  future work. The UI states this limitation next to the verify result.

## D-012 (Phase 4) Narrative verification and UI sign-off
- The reporter receives computed JSON only; the payload excludes model
  coefficients and planted penalties. Every narrative number is normalised and
  checked against that JSON. A failed LLM draft is retried once, then replaced
  by a deterministic template that passes the same check.
- Streamlit sign-off requires a non-empty approver name. The certificate tab
  shows chain verification and a clearly labelled tamper demo. Notices are
  stored in session state across the rerun so the tamper result is visible.
- The sandbox process is launched through `sandbox.serve`; the auditor package
  never contains the scoring API's import path.

## D-013 (Phase 5) Demo path and headless smoke test
- The dashboard starts on Model 2 and names the demo path Model 2 -> Model 7 ->
  Model 5: a clear gender penalty, a confounded model that must be rejected,
  then the intersectional hotspot.
- `run.sh` and `run.ps1` start the sandbox entry point, wait for `/health`, and
  clean up both processes on exit. Ports can be overridden with
  `FAIRLENS_API_PORT` / `FAIRLENS_UI_PORT`.
- `eval/demo_smoke.py` is the headless end-to-end check. It uses a real sandbox
  process and HTTP, asserts each audit is under 60 seconds, verifies the
  certificate/tamper flow, and verifies graceful failure on an unreachable API.
  The total three-model walkthrough was 58.3s in the first recorded headless run;
  individual audits were 23.3s, 15.0s, and 20.0s. Later runs measured 67.9s
  (27.7s, 17.5s, 22.6s) and 75.6s (30.2s, 24.2s, 21.1s). Every run keeps every
  audit under the 60s budget. The reported numbers are measurements, not targets.
- SQLite connections are explicitly closed after use, because Windows keeps a
  lock on the certificate file until the connection is closed.

## D-014 (Phase 5b) Dashboard presentation rules
- Streamlit is pinned to 1.66.1 so the custom CSS and component behaviour are
  reproducible. `ui/style.css` is injected once; components are pure HTML
  renderers with no Streamlit calls, so they are testable without a browser.
- The live log renders newest first. Streamlit re-renders the placeholder on
  every event, which resets an auto-scrolled container to the top; newest-first
  keeps the latest line visible without JavaScript scroll hacks.
- The mitigation chart puts the fairness gap and the accuracy change on a single
  percentage-point axis. A second y-axis makes the two series look comparable
  while hiding different scales, so the second axis was removed.
- The heatmap uses a fixed 0–100 pp colour context rather than per-model
  normalisation; per-model scaling would make a 5 pp cell look as red as a 60 pp
  cell. Empty cells render `—`, and the age labels get explicit left margin.
- After approval the report stays in `st.session_state`; the slider reruns a
  fragment, not the audit. A certificate tab with no records shows
  `NOT CHECKED / 0 records` instead of a vacuous `CHAIN VERIFIED`.
- Layout was checked at 1366×768 and 1920×1080 with a headless Chrome CDP
  capture; `document.documentElement.scrollWidth` equals the viewport width at
  both sizes. Only hidden Plotly SVG artifacts sit outside the viewport.

## D-015 (Phase 6) Evaluation and reporting rules
- The main run is 7 models × seeds 1–5 at the frozen 2% materiality. The
  sensitivity run repeats the 70 audits at 1% and 3% using in-memory copies of the
  config; `config.yaml` is never edited by the harness.
- Mitigation is fixed at seed 42. The first harness version looked for a seed-42
  row in the main results, which only contains seeds 1–5, so every model was
  silently skipped. The harness now runs its own seed-42 audit per model before
  sweeping offsets. This is a reporting bug fix, not a threshold change.
- Only the five intersectional cells with the largest net flip are carried into
  the findings board; all 12 cells are tested and Holm-corrected. This is a
  readability cap, not a filter on significance, and it is listed as a limitation
  because Model 2 has six affected female cells and reports five.
- Runtimes in `results.csv` are measured inside three parallel workers. Three
  Model 7 seeds recorded 665–672 s while sharing the sandbox with other audits and
  returned identical results to the 29–32 s seeds. The outliers stay in the
  artifact with `runtime_under_60 = False`; the serial demo is the latency
  benchmark.
- Evaluation charts use Pillow (`eval/charts.py`) because Matplotlib's native
  font DLL is blocked on the build machine.

## D-016 (Phase 7 fixes) Post-freeze correctness and honesty fixes
- Model 6 uses deterministic **per-applicant** noise: `sha256(noise_seed |
  applicant.id | applicant JSON)` seeds one Gaussian draw. Twins therefore get
  independent draws, and a retried request gets the same score. The frozen
  `expected_findings.md` says "independent per-request noise"; that file is a
  pre-registration artifact and is not edited. This entry records the
  implementation difference. It does not change Model 6's outcome: the audit
  still keeps 0 findings; `_noise` was never re-tuned.
- The certificate hash chain proves modification/reordering resistance, not
  authorship, and it cannot detect deletion of trailing records without an
  external anchor (a published head hash or append-only log). The UI and report
  state both limitations.
- `run.ps1` / `run.sh` export `FAIRLENS_API_URL` from the port they actually
  launched, and the dashboard reads it. Previously `FAIRLENS_API_PORT=9000`
  moved the sandbox but left the UI pointing at 8010.
- Certificates now embed `report.config`, the config the audit actually ran
  with, rather than the global config at signing time. A sensitivity run can no
  longer produce a certificate whose thresholds differ from its findings.
- `impact.mitigate.recommend` now returns `within_budget`. If no tested offset
  fits the budget (only reachable with a negative budget or a malformed curve),
  it shows the unaudited baseline and says so instead of claiming a
  budget-breaking offset is compliant.
- The dashboard keeps per-model events for the demo run, so "Open demo result"
  swaps the log and pipeline strip to the selected model. Before this, the
  report changed but the log still described Model 5.
- Template narrative trimming now drops only the per-finding detail sentences
  (`For ...`). It can no longer drop the rejected/immaterial disclosure or the
  limitations paragraph. The reported intersectional-cell count no longer has an
  `or 12` fallback that could contradict a measured value.

## D-017 (v2 R1) Audit service, streaming, and generated types
- `run_audit` is a synchronous generator that calls `asyncio.run` internally, so
  background jobs use a bounded `ThreadPoolExecutor` (`service.max_workers`)
  rather than adding a second async boundary. The HTTP layer stays async and
  hands blocking store calls to `asyncio.to_thread`.
- Persistence sits behind `api.storage.AuditStore`. `SQLiteAuditStore` is the
  reference implementation (WAL, 5 s busy timeout). Postgres is a documented
  extension point: implement the same methods and return it from `create_store`;
  no route or job imports SQLite directly.
- SSE readers poll the store instead of consuming an in-process queue. This is
  slightly more work per stream but is correct across worker threads and future
  multi-process deployments, and it lets a client reconnect with `Last-Event-ID`.
- `ProbeEvent` is a new lightweight contract, one per twin pair: applicant
  summaries, changed field, both decisions, and running b/c/n with a normal-
  approximation CI. The final report still uses the seeded percentile bootstrap;
  the running interval is explicitly labelled `normal_approximation` and exists
  only to keep the live stream informative.
- Probe events are delivered in batches of `api.probe_event_batch_size` (25) and
  written in one transaction per batch. This keeps the SSE stream smooth without
  opening a database round-trip per pair.
- SSE frames use `id:`, `event:`, and a JSON `data:` body shaped as
  `{seq, kind, data}`; terminal frames use `event: done`.
- `web/src/api-types.ts` is generated from `app.openapi()` by
  `python -m api.generate_types`. A test fails if the checked-in file is stale.
  The stream response advertises `StreamEvent` so `AgentEvent` and `ProbeEvent`
  appear in the component schemas.
- v1 audit semantics are unchanged: no thresholds, pair counts, penalties, or
  existing tests were modified. `service` and `probe_event_batch_size` are
  operational settings only.

## D-018 (v2 R2) Target adapters and pre-registered sequential stopping
- `targets/` is a black-box adapter layer. It imports `schemas.py`, `httpx`, and
  YAML only; it never imports `sandbox.models` or `sandbox.api`. The seven
  `targets/sandbox/model-N.yaml` files are validation adapters for the existing
  sandbox service, not shortcuts around HTTP.
- The YAML format separates concerns: `request.applicant_map` maps canonical
  `Applicant` fields, `request.body` is a template (`${applicants}` for a list),
  `response.items`/`approved`/`score` map the reply, and `limits` owns the probe
  cap, rate limit, retries/backoff, and timeout. `${VAR}` and `${VAR:-default}`
  read the environment; a missing variable is an error, never an empty string.
- Auth is `none`, `header`, `bearer`, or `query`, with the secret always read
  from an environment variable named in YAML. Secrets are never stored in the
  audit record or certificate.
- Every audit gets a fresh adapter instance. The hard probe cap is checked before
  any HTTP request and counts applicants, not retries. Exceeding the cap fails
  the audit; the job manager records the failure. This is deliberately not a
  warning.
- Adapter mode scores chunks sequentially so the rate limiter and cap see one
  request at a time. Direct-URL mode keeps the existing concurrent batching.
- Sequential stopping is pre-registered under `audit.sequential` and is **off by
  default**. Enabling it by default would change v1's fixed-sample counts and
  break the frozen evaluation, so it is opt-in per config or per API request.
- The rule: before `min_pairs`, continue; at `max_pairs`, stop; otherwise stop
  for material harm when the running normal-approximation CI's lower bound
  exceeds `materiality`, and stop for no material harm when the upper bound is
  below `materiality`. If the interval contains `materiality`, continue. The
  rule is applied to single-attribute probes only; the intersectional scan stays
  fixed-sample so its Holm family is unchanged.
- Sequential stopping is a stopping heuristic, not a new inference procedure.
  Final findings still use the exact McNemar p-value and seeded bootstrap CI on
  the pairs actually observed, and the report records `stopped_early` and
  `stop_reason` on the probe result. The normal approximation can be
  anti-conservative at low discordant counts; `min_pairs` is the safeguard.
- The audit record stores `sequential` and the target reference. Existing R1
  SQLite databases are migrated in place with an `ALTER TABLE ... ADD COLUMN`
  guarded by `PRAGMA table_info`.
- No frozen threshold, penalty, `expected_findings.md`, or v1 test was changed.

## D-019 (R3a) Real-data targets: natural models, documented mapping
- Two public datasets are used: UCI Default of Credit Card Clients (30,000 rows)
  and UCI Adult (32,561 rows). Both are CC BY 4.0; citations are in
  `targets/real/README.md` and in each `metrics.json`. The archives are cached
  under `data/real/raw/` (git-ignored) and canonical CSVs plus trained artifacts
  are committed so audits and tests are reproducible offline.
- The models are "natural": logistic regression for credit default and
  histogram gradient boosting for Adult, seed 42, stratified 80/20 holdout.
  **The protected attribute `sex` is an ordinary feature.** No fairness-aware
  preprocessing and no dropped-attribute variant was trained; the instruction was
  to default to what a practitioner would do, and this is that default. The
  Adult model also uses `race`.
- Approval rule is fixed before auditing: `P(favourable) >= 0.5`, score is
  `P*1000` on a 0-1000 scale. For credit default the favourable label is "no
  default"; for Adult it is income > 50K. The FairLens materiality threshold is
  unchanged at 0.02.
- Canonical-to-dataset mapping is deterministic and documented column by column
  in `targets/real/README.md`. Numeric fields use a monotone empirical-quantile
  transform into the training distribution; dataset columns with no canonical
  source are set to a documented training mode/median. This is feature mapping,
  not row synthesis: no applicant row is fabricated, and no substitute dataset is
  generated.
- `pincode_group`, `name_group`, and the intersectional scan are **unsupported**
  for both real targets because neither dataset has a pincode/region or name
  column, and the intersectional cells require urban/rural. The adapters declare
  this in YAML, the pipeline emits one skip event per probe with the reason, and
  the report records `supported_probes` and `skipped_probes`. The auditor does
  not invent values to keep a probe running.
- Twins are checked against the training domain before scoring. A gender twin
  must change exactly the mapped `sex` feature (the canonical name also changes,
  but names are not model inputs). Infeasible pairs are counted and reported in
  a `prober` event, never silently dropped.
- Race exists only in Adult and has no canonical field. It is held at the
  training mode when serving, so the twin audit cannot test race; the Fairlearn
  baseline measures race on the real holdout instead.
- Mitigation is disabled for real targets: an offset sweep needs the sandbox's
  score endpoint, and applying a made-up offset to a real model's probability is
  not a comparable intervention.
- The probe population is still the synthetic FairLens generator mapped onto the
  dataset columns. The model is real; the population is not the dataset's own
  population. Results are reported with that limitation.
- No threshold, planted penalty, frozen expectation, or v1 test was changed.

## D-020 (R3b) Real-target reporting: distinguish a null from no power
- The pre-registration in `expected_findings.md` was committed before the
  evaluation, in its own commit (`preregister real targets`), as "No expected
  finding. Report whatever is found, including no material bias."
- `eval.run_real_eval` runs seeds 1-5 with the unchanged v1 thresholds,
  correction, pair counts, and bootstrap settings. Mitigation is off because the
  real targets do not expose the sandbox offset endpoint.
- Impact per 10,000 is reported as `max(net_flip_rate, 0) * 10,000` for every
  candidate, not only kept findings, so an immaterial effect is still visible.
  Only a kept finding is an audit conclusion. This is a reporting convention
  fixed after the run and does not change any threshold or status.
- A result with `b = c = 0` is reported as an **inconclusive null**, not as "no
  material bias", because the probe had no discordant pairs with which to detect
  an effect. The credit model is in this state: 10,000 twins, zero decision
  changes, because no mapped score sits close enough to the 500 approval
  threshold for the roughly 20-point gender shift to cross it.
- The Adult model is the other case: a significant, consistently directional
  gender effect of +0.0050 to +0.0120 net flip, below the 0.02 materiality
  threshold, so every candidate is immaterial and no finding is kept. It is
  reported as "no material bias under the pre-registered threshold", not as
  fairness.
- No threshold, feature, mapping, model, or artifact was changed after seeing
  the results, and no probe was added to manufacture a finding.

## D-021 (R3c) LLM screener target: fixed protocol, caps, and the unavailable state
- The LLM target is a third kind of target, not a sandbox model and not a real
  dataset model. The prompt, the strict JSON contract, the name/region-only
  twins, the 24-pairs-per-probe plan, and the 300-call/USD 1.00 caps were
  written into `expected_findings.md` and committed alone (`preregister LLM
  screener`) before any call was made.
- Only names and regions vary, one direction each: `name_group` N1 -> N2 and
  `pincode_group` P1 -> P2. The pools are arbitrary and mixed on purpose. They
  are an approximation, not a claim about religion, caste, language, or
  community; the README and the report say so.
- Temperature 0, 3 repeats, majority outcome, median score. Ties and fewer than
  two parseable repeats are unresolved: counted, excluded from b/c, reported.
  Unparseable replies are never defaulted to a decision. Run-to-run variance is
  a separate metric because a language model is not a stable instrument.
- 300 calls is 24 pairs per probe; `min_pairs` is 1,000. The run is therefore
  exploratory and underpowered by construction and cannot keep a finding. This
  is stated before the run rather than discovered afterwards.
- Caps are hard limits checked before each call; cache hits are free. Cost is a
  conservative estimate for the cap, not a bill. A cache key includes model,
  prompt, temperature, and max tokens, so a config change cannot silently reuse
  a stale answer.
- No API key or model was available at run time. We did not fabricate a result:
  the target reports `unavailable`, the evaluation writes that outcome, and no
  name or region effect is claimed. The adapter is tested with an injected fake
  client; there is no mock in the product path.
- No frozen threshold, planted penalty, v1 expectation, real-data artifact, or
  existing test was changed.
