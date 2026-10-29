# Suite B and the generalized protocol (R5 Step 7)

Generated: 2026-10-29T14:57:44+00:00

Pre-registered run from `expected_findings.md`: **models 8-14 plus clean control B (Model 15) x seeds 1-5** at the frozen materiality 2%, alpha 0.05, Holm across every discovery cell, 80:20 discovery/confirmation. Models 1-7 (suite A) are rerun with the generalized protocol and shown next to their frozen old-protocol facts; the old numbers are not replaced or retuned. The 1%/3% sensitivity reuses the same seeds and statistics with an in-memory materiality override.

A miss is any planted model whose expected treatment/context is not in the kept findings, a kept legitimate attribute as treatment, or a kept finding in Model 14/15. A false alarm before the Skeptic is a candidate cell (confirmed or over the confirmation budget) that is Holm-significant with net flip >= materiality; after the Skeptic it is a kept finding.

## Suite B: expected vs found (5 seeds, 2%)

| Model | Expected treatment / context | Kept mean (range) | PASS | Kept findings | False alarms before -> after | Cells | Candidates | Confirmed | MDE n=200 | MDE n=1000 | Mean runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | age `45+` / main effect | 1.0 (1-1) | 5/5 | gen-age-45plus-credit_score-high x3; gen-age-45plus-employment_years-high x1; gen-age-45plus-income-high x1 | 135 -> 5 | 110 | 16 | 16 | 0.099 | 0.044 | 80.7s |
| 9 | pincode P2 or gender female / the other attribute | 8.2 (1-11) | 1/5 | gen-pincode_group-p2-gender-female-loan_amount-high x5; gen-pincode_group-p2-credit_score-high x4; gen-pincode_group-p2-credit_score-mid x4; gen-pincode_group-p2-employment_years-high x4; gen-pincode_group-p2-urban_rural-urban x4; gen-pincode_group-p2-age-35-44 x3; gen-pincode_group-p2-income-high x3; gen-pincode_group-p2-income-mid x3; gen-pincode_group-p2-age-<35 x2; gen-pincode_group-p2-employment_years-mid x2; gen-pincode_group-p2-loan_amount-mid x2; gen-pincode_group-p2-name_group-n3 x2; gen-pincode_group-p2-loan_amount-low x1; gen-pincode_group-p2-name_group-n1 x1; gen-pincode_group-p2-name_group-n2-age-45plus x1 | 259 -> 41 | 110 | 16 | 16 | 0.099 | 0.044 | 76.3s |
| 10 | name N2 or age `45+` / the other attribute | 9.6 (9-10) | 0/5 | gen-age-45plus-credit_score-high x5; gen-age-45plus-employment_years-high x5; gen-name_group-n2-employment_years-high x5; gen-age-45plus-employment_years-mid x4; gen-age-45plus-gender-male x4; gen-age-45plus-urban_rural-urban x4; gen-name_group-n2-age-45plus x4; gen-age-45plus-income-mid x3; gen-name_group-n2-credit_score-high x3; gen-age-45plus-income-high x2; gen-age-45plus-pincode_group-p1 x2; gen-age-45plus-loan_amount-high x1; gen-age-45plus-loan_amount-low x1; gen-age-45plus-loan_amount-mid x1; gen-age-45plus-pincode_group-p3 x1; gen-name_group-n2-gender-female-age-45plus x1; gen-name_group-n2-loan_amount-high-urban_rural-rural x1; gen-name_group-n2-pincode_group-p1 x1 | 244 -> 48 | 110 | 16 | 16 | 0.099 | 0.044 | 76.1s |
| 11 | pincode P2 / `loan_amount=high` | 1.0 (1-1) | 0/5 | gen-pincode_group-p2-income-high x5 | 120 -> 5 | 110 | 16 | 16 | 0.099 | 0.044 | 5232.2s |
| 12 | gender female or age `45+` / 45+, rural, N2 | 1.6 (1-3) | 3/5 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 x5; gen-name_group-n2-age-45plus-pincode_group-p2 x1; gen-name_group-n2-income-low-age-45plus x1; gen-name_group-n2-loan_amount-high-urban_rural-rural x1 | 42 -> 8 | 110 | 8 | 8 | 0.099 | 0.044 | 93.7s |
| 13 | age main effect, graded | 3.6 (1-14) | 4/5 | gen-age-45plus-credit_score-high x5; gen-age-45plus-credit_score-mid x1; gen-age-45plus-employment_years-high x1; gen-age-45plus-employment_years-mid x1; gen-age-45plus-gender-male x1; gen-age-45plus-income-high x1; gen-age-45plus-income-mid x1; gen-age-45plus-loan_amount-high-gender-female x1; gen-age-45plus-loan_amount-mid x1; gen-age-45plus-name_group-n1 x1; gen-age-45plus-name_group-n3 x1; gen-age-45plus-pincode_group-p1 x1; gen-age-45plus-pincode_group-p3 x1; gen-age-45plus-urban_rural-urban x1 | 140 -> 18 | 110 | 16 | 16 | 0.099 | 0.044 | 95.3s |
| 14 | no kept group finding | 0.0 (0-0) | 0/5 | none | 0 -> 0 | 110 | 0 | 0 | 0.099 | 0.044 | 70.5s |
| 15 | no kept findings (control B) | 0.0 (0-0) | 5/5 | none | 0 -> 0 | 110 | 0 | 0 | 0.099 | 0.044 | 78.1s |

