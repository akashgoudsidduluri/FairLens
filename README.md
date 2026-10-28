# FairLens India

Agentic black-box fairness auditor for a synthetic lending model. Built for the
OpenQuest Innovation Challenge, Domain 6 (Responsible AI, Privacy, Trust &
Accessibility).

FairLens probes a model it cannot read: it sends paired counterfactual
applicants over HTTP, tests the resulting decisions, challenges its own
findings, translates them into human impact, and asks a named person to approve
or reject a tamper-evident record. Every number in the narrative is checked
against the computed JSON. The LLM writes prose; it never calculates.

> Synthetic sandbox only. Findings are evidence of disparate treatment, not
> proof of intent, and the certificate chain proves tamper-evidence, not
> authorship.

## Demo in three minutes

1. Start the app (below) and open <http://127.0.0.1:8501>.
2. Keep **Model 2** and press **Start Audit**. The pipeline, live log, kept and
   rejected findings, intersectional heatmap, impact counter, mitigation slider,
   and number-checked narrative fill in.
3. Enter an approver name and press **Approve & issue certificate**.
4. Open the **Certificates** tab. Press **Verify chain**. Tick the confirmation
   and press **Demo: tamper with the newest record**, then **Verify chain** again:
   the first broken record is highlighted in red.
5. Switch back to **Audit**, choose **Model 7**, and run it: observational gaps
   appear but every candidate is rejected because gender/pincode/name twins do
   not change an income-only model's decision.
6. Choose **Model 5**: the single-gender finding is small (and kept at 0.0265 in
   the seed-42 audit, a known pre-registration miss), while the intersectional
   hotspot is large. The **Demo mode** button runs Models 2 → 7 → 5 in one go.

## Setup

Requires Python 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS/Linux use `python3 -m venv .venv` and `source .venv/bin/activate`.
An Anthropic API key is optional: without one, the reporter uses a deterministic
template that passes the same number check. Copy `.env.example` to `.env` to add
a key. Never commit `.env`.

## Run

One command (starts the sandbox on port 8010, waits for `/health`, then starts
Streamlit on port 8501, and cleans up on exit):

```powershell
.\run.ps1
```

```bash
./run.sh
```

If a port is busy:

```powershell
$env:FAIRLENS_API_PORT=8020; $env:FAIRLENS_UI_PORT=8502; .\run.ps1
```

Manual start, two terminals:

```powershell
.\.venv\Scripts\python -m sandbox.serve --host 127.0.0.1 --port 8010
.\.venv\Scripts\python -m streamlit run ui/app.py --server.port 8501
```

The sandbox exposes only `GET /health`, `POST /score`, and `POST /score_batch`.
It never reveals which model has a planted penalty. The auditor imports only
`schemas.py` and `sandbox.generator`; a static test enforces the boundary.

## Audit service (v2)

The v2 service runs audits as background jobs over HTTP, streams live progress
as Server-Sent Events, persists every audit and event in SQLite behind a
swappable store interface, and gates certificate issuance behind a named human
decision.

```powershell
# terminal 1: the black-box sandbox
.\.venv\Scripts\python -m sandbox.serve --host 127.0.0.1 --port 8010

# terminal 2: the audit service (defaults to 127.0.0.1:8020)
.\.venv\Scripts\python -m api.serve
```

Then, in a third terminal:

```powershell
# start an audit
$body = '{"model_id": 2, "include_mitigation": false, "include_narrative": false}'
$audit = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8020/audits `
  -ContentType 'application/json' -Body $body

# stream agent + per-pair probe events (SSE)
curl.exe -N "http://127.0.0.1:8020/audits/$($audit.id)/events"

# fetch the report, then sign off and issue a certificate
Invoke-RestMethod "http://127.0.0.1:8020/audits/$($audit.id)"
$decision = '{"approver": "Asha Auditor", "decision": "approve"}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8020/audits/$($audit.id)/decision" `
  -ContentType 'application/json' -Body $decision

