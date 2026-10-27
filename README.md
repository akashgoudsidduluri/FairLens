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

## Evaluation

```powershell
.\.venv\Scripts\python -m eval.run_eval
.\.venv\Scripts\python -m eval.fairlearn_baseline --n 4000
.\.venv\Scripts\python -m eval.demo_smoke
```

`eval.run_eval` runs 7 models × 5 seeds on the pre-registered 2% materiality
threshold, then the same 70 audits at 1% and 3% with in-memory config copies. It
writes `eval/results/results.csv`, `materiality_sensitivity.csv`,
`mitigation_curves.csv`, five PNG charts, and `summary.md`. The
Fairlearn baseline uses the generator's hidden repayment label, which the
black-box auditor does not observe; it is an offline comparison, not part of the
audit. `eval.demo_smoke` is the headless end-to-end check with a real sandbox.

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
| `web/src/api-types.ts` | TypeScript types generated from the OpenAPI schema |
| `eval/` | Full evaluation, Fairlearn baseline, charts, headless demo smoke |
| `tests/` | pytest suite, including black-box boundary and v2 API/SSE tests |

## Honest limitations

- Synthetic data and a deliberately simple scoring formula. Results do not
  generalise to a real lender.
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
