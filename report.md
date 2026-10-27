# FairLens India — final report

Agentic black-box fairness audit of a synthetic lending model, built for the
OpenQuest Innovation Challenge, Domain 6 (Responsible AI, Privacy, Trust &
Accessibility).

**Evidence in one line:** 35 pre-registered audits (7 models × 5 seeds) and 70
materiality-sensitivity audits ran against a real HTTP sandbox with zero errors;
the Skeptic kept the planted behaviours, rejected the confounded model, and kept
zero candidates on the two clean controls; one pre-registered expectation was
missed and is reported below rather than hidden.

> Everything here uses synthetic applicants and a deliberately simple scoring
> formula. It is evidence that the audit method works on a known target, not
> evidence about a real lender or real Indian populations.

---

## 1. The problem

A lender can refuse to share its model, its training data, and its labels. A
conventional fairness audit — Fairlearn, Aequitas, a bias metric computed on a
held-out set — needs at least one of those. An HTTP scoring endpoint gives an
auditor exactly one thing: a decision for an applicant.

That leaves two hard questions:

1. **Can we produce evidence of disparate treatment with only the endpoint?**
2. **Can we avoid mistaking a legitimate factor, such as income, for bias?**

FairLens answers both with counterfactual twins. Two applicants are identical
except for one signal. If the decision changes when only gender, pincode group,
or name group changes, the model is treating otherwise-identical people
differently. If it does not change, an observational gap is a question, not a
finding.

The system never claims to prove intent, and never claims that a null result
proves fairness.

---

## 2. Architecture

```
              ┌────────────────────┐
              │  Streamlit UI       │
              │  audit + sign-off   │
              └─────────┬──────────┘
                        │ Python calls
              ┌─────────▼──────────┐        HTTP /score, /score_batch
              │  auditor/          │ ───────────────────────────────┐
              │  plan → probe →    │                                │
              │  test → challenge  │        ┌───────────────────────▼──┐
              │  → impact          │        │  FastAPI sandbox          │
              └─────────┬──────────┘        │  sandbox.models is private │
                        │                   └───────────────────────────┘
        computed JSON only
              ┌─────────▼──────────┐        ┌───────────────────────────┐
              │  report/            │        │  trust/                   │
              │  LLM prose +        │        │  SQLite hash chain        │
              │  number checker     │        │  verify / tamper demo     │
              └────────────────────┘        └───────────────────────────┘
```

The **process boundary is the trust boundary**. The sandbox runs as a separate
FastAPI process. The auditor, impact, trust, report, and UI packages may import
`schemas.py` and `sandbox.generator` only; they may not import
`sandbox.models` or `sandbox.api`. A static test walks the imports and fails the
suite if that boundary is crossed. The sandbox has no endpoint that names the
biased model.

| Package | Responsibility |
|---|---|
| `sandbox/` | Synthetic applicants, seven scoring functions, HTTP API |
| `auditor/` | Prober, paired statistics, rule-based Skeptic, pipeline |
| `impact/` | Per-10,000 impact, mitigation curves, recommendations |
| `report/` | Computed payload, LLM prose, number checker, template fallback |
| `trust/` | Certificate payload, SQLite hash chain, verification, tamper demo |
| `ui/` | Streamlit dashboard, HTML components, Plotly theme, CSS |
| `eval/` | Full evaluation, Fairlearn baseline, charts, demo smoke test |

### Pipeline

1. **Plan** — read the frozen scope from `config.yaml`; emit the audit plan.
2. **Probe** — build twins and send them over HTTP; 2,000 natural pairs per
   single attribute, 500 stratified pairs per intersectional cell, 1,000 pairs
   in the income-matched re-test, and 4,000 observational applicants.
3. **Test** — exact McNemar, seeded percentile bootstrap CI, Holm correction
   within each family.