Invoke-RestMethod http://127.0.0.1:8020/certificates
Invoke-RestMethod -Method Post http://127.0.0.1:8020/certificates/verify
```

Operational settings live under `service:` in `config.yaml` (host, port,
`audit_db`, `max_workers`, `sse_poll_seconds`). Override the listener with
`FAIRLENS_SERVICE_HOST` / `FAIRLENS_SERVICE_PORT`. `POST /audits` returns `202`
with `id`, `events_url`, and `result_url`; SSE frames use the event names
`agent`, `probe`, and `done`, with `data:` shaped as `{seq, kind, data}` and an
`id:` equal to the monotonic sequence.

Regenerate the TypeScript client types after changing `api/schemas.py`:

```powershell
.\.venv\Scripts\python -m api.generate_types
```

This writes `web/src/api-types.ts`; `tests/test_v2_types.py` fails if the file is
stale.

### Target adapters (v2)

The seven sandbox models ship as YAML validation adapters. Select one with
`target: "sandbox:N"`; the request's `api_url` (or `FAIRLENS_API_URL`) overrides
the YAML base URL:

```powershell
$body = '{"model_id": 2, "target": "sandbox:2", "include_mitigation": false, "include_narrative": false}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8020/audits `
  -ContentType 'application/json' -Body $body
```

A custom target is a repository-relative YAML file. The adapter maps canonical
applicant fields into the target request and maps the reply back to
`(approved, score)`:

```yaml
name: my-lender
base_url: "${LENDER_URL:-https://example.test}"
auth:
  type: header            # none | header | bearer | query
  header_name: X-API-Key
  token_env: LENDER_API_KEY
request:
  method: POST
  path: /v1/decisions
  query: {product: personal_loan}
  headers: {Accept: application/json}
  applicant_map:
    annual_income: "${applicant.income}"
    credit: "${applicant.credit_score}"
    applicant_ref: "${applicant.id}"
  body:
    applicants: "${applicants}"
response:
  items: "$.decisions"
  approved: "result"
  approved_true: ["APPROVE", true]
  score: "score"
limits:
  probe_cap: 100000       # hard per-audit cap; 0 disables it
  rate_limit_per_second: 20
  max_retries: 3
  backoff_seconds: 0.25
  timeout_seconds: 20
```

Secrets are read from environment variables named in YAML; they are never stored
in the audit record. Adapters reject paths outside the repository and count
applicants (not retries) against the cap. The shared sandbox mapping lives in
`targets/sandbox/_sandbox.yaml`; `model-1.yaml` through `model-7.yaml` only
change the `model` query parameter. `tests/test_v2_targets.py` validates all
seven adapters against the real sandbox app over ASGI.

### Sequential stopping (v2)

Sequential stopping is pre-registered in `config.yaml` and disabled by default so
v1 fixed-sample runs stay reproducible. Enable it globally or per request:

```powershell
$body = '{"model_id": 2, "sequential": true, "include_mitigation": false, "include_narrative": false}'
```

The rule (documented in `auditor/statistician.py` and D-018): before
`min_pairs` continue; at `max_pairs` stop; otherwise stop once the running
normal-approximation CI for the net flip rate is entirely above `materiality`
(material harm) or entirely below it (no material harm). Final findings still use
the exact McNemar p-value and seeded bootstrap CI on the pairs actually observed.
The intersectional scan stays fixed-sample. `tests/test_v2_sequential.py`
compares a sequential run with a fixed-sample run on the same fake scorer.

### Real-data targets (R3a)

Two targets trained on public UCI datasets, with no planted behaviour. The seven
sandbox models remain the validation suite; real-target results are reported in a
separate table.

| Target | Data | Model | Holdout accuracy | Holdout AUC |
|---|---|---|---|---|
| `uci_credit_default` | UCI Default of Credit Card Clients (30,000 rows, CC BY 4.0) | logistic regression | 0.8083 | 0.7079 |
| `adult_income` | UCI Adult (32,561 rows, CC BY 4.0) | histogram gradient boosting | 0.8756 | 0.9300 |

```powershell
# train (downloads and caches UCI data; artifacts are committed)
.\.venv\Scripts\python -m targets.real.train

# serve both models (default 127.0.0.1:8030)
.\.venv\Scripts\python -m targets.real.serve

# audit through the YAML adapter
$body = '{"model_id": 2, "target": "targets/real/adult-income.yaml", "include_mitigation": false}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8020/audits `
  -ContentType 'application/json' -Body $body
