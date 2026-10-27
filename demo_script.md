# FairLens India — five-minute demo script

Audience: hackathon judges. Goal: show that the auditor is genuinely black-box,
that it challenges itself, that a human is required, and that the certificate
tamper check is real.

## Before the room (2 minutes)

```powershell
.\run.ps1
```

Wait for `FairLens dashboard: http://127.0.0.1:8501`, then open it. Check the
sandbox health badge by running an audit once if you have time. Reset the
certificate database from the **Certificates** tab so the chain starts clean.
Close other browser tabs. Set the browser zoom to 100%.

If the laptop is slow, use **Demo mode** instead of three separate audits: it
runs Models 2 → 7 → 5 and leaves the last report open.

## 0:00 — The problem (30 s)

> A lender says "our model is fair, but we can't show you the model." A
> conventional fairness audit needs the model, the training data, or the labels.
> FairLens assumes none of that. It only gets an HTTP endpoint.

Point at the hero stats: 7 models, 2,000 twins per attribute, α = 0.05 frozen
before the first audit.

## 0:30 — Model 2: find and defend a finding (90 s)

1. Keep **Model 2** and press **Start Audit**.
2. While it runs, point at the pipeline and live log. Say:

> The planner fixes the scope. The prober sends two applicants who differ only
> in gender — same income, credit, employment, pincode, age. The statistician
> uses an exact McNemar test on the discordant pairs. The Skeptic then tries to
> kill the finding: sample size, Holm significance, materiality, direction, and
> an income-matched re-test.

3. When the report lands, point at **6 kept / 2 rejected**. The gender finding is
   +65.3% net flip toward women. The pincode and name candidates are rejected as
   confounded: their observational gaps do not survive the twin test.
4. Point at the **intersectional heatmap**: five female cells are kept.
5. Point at the **impact counter**: ~7,200 people per 10,000 in the top
   intersectional subgroup (female, 45+, urban), with the 95% range. Say the
   formula out loud: `max(net flip, 0) × 10,000`, no hidden multiplier. The
   single-attribute gender finding is ~6,535; the intersectional cell is larger.
6. Move the **mitigation slider** to 2%. The recommended offset is +80: fairness
   gap 4.58%, accuracy loss −1.30% (accuracy improved). Say:

> Accuracy is measured against a hidden repayment label. This is an offline
> what-if, not a deployable policy.

7. Scroll to the **narrative**. Point at `NUMBER CHECK PASSED` and `source:
   template`. Say the LLM only rewrites computed JSON; every number is checked,
   and a failed draft falls back to the deterministic template.

## 2:00 — The human gate (45 s)

1. Press **Approve & issue certificate** without a name. It refuses. Say:

> No certificate without a named human. The auditor does not sign for you.

2. Type `Dr A. Rao`, press **Approve & issue certificate**.
3. Open the **Certificates** tab. Show the chain: genesis, record #0, approver,
   decision, UTC timestamp, `record_hash`, `prev_hash`. Press **Verify chain**.
4. Tick the confirmation and press **Demo: tamper with the newest record**, then
   **Verify chain**. Show `CHAIN BROKEN`, the red record, and `HASH MISMATCH`.

> This proves tamper-evidence, not authorship. Anyone who can rewrite every row
> can recompute the chain. Signing is future work — and the UI says so.

## 2:45 — Model 7: a gap is not a finding (45 s)

1. Back to **Audit**. Choose **Model 7**, **Start Audit** (or open the demo
   result).
2. Female, P2, and N2 approval rates look worse. Say:

> A dashboard would flag this. Model 7 approves on income only. The generator
> gives those groups lower income, so the gap is explained by a legitimate
> factor. The twins never flip, and the Skeptic rejects every candidate.

3. Point at the rejected cards and the empty impact state. No per-10,000 claim is
   invented.

## 3:30 — Model 5: where harm hides (45 s)

1. Choose **Model 5**, **Start Audit** (or open the demo result).
2. Show the single-attribute gender card: net 0.0265, kept because it is above
   the 0.02 materiality threshold. Say:

> This is our known miss. We predicted ~0.012 and "immaterial" before the first
> audit. The prediction arithmetic was wrong: male-origin twins are 4% in the
> hotspot, not 2%. We did not retune the threshold. It is in the decision log.

3. Show the hotspot card: female + 45+ + rural, net ~0.632, impact ~6,320 per
   10,000. Say the intersectional scanner samples 500 pairs per cell so a rare
   2% subgroup still has power.

## 4:15 — Evidence and close (45 s)

1. Show `eval/results/summary.md`: 7 models × 5 seeds, 1% / 3% sensitivity,
   false alarms before/after the Skeptic, every miss, certificate test, number
   check pass rate.
2. Show the Fairlearn comparison: Model 7 has a gender DP gap of 0.1501 and is
   still not flagged, because the gap is confounded; Model 2's DP gap is 0.6605
   and is flagged. Observational metrics alone cannot tell these apart.
3. Close:

> FairLens is not a fairness score. It is an audit trail: twin evidence, a
> Skeptic that tries to falsify it, human impact, a human decision, and a
> tamper-evident record. The LLM never touches the numbers.

## If something breaks

- **Audit cannot run**: check the sandbox is on `http://127.0.0.1:8010/health`.
  The UI shows a clean error and does not crash.
- **Port 8010 busy**: `$env:FAIRLENS_API_PORT=8020; $env:FAIRLENS_UI_PORT=8502;
  .\run.ps1`.
- **Audit is slow**: use **Demo mode**; the recorded headless run was 67.9s for
  all three models (27.7s, 17.5s, 22.6s), and each audit is under the 60s budget.
- **Certificate tab is red before the demo**: press **Reset demo certificate
  database**. The database is local and disposable.
- **No Anthropic key**: the template narrative is expected and passes the number
  check. Do not apologise for it; it is the deterministic fallback.

## Do not say

- "The model is biased" — say "the model's decisions show disparate treatment
  under this test."
- "The certificate proves who approved it" — say "tamper-evident, not
  authorship."
- "FairLens proves fairness" — say "a null result is not proof of fairness."
