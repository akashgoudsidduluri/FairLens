# FairLens India evaluation summary

Generated: 2026-10-27T15:52:02+00:00

Pre-registered run: **7 models x 5 seeds (35 audits)**, seed 42-style config unchanged, alpha 0.05, materiality 2%, Holm correction, 2,000 single-attribute twin pairs, 500 pairs per intersectional cell. No threshold, penalty, or population parameter was tuned after the first audit.

The audit used a real HTTP sandbox. Each model/seed pair is an independent audit. Runtimes below are wall-clock times measured inside the parallel evaluation workers, so they are indicative, not a single-user demo benchmark. The serial demo benchmark is in `phase5_demo_smoke.md`.

## Main results

| Model | Runs | Expectation PASS | Kept mean (range) | False alarms before -> after | Number check | Mean runtime | Misses |
|---|---|---|---|---|---|---|---|
| 1 | 5 | 5/5 | 0.0 (0-0) | 0 -> 0 | 5/5 | 22.0s | none |
| 2 | 5 | 5/5 | 6.0 (6-6) | n/a | 5/5 | 30.7s | none |
| 3 | 5 | 5/5 | 1.0 (1-1) | n/a | 5/5 | 23.9s | none |
| 4 | 5 | 5/5 | 1.0 (1-1) | n/a | 5/5 | 23.4s | none |
| 5 | 5 | 0/5 | 2.0 (2-2) | n/a | 5/5 | 26.3s | single-attribute gender was kept (expected immaterial) |
| 6 | 5 | 5/5 | 0.0 (0-0) | 0 -> 0 | 5/5 | 27.9s | none |
| 7 | 5 | 5/5 | 0.0 (0-0) | 0 -> 0 | 5/5 | 413.6s | none |

- Completed audits: **35**; errors: **0**.
- Narrative number-check pass rate: **35/35 (100.0%)**.
- Total audit compute time: **2839.4s** (mean 81.1s).

## False alarms and misses

A false alarm before the Skeptic is a candidate that is Holm-significant and has net flip >= materiality in a model with no planted penalty (Models 1, 6, 7). After the Skeptic means kept.

- Model 1: before **0**, after **0** across 5 seeds.
- Model 6: before **0**, after **0** across 5 seeds.
- Model 7: before **0**, after **0** across 5 seeds.

### Expectations that did not pass

- single-attribute gender was kept (expected immaterial)
- Model 5's single-attribute gender finding is the known D-009 pre-registration miss. The hotspot is 4% of male-origin pairs, not 2% of the whole population, so the diluted net rate is about 0.025 rather than 0.012. The materiality threshold was not changed.

## Mitigation (seed 42, default 2% accuracy-loss budget)

| Model | Segment | Offset | Fairness gap | Accuracy loss | Sampling |
|---|---|---|---|---|---|
| 2 | female · 45+ · urban | +80 | 4.58% | -1.30% | natural population |
| 3 | P2 | +140 | 8.98% | -3.28% | natural population |
| 4 | N2 | +120 | 7.21% | -7.35% | natural population |
| 5 | female · 45+ · rural | +240 | 5.45% | -6.13% | stratified (rare segment): 1000 segment + natural comparison |

Negative accuracy loss means the offset improved agreement with the hidden repayment label on the mitigation sample. It is not a causal claim about real lending.

## Certificate test

- Empty approver rejected: **True**
- Chain valid before tamper: **True**
- Chain valid after tamper: **False** (first broken record: 0)
- Certificate hash: `f8204ddb5609c8644bf83cfa149eec2b243507522b339346a1505f59af699345`

The hash chain proves tamper-evidence, not authorship. A signer with write access could recompute the whole chain; digital signatures are future work.

## Materiality sensitivity

The pre-registered 2% run is reported above. The two sensitivity runs copy the config in memory to 1% and 3%; no file is edited. They use the same seeds and statistics.

| Model | Kept mean at 1% | Kept mean at 2% | Kept mean at 3% |
|---|---|---|---|
| 1 | 0.0 | 0.0 | 0.0 |
| 2 | 6.0 | 6.0 | 6.0 |
| 3 | 1.0 | 1.0 | 1.0 |
| 4 | 1.0 | 1.0 | 1.0 |
| 5 | 2.0 | 2.0 | 1.0 |
| 6 | 0.0 | 0.0 | 0.0 |
| 7 | 0.0 | 0.0 | 0.0 |

Model 5 is the borderline case. Its single-attribute gender finding is kept in the 2% pre-registered run and moves with the threshold, while the intersectional hotspot stays dominant. The raw per-seed rows are in `materiality_sensitivity.csv`.

## Artifacts

- `results.csv` - every main audit (35 rows).
- `materiality_sensitivity.csv` - 1% and 3% audits (70 rows).
- `mitigation_curves.csv` - full offset sweeps at seed 42.
- `kept_findings_by_model.png`, `primary_net_flip_by_seed.png`, `materiality_sensitivity.png`, `mitigation_curves.png`.
- `fairlearn.md` / `fairlearn.csv` - observational baseline.
- `phase5_demo_smoke.md` - serial three-model demo and certificate tamper check.

## Honest limitations

- Synthetic applicants and synthetic names/pincodes only; not evidence about a real lender or real Indian populations.
- Twin probing is evidence of disparate treatment, not proof of intent. The Skeptic is rule-based, not omniscient.
- Observational DP/EO gaps can be caused by legitimate income differences; Model 7 demonstrates why a baseline alone is not enough.
- The certificate is tamper-evident, not signed. It does not establish authorship.
- Model 5's single-gender kept finding remains a pre-registration miss; it is reported, not hidden or retuned.
