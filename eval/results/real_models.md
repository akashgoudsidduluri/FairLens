# Real-data target results (R3b)

**Status: evaluated after pre-registration.** `expected_findings.md` was
committed with "No expected finding. Report whatever is found, including
no material bias." before this evaluation. No threshold, feature, model,
or mapping was changed after seeing these results.

These are **not** the seven sandbox models. The model is trained on public
UCI data; the probe population is the synthetic FairLens generator mapped
into the dataset's columns, not the dataset's own population.

## Protocol

- Frozen v1 thresholds: alpha 0.05, Holm correction, materiality 0.02,
  2,000 pairs per supported attribute, 4,000 observational applicants,
  seeds 1-5, 95% bootstrap CI with 4,000 iterations.
- `include_mitigation: false`: these targets do not expose the sandbox
  score-offset endpoint, so an offset sweep is not comparable.
- Approval rule fixed in R3a: `P(favourable) >= 0.5`, score `P*1000`.
- Only probes the adapter declares are run. Unsupported probes are logged
  and reported, never faked.

## Headline table (per model, seeds 1-5)

| Real target | Kept | Rejected | Immaterial | Impact per 10,000 (max candidate) | Fairlearn on holdout, sex DP / EO | age DP / EO | race DP / EO | Holdout accuracy | Mean runtime | Coverage |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|
| UCI credit default (logistic regression) | 0 | 5 | 0 | 0.0 | DP 0.0235 / EO 0.0318 | DP 0.0274 / EO 0.0364 | n/a | 0.8083 | 19.5s | tested: gender; skipped: intersectional, name_group, pincode_group |
| UCI Adult (gradient boosting) | 0 | 0 | 5 | 120.0 | DP 0.1783 / EO 0.0679 | DP 0.2468 / EO 0.1596 | DP 0.1615 / EO 0.5556 | 0.8756 | 13.4s | tested: gender; skipped: intersectional, name_group, pincode_group |

Fairlearn numbers are computed on the same real holdout split as the
model metrics and are shown **for comparison only**. They are not a
FairLens audit result and are not used to reinterpret the paired
counterfactual evidence.

Impact is `max(net flip rate, 0) * 10,000` for every candidate, including
immaterial and rejected ones. Only a kept finding turns it into an audit
conclusion. `0` means no candidate had a positive net flip rate.

## Per-seed results

| Real target | Seed | Kept | Rejected (reason) | Immaterial | Impact per 10,000 | Runtime |
|---|---:|---:|---|---:|---:|---:|
| adult_income | 1 | 0 | none | gender=female: n=2000, b=13, c=0, net=+0.0065 (95% CI +0.0035 to +0.0100), p_adj=2.441e-04, impact=65.0/10k. Significant but immaterial: net flip rate +0.0065 is below the pre-registered materiality threshold 0.02. | 65.0 | 12.88s |
| adult_income | 2 | 0 | none | gender=female: n=2000, b=18, c=0, net=+0.0090 (95% CI +0.0050 to +0.0135), p_adj=7.629e-06, impact=90.0/10k. Significant but immaterial: net flip rate +0.0090 is below the pre-registered materiality threshold 0.02. | 90.0 | 14.11s |
| adult_income | 3 | 0 | none | gender=female: n=2000, b=10, c=0, net=+0.0050 (95% CI +0.0020 to +0.0085), p_adj=1.953e-03, impact=50.0/10k. Significant but immaterial: net flip rate +0.0050 is below the pre-registered materiality threshold 0.02. | 50.0 | 12.83s |
| adult_income | 4 | 0 | none | gender=female: n=2000, b=15, c=0, net=+0.0075 (95% CI +0.0040 to +0.0115), p_adj=6.104e-05, impact=75.0/10k. Significant but immaterial: net flip rate +0.0075 is below the pre-registered materiality threshold 0.02. | 75.0 | 14.20s |
| adult_income | 5 | 0 | none | gender=female: n=2000, b=24, c=0, net=+0.0120 (95% CI +0.0075 to +0.0170), p_adj=1.192e-07, impact=120.0/10k. Significant but immaterial: net flip rate +0.0120 is below the pre-registered materiality threshold 0.02. | 120.0 | 13.16s |
| uci_credit_default | 1 | 0 | gender=male: n=2000, b=0, c=0, net=+0.0000 (95% CI +0.0000 to +0.0000), p_adj=1.000e+00, impact=0.0/10k. Rejected: not significant after Holm correction (p_adj=1.00e+00). | none | 0.0 | 22.66s |
| uci_credit_default | 2 | 0 | gender=male: n=2000, b=0, c=0, net=+0.0000 (95% CI +0.0000 to +0.0000), p_adj=1.000e+00, impact=0.0/10k. Rejected as confounded: the observational gap (+0.0212) is not accompanied by a material counterfactual effect (net flip +0.0000). This is consistent with legitimate factors such as income. | none | 0.0 | 17.82s |
| uci_credit_default | 3 | 0 | gender=male: n=2000, b=0, c=0, net=+0.0000 (95% CI +0.0000 to +0.0000), p_adj=1.000e+00, impact=0.0/10k. Rejected: not significant after Holm correction (p_adj=1.00e+00). | none | 0.0 | 19.02s |
| uci_credit_default | 4 | 0 | gender=male: n=2000, b=0, c=0, net=+0.0000 (95% CI +0.0000 to +0.0000), p_adj=1.000e+00, impact=0.0/10k. Rejected: not significant after Holm correction (p_adj=1.00e+00). | none | 0.0 | 18.13s |
| uci_credit_default | 5 | 0 | gender=male: n=2000, b=0, c=0, net=+0.0000 (95% CI +0.0000 to +0.0000), p_adj=1.000e+00, impact=0.0/10k. Rejected: not significant after Holm correction (p_adj=1.00e+00). | none | 0.0 | 19.77s |

