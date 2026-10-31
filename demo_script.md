# FairLens India — demo script

Audience: hackathon judges. Goal: show that the auditor is genuinely black-box,
that it challenges itself, that a human is required, and that the Audit Record
tamper check is real.

**Default: 3-minute cut in the React Probe Arena.** If the organizers confirm
5 minutes, add the two marked segments near the end. Use one UI for the live
audit: React. Streamlit stays available as a fallback, not as a second stage.

## Before the room (5 minutes)

Start all services before you walk up. Three terminals, plus one optional:

```powershell
# 1. black-box sandbox
.\.venv\Scripts\python -m sandbox.serve --host 127.0.0.1 --port 8010

# 2. audit API (also serves the Evidence page data)
.\.venv\Scripts\python -m api.serve

# 3. React Probe Arena
cd web; npm run dev

# 4. real-data targets, only if a judge asks (not needed for the 3-minute cut)
.\.venv\Scripts\python -m targets.real.serve
```

Then:

- Open <http://127.0.0.1:5173> and leave it on the model library.
- Open <http://127.0.0.1:5173/evidence> in tab 2.
- Open a suite B recording (Model 9 or 12) in tab 3.
- Reset the Audit Record database so certificate #0 is issued live:

```powershell
.\.venv\Scripts\python -m trust.reset_demo_data
```

- Laptop on AC, sleep and notifications off, browser zoom 110–125%, other tabs
  closed.
- Put the backup video on the desktop, ready to play.
- Check `http://127.0.0.1:8010/health`, `http://127.0.0.1:8020/targets`, and the
  Evidence page once.

**Streamlit fallback.** If React fails on stage, the sandbox and API are already
running. Start only the UI:

```powershell
.\.venv\Scripts\python -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Do not start `run.ps1` while the standalone sandbox owns port 8010.

## 0:00 — Start Model 2, then the problem (20 s)

Press **Start audit** on **Model 2** first, then say:

> A lender says "our model is fair, but we can't show you the model." A
> conventional fairness audit needs the model, the training data, or the labels.
> The audit itself never needs the model's data or labels — only an HTTP endpoint.

Point at the model library: 15 validation models, 2 real datasets, α = 0.05
frozen before the first audit.

If a judge asks whether this works on a real lender:

> Any HTTP endpoint with authorization is supported and verified through the
> sandbox and real-data targets. We are not claiming a real bank audit.

## 0:20 — Model 2 live (60 s)

1. The audit has been running since 0:00. It lands around **0:50** on this laptop
   (about 50 s measured). Model 2 uses the direct sandbox path, search off; the
   generalized suite B models are opened from the committed replays.
2. While it runs, point at the twin stream, agent lanes, and evidence meter. Say:

> The planner fixes the scope. The prober sends two applicants who differ only
> in gender — same income, credit, employment, pincode, age. The statistician
> uses an exact McNemar test on the discordant pairs. The Skeptic then tries to
> kill the finding: sample size, Holm significance, materiality, direction, and
> an income-matched re-test.

3. When the report lands, point at **6 kept / 2 rejected**. The gender finding is
   +65.3% net flip toward women. The pincode and name candidates are rejected as
   confounded: their observational gaps do not survive the twin test.
4. Point at **People per 10,000**: ~7,200 in the top intersectional subgroup
   (female, 45+, urban), with the 95% range. Say the formula out loud:
   `max(net flip, 0) × 10,000`, no hidden multiplier. The single-attribute
   gender finding is ~6,535.
5. Point at the **narrative** and `number check passed`, `source: template`. Say
   the LLM only rewrites computed JSON; every number is checked, and a failed
   draft falls back to the deterministic template.

## 1:20 — Model 7: a gap is not a finding (30 s)

1. Keep the Model 2 report in its tab. Open the **Model 7** recording from
   **Watch a recorded audit** and press **Skip to report**. It is a committed
   replay; no sandbox call is made.
2. Female, P2, and N2 approval rates look worse. Say:

> A dashboard would flag this. Model 7 approves on income only. The generator
> gives those groups lower income, so the gap is explained by a legitimate
> factor. The twins never flip, and the Skeptic rejects every candidate.

3. Point at the rejected badges and the empty impact state. No per-10,000 claim
   is invented.

## 1:50 — Human gate + tamper (30 s)

1. Return to the Model 2 report. Press **Approve & issue Audit Record** with the
   approver field empty. It refuses. Say:

> No Audit Record without a named human. The auditor does not sign for you.

2. Type `Dr A. Rao`, press **Approve & issue Audit Record**.
3. Click **audit records**. Press **Verify chain**. Tick the confirmation, press
   **Tamper with newest record**, then **Verify chain**. Show `CHAIN BROKEN` and
   the first broken record.

> This proves tamper-evidence, not authorship. Anyone who can rewrite every row
> can recompute the chain. Signing is future work — and the UI says so. An Audit
> Record documents what was measured; it is not a certification of fairness,
> lawfulness, or compliance.

## 2:20 — Close (20 s)

> FairLens is not a fairness score. It is an audit trail: twin evidence, a
> Skeptic that tries to falsify it, human impact, a human decision, and a
> tamper-evident record. The LLM never touches the numbers.

That is 2:40, with 20 seconds of buffer.

## 5-minute add-ons (only if the organizers confirm 5 minutes)

Insert these before the close.

### +45 s — Model 5: where harm hides

1. Open the **Model 5** recording and press **Skip to report**.
2. Show the single-attribute gender card: net 0.0265, kept because it is above
   the 0.02 materiality threshold. Say:

> This is our known miss. We predicted ~0.012 and "immaterial" before the first
> audit. The prediction arithmetic was wrong: male-origin twins are 4% in the
> hotspot, not 2%. We did not retune the threshold. It is in the decision log.

3. Show the hotspot card: female + 45+ + rural, net ~0.632, impact ~6,320 per
   10,000. Say the intersectional scanner samples 500 pairs per cell so a rare
   2% subgroup still has power.

### +45 s — Evidence: protocol 1 next to protocol 2

1. Switch to the preloaded **/evidence** tab.
2. Point at **P1 18/40 met → P2 24/40 met**, **3.1 → 0.9** kept findings per
   audit, and **125 → 38** false alarms after the Skeptic.
3. Say:

> Protocol 1 over-reported one effect as up to 11 findings. We added a
> sibling-merge rule, pre-registered before its own re-run, and reported both
> protocols side by side. Detection rose from 18 to 24 of 40, with zero new
> false alarms on the clean controls.

4. Then say the misses plainly:

> The rule collapsed 8–10 findings into 1–3 per audit. It did not always reach
> exactly one. Model 11 keeps the wrong context in all five seeds. Model 14's
> explanation path is unreachable. Models 9 and 10 sometimes keep two or three
> distinguishable cells. The clean control stayed at zero.

## If something breaks

- **React cannot reach the API**: check `http://127.0.0.1:8020/targets`. If it
  is down, restart `python -m api.serve`; if it stays down, use the Streamlit
  fallback.