4. **Challenge** — six rule-based Skeptic checks per candidate.
5. **Translate** — impact per 10,000 and a fairness/accuracy trade-off curve.
6. **Report** — computed JSON → prose → number check → deterministic fallback.
7. **Sign** — a named human approves or rejects; the decision enters a hash
   chain.

Every stage emits an `AgentEvent`, which drives the live log in the dashboard.
Given a seed, the audit is deterministic.

---

## 3. Pre-registration

`config.yaml` and `expected_findings.md` were committed in Phase 0, before the
first model was probed. The values below were not changed after any result was
seen. The Model 5 miss is the proof: the prediction was wrong and the threshold
stayed.

| Parameter | Frozen value |
|---|---|
| Significance | α = 0.05, Holm within family |
| Materiality | net flip rate ≥ 0.02 |
| Single-attribute pairs | 2,000 per attribute |
| Minimum pairs | 1,000 |
| Intersectional cells | 12, 500 pairs each, minimum cell 200 |
| Observational sample | 4,000 applicants |
| Income-matched re-test | 1,000 pairs |
| Bootstrap | 4,000 seeded percentile resamples, 95% |
| Seeds | 1–5 evaluation, 42 demo |
| Approval threshold | 500 points |
| Demo order | Model 2 → Model 7 → Model 5 |

### Orientation

For each attribute the target group is the group with the **lowest**
observational approval rate and the comparison group is the **highest**. Twins
flip from comparison to target, so a positive net flip rate means harm to the
disadvantaged group. A negative effect is reported as-is; no sign flipping after
the fact.

### Statistics

- **Exact McNemar.** With `b` = comparison approved / target twin rejected and
  `c` = comparison rejected / target twin approved, the two-sided exact test is
  a binomial test of `b` successes in `b + c` trials at p = 0.5
  (`scipy.stats.binomtest`). A test cross-checks it against
  `statsmodels`' McNemar.
- **Net flip rate** = `(b − c) / n`.
- **CI.** Seeded percentile bootstrap over the paired outcomes
  {harm, benefit, neither}, 4,000 resamples, with the seed derived from the
  finding id. It needs no normal approximation and handles small discordant
  counts.
- **Multiplicity.** Holm within the three single-attribute tests, then within
  the 12 intersectional cells. Raw and adjusted p-values are both retained.
- **Observational rates.** Wilson intervals for each rate; Newcombe hybrid score
  interval for the gap, cross-checked against `statsmodels`.

### Skeptic rules

The Skeptic is rule-based; no LLM participates.

| Rule | Question |
|---|---|
| Sample | Are there enough pairs and a large enough cell? |
| Significance | Is the Holm-adjusted p-value below α? |
| Materiality | Is the net flip rate at least 2%? |
| Direction | Is the effect oriented toward the target group, and is the noise symmetric? |
| Persistence | Does the effect survive an income-matched re-test? |
| Confounding | Is there an observational gap with no counterfactual effect? |

A rejected candidate stays in the report with its reasons. The UI stamps it
`REJECTED`; it is not deleted.

---

## 4. The seven sandbox models

The scoring functions are private to the sandbox. The audit never reads them.

| Model | Planted behaviour | Pre-registered expectation |
|---|---|---|
| 1 | Clean control, base score only | No kept findings |
| 2 | −120 points if female | Gender kept; pincode and name not kept |
| 3 | −120 points for pincode group P2 | P2 kept; gender and name not kept |
| 4 | −120 points for name group N2 | N2 kept; gender and pincode not kept |
| 5 | −240 points only if female, 45+, and rural | Hotspot kept; single-attribute gender immaterial |
| 6 | Deterministic per-applicant noise (independent across twins) | No kept findings |
| 7 | Income-only score; generator gives P2/N2/women lower income | Observational candidates rejected as confounded; 0 kept |

Model 5's design uses a target cell that is about 2% of the population, so the
single-attribute gender effect is diluted. The pre-registration predicted a
diluted rate near 0.012. The actual dilution is larger because the
single-attribute probe samples male originals only, and 4% of those are in the
hotspot. That arithmetic error is the source of the known miss, documented in
`DECISIONS.md` D-009.