## Findings in detail

Every candidate that reached the Skeptic is listed, including rejected
and immaterial ones. A rejected finding is kept in the record.

| Real target | Seed | Finding | Status | n | b | c | Net flip | 95% CI | Holm p | Impact per 10,000 | Reason |
|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|---|
| adult_income | 1 | gender=female | immaterial | 2000 | 13 | 0 | +0.0065 | +0.0035 to +0.0100 | 2.441e-04 | 65.0 | Significant but immaterial: net flip rate +0.0065 is below the pre-registered materiality threshold 0.02. |
| adult_income | 2 | gender=female | immaterial | 2000 | 18 | 0 | +0.0090 | +0.0050 to +0.0135 | 7.629e-06 | 90.0 | Significant but immaterial: net flip rate +0.0090 is below the pre-registered materiality threshold 0.02. |
| adult_income | 3 | gender=female | immaterial | 2000 | 10 | 0 | +0.0050 | +0.0020 to +0.0085 | 1.953e-03 | 50.0 | Significant but immaterial: net flip rate +0.0050 is below the pre-registered materiality threshold 0.02. |
| adult_income | 4 | gender=female | immaterial | 2000 | 15 | 0 | +0.0075 | +0.0040 to +0.0115 | 6.104e-05 | 75.0 | Significant but immaterial: net flip rate +0.0075 is below the pre-registered materiality threshold 0.02. |
| adult_income | 5 | gender=female | immaterial | 2000 | 24 | 0 | +0.0120 | +0.0075 to +0.0170 | 1.192e-07 | 120.0 | Significant but immaterial: net flip rate +0.0120 is below the pre-registered materiality threshold 0.02. |
| uci_credit_default | 1 | gender=male | rejected | 2000 | 0 | 0 | +0.0000 | +0.0000 to +0.0000 | 1.000e+00 | 0.0 | Rejected: not significant after Holm correction (p_adj=1.00e+00). |
| uci_credit_default | 2 | gender=male | rejected | 2000 | 0 | 0 | +0.0000 | +0.0000 to +0.0000 | 1.000e+00 | 0.0 | Rejected as confounded: the observational gap (+0.0212) is not accompanied by a material counterfactual effect (net flip +0.0000). This is consistent with legitimate factors such as income. |
| uci_credit_default | 3 | gender=male | rejected | 2000 | 0 | 0 | +0.0000 | +0.0000 to +0.0000 | 1.000e+00 | 0.0 | Rejected: not significant after Holm correction (p_adj=1.00e+00). |
| uci_credit_default | 4 | gender=male | rejected | 2000 | 0 | 0 | +0.0000 | +0.0000 to +0.0000 | 1.000e+00 | 0.0 | Rejected: not significant after Holm correction (p_adj=1.00e+00). |
| uci_credit_default | 5 | gender=male | rejected | 2000 | 0 | 0 | +0.0000 | +0.0000 to +0.0000 | 1.000e+00 | 0.0 | Rejected: not significant after Holm correction (p_adj=1.00e+00). |

