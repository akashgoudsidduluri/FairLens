# CLAUDE.md — FairLens India working rules

## What this is
An agentic fairness auditor for a black-box lending model. It probes a sandbox
HTTP API with counterfactual twin applicants, challenges its own findings,
translates them into human impact, and issues a tamper-evident certificate that
a human must approve. Hackathon prototype; synthetic data only.

## Hard rules
1. **Black box.** `auditor/`, `impact/`, `trust/`, `report/`, and `ui/` must not
   import `sandbox.models` or `sandbox.api`. Allowed sandbox imports:
   `sandbox.generator` (data generation and lookup tables) and `schemas.py`.
   Check with `pytest tests/test_blackbox_boundary.py`.
2. **No invented formulas.** Every statistical function documents its formula
   and has a test cross-checked against scipy/statsmodels.
3. **Seeds and thresholds.** All randomness takes an explicit seed. Every
   threshold and planted penalty lives in `config.yaml`. Never hardcode a
   threshold and never tune after an audit result.
4. **Synthetic only.** No real people, names, or pincodes. Names are invented;
   pincodes are synthetic labels.
5. **LLM never computes.** The reporter passes computed JSON to the LLM and
   number-checks the output. It may only rewrite numbers that already exist.
6. **Honesty.** Keep misses and false alarms in results. A significant but
   immaterial effect is not called bias. Rejected candidates stay in the report.
7. **Human gate.** `trust.certificate.issue()` refuses empty approver names and
   requires an explicit approve/reject decision.

## Layout
`sandbox/` generates data and serves seven secret models. `auditor/` probes,
computes paired evidence, and applies rule-based skepticism. `impact/` computes
per-10,000 impact and offset mitigation curves. `trust/` owns the SQLite hash
chain. `report/` owns the LLM narrative and number check. `ui/app.py` is the
single Streamlit page. `eval/` reproduces the evaluation. `tests/` holds the
test suite.

## Commands
```
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m uvicorn sandbox.api:app --port 8000
.venv\Scripts\streamlit run ui/app.py
```

## Current phase state
See `expected_findings.md` (frozen) and `DECISIONS.md` (append-only).