Model 7 is the counterexample to naive dashboards: it has real observational
gaps because the generator gives several groups lower income, but changing only
gender, pincode, or name with income fixed never changes its decision.

---

## 5. Impact, mitigation, narrative, and sign-off

### Impact

`impact_per_10k(finding)` = `max(net_flip_rate, 0) × 10,000`, with the CI bounds
converted identically. There is no hidden multiplier. The number answers one
question: if this net flip rate held for 10,000 people in the affected group,
how many extra adverse decisions would the model make?

### Mitigation

`build_curve` sweeps score offsets (0–240 points in steps of 20) for the primary
finding's segment, re-applies the same approval threshold, and records:

- the absolute gap between segment and comparison approval rates, so
  over-correction is visible (the gap rises again past the optimum);
- accuracy against the generator's hidden `true_repay` label;
- accuracy loss versus the unaudited model.

Rare intersectional segments use a stratified sample (1,000 segment applicants
plus up to 2,000 natural comparisons). `recommend(curve, budget)` picks the
smallest gap among offsets whose accuracy loss is inside the user's budget,
breaking ties toward the smaller offset.

The accuracy label is hidden in a real audit. This is an offline what-if, not a
deployable policy, and the UI and report say so.

### Narrative and number checking

The reporter receives computed JSON only — no model coefficients, no planted
penalties. The LLM rewrites that JSON into prose. Every numeric token in the
draft is normalised and checked against the allowed set from the payload. A
failed draft is retried once, then replaced by a deterministic template that
passes the same check.

The guarantee is narrow and honest: a passing number check proves the prose
matches the computed JSON. It does not prove the prose is wise.

### Certificate

`record_hash = sha256(prev_hash + canonical_json(payload))`, with a 64-zero
genesis hash. Verification recomputes the whole chain, checks index order,
`prev_hash` links, payload hashes, and the duplicated timestamp column, and
reports the **first broken record**. No certificate can be issued without a
non-empty approver name and an explicit approve/reject action.

The chain is **tamper-evident, not authorship-proof**. An attacker who can
rewrite every row can recompute the chain; digital signatures are future work.
The UI states this next to the verification result.

---

## 6. Evaluation protocol

The evaluation is a separate harness, not the demo:

```powershell
.\.venv\Scripts\python -m eval.run_eval            # 35 main + 70 sensitivity
.\.venv\Scripts\python -m eval.fairlearn_baseline --n 4000
.\.venv\Scripts\python -m eval.demo_smoke          # serial three-model demo
```

- **Main run:** 7 models × seeds 1–5, frozen 2% materiality, 2,000
  single-attribute pairs, 500 intersectional pairs per cell, 4,000
  observational applicants.
- **Sensitivity:** the same 70 audits at 1% and 3% materiality, using in-memory
  copies of the config. No file is edited.
- **Mitigation:** one seed-42 audit per model, then the full offset sweep for the
  largest kept finding, at a default 2% accuracy-loss budget.
- **Certificate:** issue, verify, tamper, verify again, in a temporary database.
- **Fairlearn baseline:** 4,000 synthetic applicants scored by all seven models
  over HTTP; demographic parity and equalized odds differences computed against
  the generator's hidden repayment label.

The harness launches real sandbox processes on free ports. Each audit is an
independent HTTP client. Runtime numbers are wall-clock times inside parallel
workers, so they are indicative; the serial demo benchmark is in
`eval/results/phase5_demo_smoke.md`.

---

## 7. Results

Raw artifacts: `eval/results/results.csv` (35 rows),
`materiality_sensitivity.csv` (70 rows), `mitigation_curves.csv`, and the chart
PNGs. The tables below are generated from those files.

### 7.1 Main run

