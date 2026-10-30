# FairLens India — five-minute talk

Ten slides. Each slide has the one sentence to say and the artifact on screen.
The demo script is in [demo_script.md](demo_script.md); this outline is for the
spoken argument around it.

---

## Slide 1 — Title (15 s)

**FairLens India — auditing a model you are not allowed to read.**

> A lender refuses to share its model, its training data, or its labels. We still
> have to tell a regulator whether its decisions treat people differently.

Artifact: the dashboard header.

---

## Slide 2 — The gap in conventional fairness (30 s)

- Fairlearn, Aequitas, and friends need the model, the features, or the labels.
- A black-box endpoint gives you one thing: a score for an applicant.
- Observational gaps alone cannot separate **disparate treatment** from a
  legitimate factor such as income.

Artifact: `eval/results/fairlearn.md` — Model 2 has a 0.6605 demographic-parity
gap; Model 7 has 0.1501. Both look "bad". Only Model 2 actually changes its
decision when a twin changes only gender.

> A gap is a question. It is not a finding.

---

## Slide 3 — What FairLens does (30 s)

Five stages, each visible on screen:

1. **Plan** — frozen scope from `config.yaml`.
2. **Probe** — HTTP counterfactual twins that change exactly one signal.
3. **Challenge** — a rule-based Skeptic tries to falsify every candidate.
4. **Translate** — per-10,000 people and a fairness/accuracy trade-off curve.
5. **Sign** — a named human approves; a hash chain makes the record
   tamper-evident.

> The LLM writes prose. It never computes a number.

Artifact: pipeline strip and live log during a Model 2 audit.

---

## Slide 4 — Twin probing is the evidence (45 s)

For each single attribute, 2,000 natural pairs; for each intersectional cell,
500 pairs. A twin holds income, credit, employment, age, and location fixed and
changes only gender, pincode group, or name group.

- b = original approved, twin rejected → harm to the target group
- Exact two-sided McNemar test on the discordant pairs (`scipy.stats.binomtest`)
- Seeded percentile bootstrap 95% CI
- Holm correction within each family

Artifact: Model 2 gender finding, +65.3% net flip, CI, p-value, pair count.

> We are measuring the model's own inconsistency, not a correlation in the data.

---

## Slide 5 — The Skeptic is the product (45 s)

Six rules, no LLM:

1. minimum sample size
2. Holm-adjusted significance
3. materiality (2% net flip)
4. direction / asymmetric noise
5. income-matched persistence
6. confounding — an observational gap with no counterfactual effect

Model 7 is the proof: every candidate is rejected because income-only scoring
never flips a twin. Model 2's pincode and name candidates are rejected as
confounded.

Artifact: findings board with **6 kept / 2 rejected** on Model 2, then Model 7's
all-rejected board.

> A fairness tool that only says yes is a false-alarm generator.

---

## Slide 6 — From coefficient to people (30 s)

`max(net flip rate, 0) × 10,000`, with the CI converted the same way. No hidden
multiplier.

Model 2: ~6,535 people per 10,000 in the affected group; the top female
intersectional cell reaches ~7,200 per 10,000.

Artifact: impact counter and intersectional heatmap.

---

## Slide 7 — Mitigation has a price (30 s)

Group-wise score offsets, same approval threshold, fairness gap vs accuracy
against a hidden repayment label. The user sets an accuracy-loss budget; the
recommendation is the smallest gap inside it.

Model 2 at a 2% budget: offset +80, gap 4.58%, accuracy change −1.30%.

> Accuracy improved on this synthetic sample. That is not a promise about a real
> lender; the label is hidden in a real audit, so this is an offline what-if.

Artifact: mitigation chart (one shared percentage-point axis) and slider.

---

## Slide 8 — Human gate and tamper evidence (45 s)

- No Audit Record without a non-empty approver name.
- `record_hash = sha256(prev_hash + canonical_json(payload))`, 64-zero genesis.
- Verification recomputes every row and reports the **first broken record**.
- The demo deliberately edits a row: the chain goes red.

> Tamper-evident, not authorship-proof. Anyone who can rewrite every row can
> recompute the chain; signing is future work. The UI says so.

Artifact: Audit Records tab, `CHAIN VERIFIED`, then `CHAIN BROKEN` / `HASH
MISMATCH`.

---

## Slide 9 — Evidence, including the miss (45 s)

- 7 models × 5 seeds = 35 pre-registered audits; 70 more at 1% and 3%.
- False alarms before → after the Skeptic on the clean models (1, 6, 7).
- Number-check pass rate on every narrative.
- **Model 5 miss:** we predicted the single-attribute gender effect would be
  ~0.012 and immaterial; it was kept at 0.0265. The arithmetic was wrong
  (male-origin twins are ~4% in the hotspot, not 2%). We did not retune the
  threshold. See D-009.

Artifact: `eval/results/summary.md` and the Model 5 card.

> We report the prediction we got wrong. That is the point of pre-registration.

---

## Slide 10 — Limits and close (30 s)

- Synthetic data; not evidence about a real lender or real Indian populations.
- Twins are approximations; a null result is not proof of fairness.
- The Skeptic is rule-based, not omniscient.
- The Audit Record is tamper-evident, not signed.

> FairLens is not a fairness score. It is an audit trail: twin evidence, a
> Skeptic that tries to falsify it, human impact, a human decision, and a
> tamper-evident record.

Artifact: the full report and Audit Record chain.

---

## Numbers to have ready

| Claim | Value |
|---|---|
| Models / seeds | 7 / 5 |
| Single-attribute pairs | 2,000 per attribute |
| Intersectional pairs | 500 per cell |
| Observational sample | 4,000 applicants |
| Materiality | 2% net flip (sensitivity 1% / 3%) |
| Alpha | 0.05, Holm within family |
| Model 2 gender net flip (seed 42) | 0.6535 |
| Model 2 impact (seed 42) | ~6,535 per 10,000 |
| Model 2 mitigation at 2% budget | offset +80, gap 4.58%, Δaccuracy −1.30% |
| Model 5 hotspot (seed 42) | 0.6320, ~6,320 per 10,000 |
| Model 5 known miss | single gender 0.0265, kept |
| Suite B planted models / clean control | 7 / 1 (Models 8–14 / 15) |
| Suite B expectations met, protocol 1 → 2 | 18/40 → 24/40 |
| Suite B kept per audit, protocol 1 → 2 | 3.1 → 0.9 (range 0–14 → 0–3) |
| Suite B false alarms after Skeptic, protocol 1 → 2 | 125 → 38 |
| Suite B planted treatment named | 5 of 7 (Models 8, 9, 10, 12, 13) |
| Suite B clean control 15 | 0 kept, 0 false alarms, 5/5 met in both protocols |
| Demo runtime | 67.9 s / 75.6 s for Models 2, 7, 5 |

Use the exact values in `eval/results/summary.md` if they differ from this table;
the summary is generated from the final run.
