# R5.1 sibling-context merge - protocol 2

Generated: 2026-10-29T19:48:52+00:00

This is the second protocol, run after the sibling-context rule was pre-registered in `expected_findings.md` (R5.1). It was designed after protocol 1 was reported, because Models 9/10 kept 9-11 sibling cells for one planted effect. No threshold, penalty, bin, seed, or panel cell changed. Protocol 1 (`suite_b.csv`, `suite_b.md`) is read for comparison and never rewritten.

The rule: two kept generalized findings with the same treatment and level, non-nested contexts, and confirmation net flips that a two-sided z-test cannot separate (`p >= alpha`, variance `(b+c)/n^2`) are siblings. Sibling and nested links are closed transitively; the cluster reports the shared treatment and the narrowest common context (the intersection). A specific member stays primary only when it is at least `materiality` stronger. Evidence is the primary cell's own confirmation sample, not a pooled estimate. This is a failure-to-reject rule, not an equivalence test.

## Protocol 1 vs protocol 2 (suite B, 5 seeds, 2%)

| Model | P1 kept mean (range) | P1 PASS | P2 kept mean (range) | P2 PASS | P1 false alarms before -> after | P2 false alarms before -> after |
|---|---|---|---|---|---|---|
| 8 | 1.0 (1-1) | 5/5 | 1.0 (1-1) | 5/5 | 135 -> 5 | 135 -> 5 |
| 9 | 8.2 (1-11) | 1/5 | 1.4 (1-2) | 3/5 | 259 -> 41 | 259 -> 7 |
| 10 | 9.6 (9-10) | 0/5 | 2.2 (1-3) | 1/5 | 244 -> 48 | 244 -> 11 |
| 11 | 1.0 (1-1) | 0/5 | 1.0 (1-1) | 0/5 | 120 -> 5 | 120 -> 5 |
| 12 | 1.6 (1-3) | 3/5 | 1.0 (1-1) | 5/5 | 42 -> 8 | 42 -> 5 |
| 13 | 3.6 (1-14) | 4/5 | 1.0 (1-1) | 5/5 | 140 -> 18 | 140 -> 5 |
| 14 | 0.0 (0-0) | 0/5 | 0.0 (0-0) | 0/5 | 0 -> 0 | 0 -> 0 |
| 15 | 0.0 (0-0) | 5/5 | 0.0 (0-0) | 5/5 | 0 -> 0 | 0 -> 0 |
| **All** | 3.1 (0-14) | 18/40 | 0.9 (0-3) | 24/40 | 940 -> 125 | 940 -> 38 |

## Per-seed detail (protocol 2)