## Per-seed detail

| Model | Seed | Kept | Kept ids | Expectation | Misses | Notes | Runtime |
|---|---|---|---|---|---|---|---|
| 8 | 1 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 83.1s |
| 8 | 2 | 1 | gen-age-45plus-employment_years-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-employment_years-high context={'employment_years': 'high'} | 84.0s |
| 8 | 3 | 1 | gen-age-45plus-income-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-income-high context={'income': 'high'} | 82.6s |
| 8 | 4 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 81.4s |
| 8 | 5 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 72.5s |
| 9 | 1 | 1 | gen-pincode_group-p2-gender-female-loan_amount-high | PASS | none | none | 74.8s |
| 9 | 2 | 9 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-credit_score-high, gen-pincode_group-p2-employment_years-high, gen-pincode_group-p2-name_group-n1, gen-pincode_group-p2-urban_rural-urban, gen-pincode_group-p2-age-35-44, gen-pincode_group-p2-employment_years-mid, gen-pincode_group-p2-credit_score-mid, gen-pincode_group-p2-loan_amount-mid | MISS | expected exactly one kept finding, got 9 | none | 74.0s |
| 9 | 3 | 11 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-credit_score-high, gen-pincode_group-p2-employment_years-high, gen-pincode_group-p2-name_group-n3, gen-pincode_group-p2-income-mid, gen-pincode_group-p2-age-<35, gen-pincode_group-p2-age-35-44, gen-pincode_group-p2-urban_rural-urban, gen-pincode_group-p2-income-high, gen-pincode_group-p2-loan_amount-mid, gen-pincode_group-p2-credit_score-mid | MISS | expected exactly one kept finding, got 11 | none | 75.1s |
| 9 | 4 | 9 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-employment_years-high, gen-pincode_group-p2-credit_score-high, gen-pincode_group-p2-income-mid, gen-pincode_group-p2-income-high, gen-pincode_group-p2-age-35-44, gen-pincode_group-p2-credit_score-mid, gen-pincode_group-p2-loan_amount-low, gen-pincode_group-p2-urban_rural-urban | MISS | expected exactly one kept finding, got 9 | none | 80.3s |
| 9 | 5 | 11 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-income-mid, gen-pincode_group-p2-credit_score-high, gen-pincode_group-p2-name_group-n3, gen-pincode_group-p2-age-<35, gen-pincode_group-p2-credit_score-mid, gen-pincode_group-p2-employment_years-high, gen-pincode_group-p2-income-high, gen-pincode_group-p2-urban_rural-urban, gen-pincode_group-p2-name_group-n2-age-45plus, gen-pincode_group-p2-employment_years-mid | MISS | expected exactly one kept finding, got 11 | none | 77.5s |
| 10 | 1 | 10 | gen-name_group-n2-age-45plus, gen-age-45plus-employment_years-high, gen-name_group-n2-employment_years-high, gen-age-45plus-credit_score-high, gen-name_group-n2-credit_score-high, gen-age-45plus-gender-male, gen-age-45plus-income-mid, gen-age-45plus-pincode_group-p3, gen-age-45plus-urban_rural-urban, gen-age-45plus-employment_years-mid | MISS | expected exactly one kept finding, got 10 | none | 78.2s |
| 10 | 2 | 10 | gen-name_group-n2-age-45plus, gen-age-45plus-credit_score-high, gen-age-45plus-employment_years-high, gen-name_group-n2-loan_amount-high-urban_rural-rural, gen-age-45plus-employment_years-mid, gen-age-45plus-urban_rural-urban, gen-age-45plus-loan_amount-low, gen-name_group-n2-employment_years-high, gen-age-45plus-pincode_group-p1, gen-name_group-n2-pincode_group-p1 | MISS | expected exactly one kept finding, got 10 | none | 77.3s |
| 10 | 3 | 9 | gen-name_group-n2-gender-female-age-45plus, gen-age-45plus-employment_years-high, gen-age-45plus-credit_score-high, gen-age-45plus-income-mid, gen-age-45plus-income-high, gen-age-45plus-gender-male, gen-age-45plus-urban_rural-urban, gen-name_group-n2-credit_score-high, gen-name_group-n2-employment_years-high | MISS | expected exactly one kept finding, got 9 | none | 73.2s |
| 10 | 4 | 10 | gen-name_group-n2-age-45plus, gen-age-45plus-credit_score-high, gen-name_group-n2-employment_years-high, gen-age-45plus-employment_years-high, gen-age-45plus-employment_years-mid, gen-age-45plus-income-mid, gen-age-45plus-gender-male, gen-name_group-n2-credit_score-high, gen-age-45plus-pincode_group-p1, gen-age-45plus-urban_rural-urban | MISS | expected exactly one kept finding, got 10 | none | 75.1s |
| 10 | 5 | 9 | gen-name_group-n2-age-45plus, gen-age-45plus-employment_years-high, gen-age-45plus-credit_score-high, gen-name_group-n2-employment_years-high, gen-age-45plus-gender-male, gen-age-45plus-employment_years-mid, gen-age-45plus-loan_amount-high, gen-age-45plus-income-high, gen-age-45plus-loan_amount-mid | MISS | expected exactly one kept finding, got 9 | none | 76.5s |
| 11 | 1 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 72.1s |
| 11 | 2 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 6522.6s |
| 11 | 3 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 6521.1s |
| 11 | 4 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 6523.1s |
| 11 | 5 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 6522.3s |
| 12 | 1 | 3 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2, gen-name_group-n2-income-low-age-45plus, gen-name_group-n2-age-45plus-pincode_group-p2 | MISS | expected exactly one kept finding, got 3 | none | 99.3s |
| 12 | 2 | 2 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2, gen-name_group-n2-loan_amount-high-urban_rural-rural | MISS | expected exactly one kept finding, got 2 | none | 96.8s |
| 12 | 3 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 94.1s |
| 12 | 4 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 93.5s |
| 12 | 5 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 84.6s |
| 13 | 1 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 100.0s |
| 13 | 2 | 14 | gen-age-45plus-employment_years-high, gen-age-45plus-credit_score-high, gen-age-45plus-income-high, gen-age-45plus-name_group-n1, gen-age-45plus-income-mid, gen-age-45plus-gender-male, gen-age-45plus-pincode_group-p1, gen-age-45plus-employment_years-mid, gen-age-45plus-urban_rural-urban, gen-age-45plus-pincode_group-p3, gen-age-45plus-loan_amount-high-gender-female, gen-age-45plus-credit_score-mid, gen-age-45plus-name_group-n3, gen-age-45plus-loan_amount-mid | MISS | expected exactly one kept finding, got 14; expected exactly one kept finding, got 14 | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-employment_years-high context={'employment_years': 'high'} | 100.9s |
| 13 | 3 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 99.3s |
| 13 | 4 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 87.9s |
| 13 | 5 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 88.5s |
| 14 | 1 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 72.6s |
| 14 | 2 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 71.0s |
| 14 | 3 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 68.7s |
| 14 | 4 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 70.2s |
| 14 | 5 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 69.8s |
| 15 | 1 | 0 | none | PASS | none | none | 74.2s |
| 15 | 2 | 0 | none | PASS | none | none | 79.9s |
| 15 | 3 | 0 | none | PASS | none | none | 81.6s |
| 15 | 4 | 0 | none | PASS | none | none | 83.1s |
| 15 | 5 | 0 | none | PASS | none | none | 71.7s |

