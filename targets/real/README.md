# Real-data targets (R3a)

These are the first FairLens targets whose behaviour nobody planted. They are
trained on public UCI datasets. The seven synthetic sandbox models remain the
validation suite; real-target results are reported separately and labelled as
such.

## Datasets

| Target | Dataset | Rows | Licence | Citation |
|---|---|---|---|---|
| `uci_credit_default` | [Default of Credit Card Clients](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients) (UCI 350) | 30,000 | CC BY 4.0 | Yeh, I. C., & Lien, C. H. (2009). *The comparisons of data mining techniques for the predictive accuracy of probability of default of credit card clients.* Expert Systems with Applications, 36(2), 2473–2480. DOI 10.24432/C55S3H |
| `adult_income` | [Adult](https://archive.ics.uci.edu/dataset/2/adult) (UCI 2) | 32,561 | CC BY 4.0 | Becker, B., & Kohavi, R. (1996). *Adult* [Dataset]. UCI Machine Learning Repository. DOI 10.24432/C5XW20 |

Both datasets describe people. They are used here only to train a model and to
measure its behaviour; no row is presented as a FairLens applicant, and no
claim is made about any real person or group.

### Download and cache

```powershell
.\.venv\Scripts\python -m targets.real.train
```

This downloads the archives from the UCI URLs in `targets/real/datasets.py`,
extracts them under `data/real/raw/`, and writes canonical CSVs to
`data/real/`. The CSVs and trained artifacts are committed, so audits and tests
run offline.

If the download fails, the loader raises `DatasetUnavailable` and prints the
exact URL and destination. Place the archive here:

```
data/real/raw/credit.zip     -> contains "default of credit card clients.xls"
data/real/raw/adult.zip      -> contains adult.data and adult.test
```

Nothing is synthesised as a substitute. `adult.test` is downloaded for
completeness but not used: the evaluation uses a stratified 80/20 split of
`adult.data`, fixed at seed 42.

## Models

| Target | Estimator | Label | Approval rule |
|---|---|---|---|
| `uci_credit_default` | Logistic regression (`StandardScaler`, `max_iter=2000`, seed 42) | `default payment next month` | approve if `P(no default) >= 0.5`; score = `P*1000` |
| `adult_income` | Histogram gradient boosting (`max_iter=200`, `lr=0.08`, seed 42) | income `> 50K` | approve if `P(>50K) >= 0.5`; score = `P*1000` |

Both are "natural" models: the protected attribute `sex` is an ordinary feature,
because that is what a practitioner training on these columns would normally do.
No fairness-aware preprocessing, no dropped protected attribute. This choice is
recorded in `DECISIONS.md` D-019. The Adult model also uses `race`; the credit
model has no race column.

Holdout accuracy, AUC, approval rate, Fairlearn demographic-parity and
equalized-odds differences, feature ranges, quantile grids, and category
vocabularies are written to
`data/real/artifacts/<model>.metrics.json`.

## How dataset columns map to the canonical applicant

`targets/real/features.py` is the single mapping used by both the serving
process and the adapter's feasibility check. Numeric canonical fields use a
monotone empirical-quantile transform into the dataset's observed distribution,
recorded in `metrics.json`. It is deterministic: two applicants that differ only
in gender differ only in `sex` after mapping.

### `uci_credit_default`

| Dataset column | Source |
|---|---|
| `LIMIT_BAL` | `income`, quantile-mapped |
| `SEX` | `gender` (1 = male, 2 = female) |
| `AGE` | `age`, clipped to the training range |
| `EDUCATION` | `credit_score`: >=750 -> 1, >=650 -> 2, else 3 |
| `MARRIAGE` | constant 2 |
| `PAY_0`, `PAY_2`..`PAY_6` | `clip(round((700 - credit_score) / 55), -2, 8)` |
| `BILL_AMT1`..`6` | `loan_amount`, quantile-mapped |
| `PAY_AMT1`..`6` | `income / 12`, quantile-mapped |

Canonical fields **not used**: `employment_years`, `pincode`, `name`,
`pincode_group`, `name_group`, `urban_rural`, `age_band`, `id`.

### `adult_income`

| Dataset column | Source |
|---|---|
| `age` | `age`, clipped to the training range |
| `sex` | `gender` |
| `education`, `education_num` | `credit_score`: >=750 -> Masters/14, >=650 -> Bachelors/13, else HS-grad/9 |
| `hours_per_week` | `employment_years`, quantile-mapped |
| `fnlwgt` | training median |
| `workclass` | constant `Private` |
| `marital_status` | constant `Never-married` |
| `occupation` | constant `Prof-specialty` |
| `relationship` | constant `Not-in-family` |
| `race` | constant `White` |
| `capital_gain`, `capital_loss` | 0 |
| `native_country` | constant `United-States` |

Canonical fields **not used**: `income`, `loan_amount`, `pincode`, `name`,
`pincode_group`, `name_group`, `urban_rural`, `age_band`, `id`.

`race` exists in the dataset but not in the canonical contract. The audit
therefore cannot vary it; it is held at the training mode when serving. The
Fairlearn baseline still evaluates race on the real holdout data, which is the
only place race is measured.

## Protected attributes and unsupported probes

Both datasets have `sex`, so the canonical `gender` probe is defined. Both have
`age`, which is a model input in both models and is measured by the Fairlearn
baseline; the frozen FairLens probe family has no age-only twin, so age is not
counterfactually audited. Adult has `race`; the canonical contract has no race
field, so race is not probed.

The datasets have **no name column and no pincode/region column**. The adapters
declare these probes unsupported:

| Probe | Status | Why |
|---|---|---|
| `gender` | supported | dataset `sex` |
| `pincode_group` | **unsupported** | no region column; a twin would not change any input |
| `name_group` | **unsupported** | no name column; a name twin would not change any input |
| `intersectional` | **unsupported** | the 12 cells require urban/rural, which neither dataset has |

The auditor logs one event per skipped probe with the reason and records
`supported_probes` / `skipped_probes` in the report. It never invents a pincode
or a name to keep the probe count.

## Twin feasibility

`RealTargetAdapter.validate_pair` maps both applicants and checks:

1. every feature is inside the training range or vocabulary;
2. a gender twin changes **exactly** `sex` (the synthetic name also changes in
   the canonical pair, but names are not model inputs);
3. other supported probes must change at least one mapped feature.

Infeasible pairs are counted and reported in a `prober` event, never silently
dropped. Because the mapping is quantile-based, feasible pairs are expected in
normal operation; the check exists to catch domain drift and bad mappings.

## Serve and audit

```powershell
# terminal 1: the real-data target service (default 127.0.0.1:8030)
.\.venv\Scripts\python -m targets.real.serve

# terminal 2: the audit service (default 127.0.0.1:8020)
.\.venv\Scripts\python -m api.serve

# start an audit routed through the YAML adapter
$body = '{"model_id": 2, "target": "targets/real/adult-income.yaml", "include_mitigation": false}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8020/audits -ContentType 'application/json' -Body $body
```

`build_target("targets/real/uci-credit-default.yaml", config)` and
`build_target("targets/real/adult-income.yaml", config)` return a
`RealTargetAdapter`. Override the service URL with `FAIRLENS_REAL_URL`.

## Limitations

- The **model** is real; the **probe population** is the synthetic FairLens
  generator mapped onto dataset columns. Results describe this model's
  counterfactual behaviour over that mapped population, not the dataset's own
  population.
- `race` and several Adult columns are constants when serving, so the audit
  cannot test them even though the model was trained on them.
- Approval rates are the model's natural rates at a 0.5 probability threshold.
  The threshold was fixed before auditing and is not tuned.
- The credit model has no region or name input, so two of the three frozen
  probes do not exist for it. The audit is narrower than the sandbox audit.
- This is not a production credit model and not a claim about UCI's data
  subjects. It is a reproducibility artifact for auditing a model nobody
  hand-tuned for the demo.