| Model | Seed | Kept | Kept ids | Expectation | Misses | Notes | Runtime |
|---|---|---|---|---|---|---|---|
| 8 | 1 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 108.1s |
| 8 | 2 | 1 | gen-age-45plus-employment_years-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-employment_years-high context={'employment_years': 'high'} | 106.3s |
| 8 | 3 | 1 | gen-age-45plus-income-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-income-high context={'income': 'high'} | 107.4s |
| 8 | 4 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 106.5s |
| 8 | 5 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 96.4s |
| 9 | 1 | 1 | gen-pincode_group-p2-gender-female-loan_amount-high | PASS | none | none | 99.2s |
| 9 | 2 | 1 | gen-pincode_group-p2-gender-female-loan_amount-high | PASS | none | none | 101.4s |
| 9 | 3 | 2 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-employment_years-high | MISS | expected exactly one kept finding, got 2 | none | 99.3s |
| 9 | 4 | 1 | gen-pincode_group-p2-gender-female-loan_amount-high | PASS | none | none | 104.4s |
| 9 | 5 | 2 | gen-pincode_group-p2-gender-female-loan_amount-high, gen-pincode_group-p2-credit_score-high | MISS | expected exactly one kept finding, got 2 | none | 99.2s |
| 10 | 1 | 3 | gen-name_group-n2-age-45plus, gen-name_group-n2-employment_years-high, gen-name_group-n2-credit_score-high | MISS | expected exactly one kept finding, got 3 | none | 101.1s |
| 10 | 2 | 1 | gen-name_group-n2-age-45plus | PASS | none | none | 99.9s |
| 10 | 3 | 2 | gen-name_group-n2-gender-female-age-45plus, gen-name_group-n2-employment_years-high | MISS | expected exactly one kept finding, got 2 | none | 96.2s |
| 10 | 4 | 3 | gen-name_group-n2-age-45plus, gen-name_group-n2-employment_years-high, gen-name_group-n2-credit_score-high | MISS | expected exactly one kept finding, got 3 | none | 98.0s |
| 10 | 5 | 2 | gen-name_group-n2-age-45plus, gen-name_group-n2-employment_years-high | MISS | expected exactly one kept finding, got 2 | none | 99.8s |
| 11 | 1 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 95.3s |
| 11 | 2 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 90.8s |
| 11 | 3 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 92.2s |
| 11 | 4 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 95.0s |
| 11 | 5 | 1 | gen-pincode_group-p2-income-high | MISS | kept pincode P2 finding in the high-loan context is missing | none | 93.7s |
| 12 | 1 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 88.5s |
| 12 | 2 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 84.4s |
| 12 | 3 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 82.5s |
| 12 | 4 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 84.1s |
| 12 | 5 | 1 | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | PASS | none | none | 89.5s |
| 13 | 1 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 104.3s |
| 13 | 2 | 1 | gen-age-45plus-credit_score-high | PASS | none | none | 104.4s |
| 13 | 3 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 102.1s |
| 13 | 4 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 81.2s |
| 13 | 5 | 1 | gen-age-45plus-credit_score-high | PASS | none | kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'} | 81.4s |
| 14 | 1 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 67.0s |
| 14 | 2 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 64.8s |
| 14 | 3 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 64.0s |
| 14 | 4 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 67.6s |
| 14 | 5 | 0 | none | MISS | no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic) | none | 65.5s |
| 15 | 1 | 0 | none | PASS | none | none | 74.2s |
| 15 | 2 | 0 | none | PASS | none | none | 80.8s |
| 15 | 3 | 0 | none | PASS | none | none | 87.8s |
| 15 | 4 | 0 | none | PASS | none | none | 89.0s |
| 15 | 5 | 0 | none | PASS | none | none | 82.6s |

## Misses and notes across all seeds

- **MISS x5**: kept pincode P2 finding in the high-loan context is missing
- **MISS x5**: no rejected candidate cites loan amount (the pre-registered explanation path is unreachable when no candidate reaches the Skeptic)
- **MISS x4**: expected exactly one kept finding, got 2
- **MISS x2**: expected exactly one kept finding, got 3
- Note x7: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-credit_score-high context={'credit_score': 'high'}
- Note x1: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-employment_years-high context={'employment_years': 'high'}
- Note x1: kept age finding is context-specific, not the pre-registered main effect: gen-age-45plus-income-high context={'income': 'high'}

## Clean controls (Models 14 and 15)

| Model | P1 kept (5 seeds) | P1 false alarms before -> after | P2 kept (5 seeds) | P2 false alarms before -> after |
|---|---|---|---|---|
| 14 | 0 | 0 -> 0 | 0 | 0 -> 0 |
| 15 | 0 | 0 -> 0 | 0 | 0 -> 0 |

## Materiality sensitivity (in-memory override, same seeds)