## Misses and notes across all seeds

- **MISS x5**: kept pincode P2 finding in the high-loan context is missing
- **MISS x5**: no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic)
- **MISS x4**: expected exactly one kept finding, got 9
- **MISS x3**: expected exactly one kept finding, got 10
- **MISS x2**: expected exactly one kept finding, got 11
- **MISS x2**: expected exactly one kept finding, got 14
- **MISS x1**: expected exactly one kept finding, got 2
- **MISS x1**: expected exactly one kept finding, got 3
- Note x7: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'}
- Note x2: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-employment_years-high context={'employment_years': 'high'}
- Note x1: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-income-high context={'income': 'high'}

## False alarms before and after the Skeptic (Models 14 and 15)

| Model | Seed | Kept | Confirmed cells | Before Skeptic | After Skeptic | Runtime |
|---|---|---|---|---|---|---|
| 14 | 1 | 0 | 0 | 0 | 0 | 72.6s |
| 14 | 2 | 0 | 0 | 0 | 0 | 71.0s |
| 14 | 3 | 0 | 0 | 0 | 0 | 68.7s |
| 14 | 4 | 0 | 0 | 0 | 0 | 70.2s |
| 14 | 5 | 0 | 0 | 0 | 0 | 69.8s |
| 15 | 1 | 0 | 0 | 0 | 0 | 74.2s |
| 15 | 2 | 0 | 0 | 0 | 0 | 79.9s |
| 15 | 3 | 0 | 0 | 0 | 0 | 81.6s |
| 15 | 4 | 0 | 0 | 0 | 0 | 83.1s |
| 15 | 5 | 0 | 0 | 0 | 0 | 71.7s |