| Model | Runs | Expectation PASS | Kept mean (range) | False alarms before → after | Number check | Mean runtime | Misses |
|---|---|---|---|---|---|---|---|
| 1 | 5 | 5/5 | 0.0 (0–0) | 0 → 0 | 5/5 | 22.0 s | none |
| 2 | 5 | 5/5 | 6.0 (6–6) | n/a | 5/5 | 30.7 s | none |
| 3 | 5 | 5/5 | 1.0 (1–1) | n/a | 5/5 | 23.9 s | none |
| 4 | 5 | 5/5 | 1.0 (1–1) | n/a | 5/5 | 23.4 s | none |
| 5 | 5 | **0/5** | 2.0 (2–2) | n/a | 5/5 | 26.3 s | single-attribute gender kept |
| 6 | 5 | 5/5 | 0.0 (0–0) | 0 → 0 | 5/5 | 27.9 s | none |
| 7 | 5 | 5/5 | 0.0 (0–0) | 0 → 0 | 5/5 | 413.6 s* | none |

- **Completed audits:** 35; **errors:** 0.
- **Narrative number checks:** 35/35 passed (100%).
- **Median runtime:** 26.3 s. 32 of 35 main audits finished under 60 s.

\* Three Model 7 audits measured 665–672 s in the shared run. They returned the
same result as the other seeds (0 kept) and are a measurement artifact of local
HTTP contention, not an audit failure; see 7.7.