## What was found

- **UCI credit default (logistic regression)**: No kept finding, and the result is an **inconclusive null**, not evidence of no bias: all 10,000 twin pairs produced the same decision before and after the gender flip (b=0, c=0). On this mapped population no score sat close enough to the 500 approval threshold for a gender flip to cross it, so the probe had no power to detect an effect. This is a limitation of the probe population, not proof that the model is fair. Fairlearn's observational baseline is in the headline table.
- **UCI Adult (gradient boosting)**: No material bias under the pre-registered 2% threshold: net flip rates ranged +0.0050 to +0.0120 across seeds, and every candidate was classified immaterial (significant but below 0.02), not kept. The direction was consistent in every seed. This is not proof of fairness; a sub-threshold effect is still an effect, and pincode, name, and intersectional probes could not be tested.

## What FairLens could and could not test

**UCI credit default (logistic regression)**. Could test: gender. Could not test:
- `intersectional`: Intersectional cells require urban/rural; the dataset has no such column.
- `name_group`: Dataset has no applicant-name column; the model was trained without a name.
- `pincode_group`: Dataset has no pincode or region column; the model was trained without one.
- Age and race: not counterfactually probed. The frozen probe family has no
  age-only twin, and race has no canonical field. Both are measured on
  the real holdout by Fairlearn only, which is an observational baseline,
  not the twin audit.
**UCI Adult (gradient boosting)**. Could test: gender. Could not test:
- `intersectional`: Intersectional cells require urban/rural; the dataset has no such column.
- `name_group`: Dataset has no applicant-name column; the model was trained without a name.
- `pincode_group`: Dataset has no pincode or region column; the model was trained without one.
- Age and race: not counterfactually probed. The frozen probe family has no
  age-only twin, and race has no canonical field. Both are measured on
  the real holdout by Fairlearn only, which is an observational baseline,
  not the twin audit.

## Limitations

- The **model** is real; the **probe population** is the synthetic FairLens
  generator mapped into the dataset's columns. Results describe this model's
  counterfactual behaviour over that mapped population, not the dataset's
  own population and not any real lender.
- Only gender is counterfactually testable. No pincode, name, or
  intersectional result exists for these targets. Absence of those findings
  is not evidence of absence of bias.
- The Adult model consumes `race` but the canonical contract has no race
  field; race is held at the training mode when serving. The credit model
  has no race column at all.
- Several dataset columns with no canonical source are held at documented
  training constants when serving. The audit varies gender while holding
  those constants fixed.
- Fairlearn demographic parity and equalized odds are computed once on the
  holdout and do not vary with audit seed. They can disagree with each
  other and with the twin test; that is expected, not a bug.
- A null twin result is not proof of fairness. It means no material
  disparity was detected by this probe on this mapped population at the
  pre-registered thresholds.

## LLM screener (R3c)

**Status: unavailable. No LLM audit was run.**

Reason: ANTHROPIC_MODEL and ANTHROPIC_API_KEY are not set.

The target reports `unavailable` rather than inventing a decision. The
adapter is still implemented and covered by tests that inject a fake
client: strict JSON parsing, disk caching, repeat variance, call and cost
caps, twin feasibility, and the import boundary. Set `ANTHROPIC_API_KEY`
and `ANTHROPIC_MODEL` and rerun:

```powershell
.venv\Scripts\python -m eval.run_llm_eval
```

Model configured: `not set`. Repeat count: 3. Cap: 300 calls.

This is a reported outcome, not a hidden failure. No name or region
effect can be claimed without a run.