## Age dose-response (diagnostic reported for Models 8 and 13)

Originals are the `<35` band; each point flips the age of the same applicant to one exact age, holding every other signal fixed. `500` pairs per point, fixed before the run. These probes are not used to select findings.

| Model | Seed | age 45 net | age 50 net | age 55 net | age 60 net |
|---|---|---|---|---|---|
| 8 | 1 | +0.0000 | +0.0000 | +0.6100 | +0.6100 |
| 8 | 2 | +0.0000 | +0.0000 | +0.5560 | +0.5560 |
| 8 | 3 | +0.0000 | +0.0000 | +0.5900 | +0.5900 |
| 8 | 4 | +0.0000 | +0.0000 | +0.5720 | +0.5720 |
| 8 | 5 | +0.0000 | +0.0000 | +0.5720 | +0.5720 |
| 13 | 1 | +0.3100 | +0.5160 | +0.5960 | +0.6100 |
| 13 | 2 | +0.2740 | +0.4680 | +0.5420 | +0.5540 |
| 13 | 3 | +0.2900 | +0.4880 | +0.5620 | +0.5880 |
| 13 | 4 | +0.2820 | +0.4760 | +0.5520 | +0.5720 |
| 13 | 5 | +0.2960 | +0.4880 | +0.5500 | +0.5680 |