The kept count is constant across seeds for every model. That is expected: the
generator, pair construction, and bootstrap are seeded per audit, and the planted
effects are far from the 2% threshold. The one exception is a borderline finding
(Model 5's single gender effect), which is exactly the case the sensitivity
analysis is for.

### 7.2 What was kept

At seed 42, the audit reproduces the planted structure:

| Model | Kept finding (seed 42) | Net flip | Verdict |
|---|---|---|---|
| 1 | none | — | 0 kept; 8 candidates rejected |
| 2 | gender (female) plus five female intersectional cells | 0.6535 | kept |
| 3 | `pincode_group=P2` | 0.6745 | kept |
| 4 | `name_group=N2` | 0.6890 | kept |
| 5 | `female · 45+ · rural` hotspot | 0.6320 | kept |
| 5 | single-attribute gender | 0.0265 | **kept, known miss** |
| 6 | none | — | 0 kept; noise candidates rejected |
| 7 | none | — | 8 candidates rejected as confounded |

For Model 2 the rejected candidates are pincode P2 (observational gap +5.2%,
net flip 0.0000) and name N2 (gap +6.3%, net flip 0.0000). The twin test finds no
counterfactual effect, so the observational gap is not attributed to the
protected attribute. Model 7 rejects gender, pincode, and name candidates for the
same reason; it is income-only.

### 7.3 False alarms

A false alarm here is a candidate that passes the significance and materiality
pre-filter in a model with no planted penalty (Models 1, 6, 7) — that is, a claim
the audit would have made without the Skeptic.

| Model | Materiality-qualified candidates before Skeptic | Kept after Skeptic |
|---|---|---|
| 1 (clean) | 0 | 0 |
| 6 (noisy) | 0 | 0 |
| 7 (confounded) | 0 | 0 |

The pre-registration allowed Model 7 to produce up to three observational
candidates, provided the Skeptic rejected them. In practice Model 7 produced
eight candidate findings in every run, all with a zero counterfactual effect, and
all were rejected; none of them even reached the materiality pre-filter. A naive
"significant observational gap" rule would have flagged them; the twin evidence
prevented it.

### 7.4 The pre-registration miss

Model 5 is the only expectation that failed, on all five seeds:

- expected: hotspot kept, single-attribute gender immaterial;
- observed: hotspot kept at 0.6320 **and** single-attribute gender kept at
  0.0265, just above the 0.02 materiality threshold.

The cause is the pre-registration arithmetic, not a change in the audit. The
single-attribute probe samples male originals; about 4% of those are in the
hotspot, not 2% of the whole population. The predicted diluted rate should have
been ≈ `0.04 × 0.63 = 0.025`, which is exactly what the audit found. No
threshold, penalty, population parameter, or model was changed. See D-009.

### 7.5 Materiality sensitivity

| Model | Kept mean at 1% | Kept mean at 2% (pre-registered) | Kept mean at 3% |
|---|---|---|---|
| 1 | 0.0 | 0.0 | 0.0 |
| 2 | 6.0 | 6.0 | 6.0 |
| 3 | 1.0 | 1.0 | 1.0 |
| 4 | 1.0 | 1.0 | 1.0 |
| 5 | 2.0 | 2.0 | **1.0** |
| 6 | 0.0 | 0.0 | 0.0 |
| 7 | 0.0 | 0.0 | 0.0 |

Only Model 5 moves. At 1% it keeps the hotspot and the single gender finding; at
3% the gender finding falls below materiality and only the hotspot remains. This
is the honest interpretation: the gender effect is real but small, and its
materiality verdict is threshold-dependent. The pre-registered run stays at 2%.

### 7.6 Mitigation

Seed 42, default 2% accuracy-loss budget:

| Model | Segment | Offset | Fairness gap | Δ accuracy | Sampling |
|---|---|---|---|---|---|
| 2 | female · 45+ · urban | +80 | 4.58% | −1.30% | natural population |
| 3 | P2 | +140 | 8.98% | −3.28% | natural population |
| 4 | N2 | +120 | 7.21% | −7.35% | natural population |
| 5 | female · 45+ · rural | +240 | 5.45% | −6.13% | stratified (1,000 + comparisons) |

Negative accuracy loss means agreement with the hidden repayment label
**improved** after removing the penalty. That is plausible: these penalties are
not predictive of repayment, so removing them helps accuracy. It is still an
offline what-if, not a causal claim. Model 5 needs the maximum tested offset
(240) and the rare-cell curve uses a stratified sample, which is why the UI
labels it.

### 7.7 Runtime

The audit itself is not the bottleneck; the shared evaluation harness is. The
median main audit took **26.3 s**; 32 of 35 were under 60 s. Three Model 7
audits recorded 665–672 s while sharing three sandbox processes with other
audits; they returned identical results, and the next two Model 7 seeds on the
same code took 32.0 s and 29.2 s. The serial, single-user demo is the fair
latency benchmark: **75.6 s for all three demo models** (30.2 s, 24.2 s,
21.1 s), measured by `eval.demo_smoke` against a real sandbox. An earlier run
of the same code measured 67.9 s; both runs keep every audit under 60 s.

The report does not hide the outliers: they are in `results.csv` with
`runtime_under_60 = False`. They are not used to claim a latency win.

### 7.8 Certificate test

| Check | Result |
|---|---|
| Empty approver rejected | True |
| Chain valid before tamper | True |
| Chain valid after tamper | False |
| First broken record | 0 |
| Certificate hash (eval harness run) | `f8204ddb5609c8644bf83cfa149eec2b243507522b339346a1505f59af699345` |

The tamper demo edits a real row, then verification recomputes every hash and
link and reports the first failure. The hash changes on every run because the
payload contains a UTC timestamp; the mechanism is what is being tested, not a
fixed digest.

### 7.9 Fairlearn comparison

Fairlearn on 4,000 observational applicants, using the hidden repayment label:

| Model | Worst DP difference (attribute) | Gender DP | Gender EO | FairLens result |
|---|---|---|---|---|
| 1 | 0.1403 (age band) | 0.0613 | 0.0497 | 0 kept |
| 2 | 0.6605 (gender) | 0.6605 | 0.8095 | gender + cells kept |
| 3 | 0.6814 (pincode) | 0.0304 | 0.0155 | P2 kept |
| 4 | 0.6725 (name) | 0.0531 | 0.0442 | N2 kept |
| 5 | 0.1564 (urban/rural) | 0.0897 | 0.0870 | hotspot + gender kept |
| 6 | 0.1024 (age band) | 0.0419 | 0.0478 | 0 kept |
| 7 | 0.2472 (pincode) | 0.1501 | 0.1544 | 0 kept (confounded) |

Two rows make the argument:

- **Model 1** is a clean control with no planted penalty, yet it has an age-band
  DP gap of 0.1403 and a pincode DP gap of 0.1401. A dashboard would flag it.
  The twins find nothing.
- **Model 7** is income-only, yet its gender DP gap is 0.1501 and its pincode DP
  gap is 0.2472. FairLens keeps nothing because the counterfactual effect is
  zero.

Observational metrics and counterfactual evidence answer different questions.
The first asks "are outcomes different?"; the second asks "does the model change
its decision when only this signal changes?" FairLens reports both, and refuses
to call the first one a finding on its own.

### 7.10 UI checks

The dashboard was driven with headless Chrome at 1366×768 and 1920×1080. Both
sizes have no horizontal page overflow (`scrollWidth == viewport width`). The
full report, the empty certificate state, a verified chain, and a tampered chain
were captured. The Streamlit test harness also exercises the audit, approve,
reject, demo, and tamper flows.

---

## 8. Dashboard and demo experience

The dashboard is a single Streamlit page with two tabs.

**Audit tab**

- header with model picker, sandbox URL, **Start Audit**, and **Demo mode**;
- pipeline strip that lights up stage by stage;
- live agent log, newest first, colour-coded; Skeptic rejections are red;
- findings board — kept cards carry evidence, CI, and checks; rejected cards
  carry a `REJECTED` stamp and the reason;
- intersectional heatmap with a table fallback;
- impact counter that counts up to the per-10,000 estimate;
- mitigation slider in an `st.fragment`, so moving it reruns only that section;
- number-checked narrative with a `NUMBER CHECK PASSED` badge;
- sign-off: approver name plus Approve/Reject. No name, no certificate.

**Certificates tab**

- chain view with genesis, record hash, previous hash, approver, decision, and
  UTC timestamp;
- **Verify chain** recomputes the chain; the badge is `NOT CHECKED` until the
  user asks, `CHAIN VERIFIED` or `CHAIN BROKEN` after;
- a labelled tamper demo behind a confirmation checkbox, with the first broken
  record highlighted;
- reset-demo-database.

**Design and layout**

- `.streamlit/config.toml` sets a dark theme, one accent (`#5EEAD4`), and Inter;
  `ui/style.css` is injected once and defines the cards, JetBrains Mono for
  logs and hashes, and the pulse/stamp/glow animations.
- One Plotly template: transparent background, accent series, no modebar.
- The heatmap uses a fixed 0–100 pp colour context, so a 5 pp cell cannot look
  as alarming as a 60 pp cell. The mitigation chart puts both series on one
  percentage-point axis; a second axis would make them look comparable when
  they are not.
- Empty, loading, and error states are explicit. An unreachable sandbox shows an
  error card; no audit shows a clear empty state; zero certificates shows
  `NOT CHECKED / 0 records`, not a vacuous verification.
- Layout was checked at 1366×768 and 1920×1080 with headless Chrome. In both
  cases `document.documentElement.scrollWidth` equals the viewport width. The
  only elements outside the viewport are hidden Plotly SVG artifacts at
  `x = −10000`.

Screenshots: `eval/results/ui_1366x768.png`, `ui_1920x1080.png`, and the three
certificate states.

The demo path is **Model 2 → Model 7 → Model 5**. **Demo mode** runs all three
and leaves the last report open. The latest serial headless run took **75.6 s**
for the three audits (30.2 s, 24.2 s, 21.1 s), and an earlier run took 67.9 s;
every audit stays under the 60-second budget.

Known cosmetic issue: Streamlit 1.66.1 prints a deprecation warning for
`st.components.v1.html`. The component is required by the brief and still
works; `st.iframe` cannot carry the inline HTML/JS the animations use.

---

## 9. What failed, and what we would fix

This section is deliberately not a victory lap.

### The Model 5 pre-registration miss

`expected_findings.md` predicted the single-attribute gender effect for Model 5
would be about **0.012** net flip and therefore immaterial. The seed-42 audit
kept it at **0.0265**, above the 0.02 threshold. The audit also kept the
intersectional hotspot at **0.6320**, as predicted.

The cause is a pre-registration arithmetic error, not a bug in the audit: the
single-attribute probe samples male originals, and about 4% of those are in the
hotspot, not 2% of the whole population. The predicted diluted rate should have
been about `0.04 × 0.63 ≈ 0.025`.

We did not change the materiality threshold, the penalty, the generator, or the
model. The miss is carried in the evaluation summary and the demo script. It is
also the best argument for pre-registration: the expectation was falsifiable and
it was falsified.

### False alarms and rejected candidates

Every candidate is kept or rejected with a rule and a reason. Rejected
candidates remain on the board. Model 7 produces observational gaps for gender,
pincode, and name; all are rejected because the counterfactual effect is zero —
the model scores income only. This is the intended behaviour, not a miss: the
pre-registration allowed Model 7 to produce up to three observational candidates
as long as the Skeptic rejected them.

### Defects found in the final review, and fixed

The final pass re-ran the live audits and the headless demo, then reviewed the
code paths that the demo does not exercise. These were real defects, not
cosmetic changes:

- **Port override did not reach the dashboard.** `run.ps1` / `run.sh` accepted
  `FAIRLENS_API_PORT`, but the UI still defaulted to `config.yaml`'s 8010. A
  non-default port started a sandbox the dashboard could not reach. The
  launchers now export `FAIRLENS_API_URL`, the UI reads it, and a regression
  test checks it.
- **Certificates hashed the wrong config.** Sign-off hashed the global config at
  signing time. It now hashes `report.config`, the config the audit actually
  ran with, so a sensitivity audit cannot produce a certificate whose
  thresholds disagree with its findings.
- **Demo inspection showed the wrong log.** "Open demo result" changed the
  report but left the live log and pipeline strip on the last model (5). The
  dashboard now stores events per demo model and restores the selected one.
- **A budget-breaking offset could be called compliant.** `recommend` fell back
  to the curve's first point when no offset fit the accuracy budget, while
  keeping a rationale that claimed budget compliance. It now returns
  `within_budget: False`, shows the smallest tested offset, and says plainly
  that no tested point fits. This state is only reachable with a negative budget
  or a malformed curve.
- **Template trimming could delete the limitations.** The old loop popped from a
  fixed index and could remove the rejected/immaterial disclosure or the
  limitations paragraph. It now removes only per-finding "For ..." sentences,
  and a regression test asserts the disclosure and limitations survive.
- **The reporter had a fabricated count fallback.** An `or 12` turned a measured
  zero cell count into a made-up 12. It was removed; the payload now reports the
  measured value.
- **Model 6 documentation was wrong.** The frozen `expected_findings.md` says
  "independent per-request noise"; the implementation draws deterministic
  per-applicant noise (independent across twins, stable across retries). The
  frozen pre-registration was not edited. The implementation and the difference
  are recorded in `DECISIONS.md` D-016, `SPEC.md`, and `config.yaml`.

The regression suite is now **84 passing tests** (up from 80), and the latest
headless demo completed all three audits plus the certificate/tamper/unreachable
checks in **75.6 s**. The certificate chain still cannot detect deletion of
trailing rows without an external head hash; that is a documented design limit,
not a fixed defect.

### Method limits

- **Twins are approximations.** They hold observed fields fixed, not unobserved
  ones. A model that reacts to a feature we do not vary will look neutral.
- **A null result is not proof of fairness.** It means this probe, at this
  sample size, did not detect disparate treatment.
- **Multiple testing is controlled within families, not globally.** Holm is
  applied to the three single-attribute tests and to the 12 cells separately.
- **Only the five largest intersectional cells are carried into the report.**
  All 12 cells are tested and Holm-corrected, but the pipeline reports the top
  five by net flip rate. This keeps the board readable and focuses the Skeptic,
  at the cost of possibly omitting a sixth genuinely affected cell. Model 2 is
  the boundary case: it has a gender effect in all six female cells, and five
  are reported. The heatmap still shows the full cell grid.
- **The bootstrap CI is seeded**, so it is reproducible, not a Bayesian
  statement.
- **The Skeptic is a rule set.** It encodes our judgement about materiality,
  confounding, and sample size. Another team would write different rules.
- **Impact is a linear translation** of a net flip rate. It is an
  interpretability aid, not a causal estimate of downstream harm.
- **Mitigation uses a hidden label** for accuracy. In a real audit that label is
  usually unavailable, so the curve is an offline what-if.
- **The number check is syntactic.** It proves the prose matches the JSON, not
  that the JSON is the right analysis.
- **The certificate is tamper-evident, not signed.** Anyone with write access
  can recompute the chain. It also cannot detect deletion of trailing records
  without an external head hash or append-only log. Digital signatures and such
  an anchor are future work.
- **Synthetic data.** Pincodes, names, and income distributions are invented.
  No claim is made about real Indian populations or a real lender.
- **No authentication or multi-user store.** The dashboard is a local demo; the
  certificate database is a local SQLite file.

---

## 10. Reproducibility

Environment: Python 3.11 in `.venv`; FastAPI/Uvicorn, Streamlit 1.66.1,
pytest, httpx, numpy, scipy, statsmodels, scikit-learn, Plotly, Pillow,
pydantic v2, PyYAML, fairlearn. Matplotlib is intentionally absent: its native
font DLL is blocked on the build machine, so evaluation charts use Pillow
(`eval/charts.py`).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

.\.venv\Scripts\python -m pytest -q                     # full suite
.\.venv\Scripts\python -m eval.demo_smoke               # 3-model end-to-end
.\.venv\Scripts\python -m eval.run_eval                 # 35 + 70 audits
.\.venv\Scripts\python -m eval.fairlearn_baseline --n 4000
```

Artifacts:

| File | Contents |
|---|---|
| `eval/results/results.csv` | Every main audit: model, seed, kept/rejected, expectation, runtime, number check, error |
| `eval/results/materiality_sensitivity.csv` | 1% and 3% audits |
| `eval/results/mitigation_curves.csv` | Full offset sweeps at seed 42 |
| `eval/results/summary.md` | Aggregated table, false alarms, misses, sensitivity, certificate test |
| `eval/results/fairlearn.md` / `.csv` | Observational baseline |
| `eval/results/phase5_demo_smoke.md` | Serial three-model demo and certificate flow |
| `eval/results/*.png` | Evaluation charts and dashboard screenshots |

The demo is deterministic at seed 42. Evaluation seeds 1–5 are reserved; the
mitigation sweeps use seed 42 plus a fixed offset (`42 + 31,000`) so they do not
consume an evaluation seed.

---

## 11. Future work

1. **Digital signatures.** Sign each certificate with an Ed25519 key held by the
   approver, and anchor the chain head outside the database. That turns
   tamper-evidence into authorship evidence.
2. **Adaptive probing.** Spend more pairs where the CI is wide, instead of fixed
   per-attribute counts.
3. **Richer twin design.** Vary interaction terms and near-boundary cases, and
   estimate treatment effects for intersectional groups with hierarchical
   shrinkage instead of independent cells.
4. **Real-label-free mitigation.** Replace hidden-label accuracy with a
   proxy-constrained or counterfactual objective, and state the assumption
   explicitly.
5. **Drift monitoring.** Re-run the same frozen probe set on a schedule and
   compare net flip rates over time.
6. **Multi-auditor workflow.** Roles, review queues, and an external append-only
   log; the current SQLite file is single-user.
7. **LLM hardening.** Keep the number checker, add claim-level entailment checks,
   and log every prompt/response pair as evidence.