| Model | P1 kept 1% | P2 kept 1% | P1 kept 2% | P2 kept 2% | P1 kept 3% | P2 kept 3% | P2 PASS 1% | P2 PASS 2% | P2 PASS 3% |
|---|---|---|---|---|---|---|---|---|---|
| 8 | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 5/5 | 5/5 | 5/5 |
| 9 | 8.2 (1-11) | 1.4 (1-2) | 8.2 (1-11) | 1.4 (1-2) | 8.2 (1-11) | 1.4 (1-2) | 3/5 | 3/5 | 3/5 |
| 10 | 9.6 (9-10) | 2.2 (1-3) | 9.6 (9-10) | 2.2 (1-3) | 9.6 (9-10) | 2.2 (1-3) | 1/5 | 1/5 | 1/5 |
| 11 | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 0/5 | 0/5 | 0/5 |
| 12 | 1.6 (1-3) | 1.0 (1-1) | 1.6 (1-3) | 1.0 (1-1) | 1.6 (1-3) | 1.0 (1-1) | 5/5 | 5/5 | 5/5 |
| 13 | 3.6 (1-14) | 1.0 (1-1) | 3.6 (1-14) | 1.0 (1-1) | 3.6 (1-14) | 1.0 (1-1) | 5/5 | 5/5 | 5/5 |
| 14 | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0/5 | 0/5 | 0/5 |
| 15 | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 5/5 | 5/5 | 5/5 |

The pre-registered materiality is 2%; 1% and 3% are sensitivity runs and are never used to pick the best result.

## Suite A rerun (no-regression comparison)

Old-protocol facts come from `eval/results/results.csv` and stay frozen. P1 and P2 are both semantic re-checks of the same frozen expectations.

| Model | Old kept mean (range) | P1 kept mean (range) | P2 kept mean (range) | P1 PASS | P2 PASS | P2 misses |
|---|---|---|---|---|---|---|
| 1 | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 5/5 | 5/5 | none |
| 2 | 6.0 (6-6) | 1.0 (1-1) | 1.0 (1-1) | 5/5 | 5/5 | none |
| 3 | 1.0 (1-1) | 1.0 (1-1) | 1.0 (1-1) | 5/5 | 5/5 | none |
| 4 | 1.0 (1-1) | 3.4 (1-13) | 1.0 (1-1) | 5/5 | 5/5 | none |
| 5 | 2.0 (2-2) | 3.8 (1-8) | 1.4 (1-2) | 5/5 | 5/5 | none |
| 6 | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 5/5 | 5/5 | none |
| 7 | 0.0 (0-0) | 0.0 (0-0) | 0.0 (0-0) | 5/5 | 5/5 | none |

## Runtimes

Runtimes are per-audit wall-clock times inside a worker, not a single-user benchmark and not a sum across workers.

- 155 audits: median **77.8s**, range 55.4-108.1s.
- Suite A: median 77.1s (68.3-95.0s, n=35).
- Suite B: median 78.2s (55.4-108.1s, n=120).
- No audit exceeded 600s, so no host-suspension outliers were excluded.
- Fairlearn baseline re-run on the same seeded sample (4,000 applicants, seed 42); the inputs are identical to protocol 1, so the observational gaps are unchanged.

## Honest limitations

- The sibling rule was designed after protocol-1 results, so it is a pre-registered second protocol, not a blind first look. It is reported side by side and protocol 1 is not replaced.
- "Indistinguishable" is a failure to reject equality at alpha, not an equivalence test; it does not prove the sibling effects are equal.
- A re-described primary keeps its own confirmation sample. The reported evidence is not pooled across sibling cells, and the reason string says so.
- A materially stronger specific member still wins, as in protocol 1; the cluster then names that specific context rather than the common one.
- Suite A's new-protocol checks remain semantic re-implementations; the frozen old-protocol rows are unchanged.
- Model 14's pre-registered "at least one rejected candidate cites loan amount" remains a **miss**: no group candidate reaches the Skeptic, so that explanation path is unreachable. This is a gap in the pre-registration, not a post-hoc check.
- Model 11 remains a **miss**: the planted `loan_amount=high` context is not in any kept finding; the kept cell was `gen-pincode_group-p2-income-high` on every seed. Income and loan amount are correlated in the generator, so discovery ranks the high-income context above the pre-registered high-loan context. Not retuned.

## Artifacts

- `suite_b_r51.csv` - every protocol-2 audit row (suite, model, seed, materiality).
- `suite_b_r51_fairlearn.csv` - Fairlearn DP/EO for models 8-15 on the same seeded sample.
- `suite_b_r51.md` - this file.
- `suite_b.csv`, `suite_b_fairlearn.csv`, `suite_b.md` - protocol 1, untouched.