## Materiality sensitivity (in-memory override, same seeds)

| Model | Kept mean 1% | Kept mean 2% | Kept mean 3% | PASS 1% | PASS 2% | PASS 3% |
|---|---|---|---|---|---|---|
| 8 | 1.0 | 1.0 | 1.0 | 5/5 | 5/5 | 5/5 |
| 9 | 8.2 | 8.2 | 8.2 | 1/5 | 1/5 | 1/5 |
| 10 | 9.6 | 9.6 | 9.6 | 0/5 | 0/5 | 0/5 |
| 11 | 1.0 | 1.0 | 1.0 | 0/5 | 0/5 | 0/5 |
| 12 | 1.6 | 1.6 | 1.6 | 3/5 | 3/5 | 3/5 |
| 13 | 3.6 | 3.6 | 3.6 | 4/5 | 4/5 | 4/5 |
| 14 | 0.0 | 0.0 | 0.0 | 0/5 | 0/5 | 0/5 |
| 15 | 0.0 | 0.0 | 0.0 | 5/5 | 5/5 | 5/5 |

The pre-registered materiality is 2%; 1% and 3% are sensitivity runs and are never used to pick the best result.

## Suite A rerun under the generalized protocol

Old-protocol facts are read from `eval/results/results.csv` (seven models x five seeds). They are frozen and never replaced. The new protocol is checked semantically because it no longer emits `single-*`/`inter-*` findings.

| Model | Old kept mean (range) | Old ids | New kept mean (range) | New ids | New PASS | New misses |
|---|---|---|---|---|---|---|
| 1 | 0.0 (0-0) | none | 0.0 (0-0) | none | 5/5 | none |
| 2 | 6.0 (6-6) | inter-female-35-44-rural, inter-female-35-44-urban, inter-female-45plus-rural, inter-female-45plus-urban, inter-female-<35-urban, single-gender-female | 1.0 (1-1) | gen-gender-female-credit_score-high, gen-gender-female-employment_years-high | 5/5 | none |
| 3 | 1.0 (1-1) | single-pincode_group-p2 | 1.0 (1-1) | gen-pincode_group-p2-credit_score-high | 5/5 | none |
| 4 | 1.0 (1-1) | single-name_group-n2 | 3.4 (1-13) | gen-name_group-n2-age-35-44, gen-name_group-n2-age-45plus, gen-name_group-n2-credit_score-high, gen-name_group-n2-credit_score-mid, gen-name_group-n2-employment_years-high, gen-name_group-n2-employment_years-mid, gen-name_group-n2-gender-male, gen-name_group-n2-income-high, gen-name_group-n2-income-mid, gen-name_group-n2-loan_amount-high, gen-name_group-n2-pincode_group-p1, gen-name_group-n2-pincode_group-p3, gen-name_group-n2-urban_rural-urban | 5/5 | none |
| 5 | 2.0 (2-2) | inter-female-45plus-rural, single-gender-female | 3.8 (1-8) | gen-age-45plus-credit_score-high, gen-age-45plus-employment_years-high, gen-age-45plus-employment_years-mid, gen-age-45plus-income-low, gen-age-45plus-income-mid, gen-age-45plus-loan_amount-low, gen-age-45plus-name_group-n1, gen-age-45plus-pincode_group-p1, gen-gender-female-age-45plus-urban_rural-rural-name_group-n2, gen-gender-female-employment_years-high, gen-gender-female-loan_amount-low | 5/5 | none |
| 6 | 0.0 (0-0) | none | 0.0 (0-0) | none | 5/5 | none |
| 7 | 0.0 (0-0) | none | 0.0 (0-0) | none | 5/5 | none |

## Fairlearn comparison (same data)

Fairlearn is fitted on **4,000 synthetic applicants, seed 42**, scored by every model over the same HTTP sandbox. DP = maximum approval-rate gap; EO = larger of the TPR/FPR gaps against the generator's hidden repayment label. These are observational gaps, not counterfactual findings, and lower is not automatically fair.