```

The protected attribute `sex` is a natural model feature in both models (D-019).
Neither dataset has a name or pincode/region column, so `name_group`,
`pincode_group`, and the intersectional scan are declared unsupported: the
pipeline skips them, emits one event per skipped probe with the reason, and
records the skips in the report. Twins are checked against the training feature
ranges and a gender twin must change exactly `sex`. Fairlearn demographic-parity
and equalized-odds differences on the same holdout are stored in
`data/real/artifacts/*.metrics.json` for comparison only.

The model is real; the probe population is the synthetic FairLens generator
mapped into the dataset's columns, not the dataset's own population. Full
licences, citations, column mapping, and limitations: `targets/real/README.md`.

### LLM screener target (R3c)

`target: "llm:screener"` routes the audit to an Anthropic model instead of a
model we wrote. The prompt asks the model to screen one applicant and to reply
with exactly `{"approved": <bool>, "score": <0-1000>}`. Anything else is a
parse failure; failures are counted, never replaced with a default.

```powershell
# set both in this shell only; nothing is written to disk
$env:ANTHROPIC_API_KEY = "..."
$env:ANTHROPIC_MODEL = "..."

# exploratory, capped audit (24 pairs per probe, 300 calls, USD 1.00)
.\.venv\Scripts\python -m eval.run_llm_eval
```

Only names and regions change between twins: `name_group` N1 -> N2 and
`pincode_group` P1 -> P2. Every other prompt line is byte-identical and the
adapter verifies that before scoring. The name and region pools in
`targets/llm/names.py` are documented approximations and are not a statement
about anyone's religion, caste, language, or community.

Design choices: temperature 0, 3 repeats per applicant, majority outcome per
pair, run-to-run variance reported as a separate metric, unparseable replies
counted, and a disk cache keyed by prompt hash so reruns cost nothing. Hard caps
of 300 calls and USD 1.00 per audit are checked before each call. With no key
the target reports `unavailable` and no audit runs; that is a reported outcome,
not a hidden failure. Full detail: `targets/llm/README.md`.

300 calls is 24 pairs per probe, far below the frozen `min_pairs = 1000`, so an
LLM result is exploratory and underpowered by construction. It cannot be a kept
finding. This is fixed in `expected_findings.md` before the run.

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

The suite covers the frozen contracts, generator and seven models, twin
construction, exact McNemar/bootstrap/Holm statistics, Skeptic rules, mitigation,
impact arithmetic, certificate chain and tamper detection, number checking, the
reporter fallback, Streamlit flows (audit, approve/reject, demo, tamper),
black-box import boundaries, launchers, the shared Plotly theme, and the v2
audit API, SSE stream, generated types, target adapters, and sequential stopping.
The R3c tests cover strict JSON parsing, prompt-twin diffing, majority and tie
handling, the disk cache, repeat variance, call and cost caps, the unavailable
state, and the `llm:screener` dispatch, all with an injected fake client.

## Evaluation

```powershell
.\.venv\Scripts\python -m eval.run_eval
.\.venv\Scripts\python -m eval.fairlearn_baseline --n 4000
.\.venv\Scripts\python -m eval.run_real_eval
.\.venv\Scripts\python -m eval.run_llm_eval
.\.venv\Scripts\python -m eval.demo_smoke
```

`eval.run_eval` runs 7 models × 5 seeds on the pre-registered 2% materiality
threshold, then the same 70 audits at 1% and 3% with in-memory config copies. It
writes `eval/results/results.csv`, `materiality_sensitivity.csv`,
`mitigation_curves.csv`, five PNG charts, and `summary.md`. The
Fairlearn baseline uses the generator's hidden repayment label, which the
black-box auditor does not observe; it is an offline comparison, not part of the
audit. `eval.demo_smoke` is the headless end-to-end check with a real sandbox.

`eval.run_real_eval` audits the two R3a real-data targets on seeds 1-5 with the
same frozen thresholds and no mitigation. It writes
`eval/results/real_models.csv` and `real_models.md`, including rejected findings
with reasons, immaterial findings, impact per 10,000, Fairlearn holdout numbers,
accuracy, runtime, and the probes that could not be tested. The outcome was
pre-registered in `expected_findings.md` as "No expected finding."

`eval.run_llm_eval` runs the R3c LLM screener with the operational caps in
`config.yaml` (300 calls, USD 1.00, 24 pairs per probe, 3 repeats) and writes
`eval/results/llm_screener.csv`, `llm_screener.md`, and an LLM section in
`real_models.md`. Every row is labelled exploratory and underpowered because 24
pairs cannot meet the frozen 1,000-pair minimum. If `ANTHROPIC_API_KEY` or
`ANTHROPIC_MODEL` is missing, it writes the unavailable outcome and runs no
audit.

See [report.md](report.md) for results and every miss, [demo_script.md](demo_script.md)
for the walkthrough, and [slides_outline.md](slides_outline.md) for a five-minute
talk. Pre-registration is frozen in [config.yaml](config.yaml) and
[expected_findings.md](expected_findings.md); implementation decisions, including
the Model 5 miss, are in [DECISIONS.md](DECISIONS.md).

## How the audit works

1. **Plan** — fixed scope, seed, thresholds, and pair counts from `config.yaml`.
2. **Probe** — 2,000 natural twin pairs per single attribute, 500 per
   intersectional cell, plus 4,000 observational applicants. A twin changes one
   signal (gender, pincode group, name group) and holds everything else fixed.
3. **Test** — exact two-sided McNemar test (`scipy.stats.binomtest`), seeded
   percentile bootstrap CI, Holm correction within each family.
4. **Skeptic** — rule-based checks for sample size, significance, materiality,
   direction, income-matched persistence, and confounding. No LLM.
5. **Impact** — `max(net flip rate, 0) × 10,000` people per 10,000, with the same
   conversion applied to the CI. No hidden multiplier.
6. **Mitigate** — group-wise score offsets with the same approval threshold;
   fairness gap and accuracy versus the hidden repayment label; recommendation
   subject to the user's accuracy-loss budget.
7. **Report** — computed JSON → LLM prose, then number checking against the JSON;
   deterministic template fallback.
8. **Sign-off** — a named human approves or rejects; a hash chain stores the
   decision. Verification recomputes the whole chain and reports the first broken
   record.

## Project layout

| Path | Purpose |
|---|---|
| `sandbox/` | Synthetic applicants, seven black-box models, HTTP API |
| `auditor/` | Prober, paired statistics, Skeptic, pipeline |
| `impact/` | Per-10,000 impact and mitigation curves |
| `report/` | Number checker, LLM reporter, template fallback |
| `trust/` | Certificate payload, SQLite hash chain, verification, tamper demo |
| `ui/` | Streamlit app, pure HTML components, Plotly theme, CSS |
| `api/` | v2 FastAPI audit service, SQLite store, SSE stream, TS type generation |
| `targets/` | v2 YAML target adapters, sandbox validation adapters, probe caps |
| `targets/real/` | R3a models trained on public UCI data, mapping, serving, adapters |
| `targets/llm/` | R3c Anthropic screener, prompt, pools, cache, caps, variance |
| `data/real/` | Cached canonical CSVs and trained artifacts (raw archives ignored) |
| `data/llm_cache/` | Prompt-hash-keyed LLM responses (git-ignored) |
| `web/src/api-types.ts` | TypeScript types generated from the OpenAPI schema |
| `eval/` | Full evaluation, Fairlearn baseline, charts, headless demo smoke |
| `tests/` | pytest suite, including black-box boundary and v2 API/SSE tests |

## Honest limitations

- Synthetic data and a deliberately simple scoring formula. Results do not
  generalise to a real lender.
- The R3a real-data models are trained on public data, but the probe population
  is still the synthetic generator mapped into the dataset's columns. Neither
  dataset has a name or region column, so two of the three frozen probes and the
  intersectional scan are unsupported and skipped; age and race are measured only
  by the Fairlearn holdout baseline.
- The R3c LLM target is capped at 300 calls, so it can run 24 pairs per probe
  against a 1,000-pair minimum. It is exploratory and cannot keep a finding. The
  name and region pools are approximations, and a language model is not a stable
  measurement instrument even at temperature 0; run-to-run variance is reported
  separately for that reason.
- Twins are approximations. Fairness metrics can conflict; a null result is not
  proof of fairness.
- Model 5's single-attribute gender finding was predicted to be immaterial but
  was kept at 0.0265 on seed 42. The prediction arithmetic was wrong; thresholds
  were not retuned. See D-009.
- The hash chain is tamper-evident, not authorship-proof. Anyone who can rewrite
  every row can recompute it. Digital signatures are future work.
- The mitigation curve uses the hidden repayment label to estimate accuracy, so
  it is an offline "what if" rather than a deployable policy.
- The LLM never calculates, but a passing number check only proves that numbers
  match the computed JSON, not that the prose is wise.