- **Audit cannot run**: check the sandbox is on
  `http://127.0.0.1:8010/health`. The UI shows a clean error and does not crash.
- **Port 8010 busy**: stop the process holding 8010 and restart the sandbox.
  Do not move it to 8020; the audit API uses that port.
- **Audit is slow**: open a committed recording instead. Model 2 on the direct
  path measured about 50 s on the demo laptop; a generalized suite B audit is
  about 78 s. Start Model 2 before the problem line.
- **Audit Records tab is red before the demo**: run
  `python -m trust.reset_demo_data`. The database is local and disposable.
- **No Anthropic key**: the template narrative is expected and passes the number
  check. Do not apologise for it; it is the deterministic fallback.
- **Mitigation slider**: the live React report does not include it. Show it in
  the backup video or the Streamlit fallback only if a judge asks, and say "the
  mitigation curve is in the fallback UI and the video."

## If a judge asks about the validation suite

> Protocol 1 over-reported one effect as up to 11 findings. We added a
> sibling-merge rule, pre-registered before its own re-run, and reported both
> protocols side by side. Detection rose from 18 to 24 of 40, with zero new
> false alarms on the clean controls.

Then say the misses plainly:

- The rule collapsed 8–10 findings into 1–3 per audit. It did not always reach
  exactly one.
- Model 11 keeps the wrong context in all five seeds. Model 14's explanation
  path is unreachable. Models 9 and 10 sometimes keep two or three
  distinguishable cells.
- Model 15, the clean control, stayed at zero kept findings and zero false
  alarms in both protocols.
- It is a failure-to-reject refinement, not an equivalence test, and not a clean
  first-pass result.

## Do not say

- "The model is biased" — say "the model's decisions show disparate treatment
  under this test."
- "The Audit Record proves who approved it" — say "tamper-evident, not
  authorship."
- "FairLens proves fairness" — say "a null result is not proof of fairness."
- "Protocol 2 fixed it" — say "a pre-registered refinement; it reduced
  over-reporting and still has disclosed misses."
- "We detected all the planted bias" — say "we found the planted treatment in 5
  of the 7 planted behaviours."
- "Eight more models" — say "eight additional validation models (suite B,
  including one clean control)."
- "We audited a real bank" — say "the adapter path is verified through the
  sandbox and two public UCI datasets."
- "The audit needs the model's data or labels" — say "the audit itself never
  needs the model's data or labels."