| Model | Max DP gap (attribute) | DP gender | DP age | EO gender | EO age | FairLens kept (2%) |
|---|---|---|---|---|---|---|
| 8 | 0.3245 (age_band) | 0.0609 | 0.3245 | 0.054 | 0.4099 | 1.0 |
| 9 | 0.3905 (pincode_group) | 0.2094 | 0.1109 | 0.222 | 0.1199 | 8.2 |
| 10 | 0.2230 (name_group) | 0.0611 | 0.1731 | 0.0499 | 0.2078 | 9.6 |
| 11 | 0.3475 (pincode_group) | 0.0339 | 0.1162 | 0.0162 | 0.1109 | 1.0 |
| 12 | 0.1417 (pincode_group) | 0.0718 | 0.1134 | 0.0583 | 0.1187 | 1.6 |
| 13 | 0.4959 (age_band) | 0.055 | 0.4959 | 0.0519 | 0.6171 | 3.6 |
| 14 | 0.1834 (pincode_group) | 0.099 | 0.1091 | 0.0975 | 0.1082 | 0.0 |
| 15 | 0.1564 (age_band) | 0.0566 | 0.1564 | 0.0548 | 0.1572 | 0.0 |

Models 14 and 15 are the useful contrast: the observational gaps are real, but the group twins never move the decision (Model 14 moves on loan amount, Model 15 has no group term at all), so the counterfactual audit keeps nothing. A Fairlearn-only review cannot tell those cases apart from a planted group penalty.

## Cells, candidates, confirmation, and MDE

- Every suite B audit examined 110 discovery cells (5 main effects, 89 depth-1 contexts, 16 deep-panel cells), with Holm applied to all 110.
- Discovery pairs, confirmation pairs, candidates, and confirmed cells are in `suite_b.csv`; confirmation uses 400 fresh pairs per candidate and at most 16 candidates.
- MDE is the pre-registered planning approximation with power 0.80 and assumed discordance 0.25; it is not a post-hoc power claim.

## Honest limitations

- Synthetic applicants and synthetic names/pincodes only; this is not evidence about a real lender or real Indian populations.
- The merge rule can prefer a materially stronger context over the pre-registered main effect. It did so in 23 kept finding(s); for example model 8 seed 1 kept `gen-age-45plus-credit_score-high` rather than the bare main effect. The choice is reported, not retuned.
- The merge rule only folds a kept subgroup into a kept subgroup that contains it. Sibling contexts beneath the same main effect are not folded together, so model 9 seeds 2, 3, 4, 5; model 10 seeds 1, 2, 3, 4, 5; model 12 seeds 1, 2; model 13 seed 2 kept more than one finding. The extra cells name the same treatment level in different contexts, not a new treatment; they are why the pre-registered "exactly one kept finding" criterion fails for those seeds.
- Model 11's planted `loan_amount=high` context is not in any kept finding; the kept cell was `gen-pincode_group-p2-income-high` on every seed. Discovery ranked the high-income context above the pre-registered high-loan context and the merge kept that one. This is reported as a miss, not retuned.
- Model 14's pre-registered criterion "at least one rejected candidate cites loan amount" is reported as a **miss**. Model 14 has no group term, so no cell reaches discovery and the Skeptic never sees a candidate; the legitimate-feature explanation is only visible in the observational gaps and the loan-amount context cells. This is a gap in the pre-registration, not a reason to add a post-hoc check.
- Suite A's new-protocol pass checks are semantic re-implementations of the frozen expectations; the frozen `expectation_check` is unchanged and its old-protocol rows remain the recorded suite A result.
- A few batches report very long wall-clock times (1368-6523s) with nearly identical values across the four concurrent workers, which is host suspension and scheduling time rather than audit compute. Probe counts, seeds, and statistics are unaffected, and runtime is not a benchmark.

## Artifacts

- `suite_b.csv` - every audit row (suite, model, seed, materiality).
- `suite_b_fairlearn.csv` - Fairlearn DP/EO for models 8-15.
- `suite_b.md` - this file.
