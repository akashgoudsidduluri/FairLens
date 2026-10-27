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

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

The suite covers the frozen contracts, generator and seven models, twin
construction, exact McNemar/bootstrap/Holm statistics, Skeptic rules, mitigation,
impact arithmetic, certificate chain and tamper detection, number checking, the
reporter fallback, Streamlit flows (audit, approve/reject, demo, tamper),
black-box import boundaries, launchers, and the shared Plotly theme.

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
| `eval/` | Full evaluation, Fairlearn baseline, charts, headless demo smoke |
| `tests/` | pytest suite, including black-box boundary checks |

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
