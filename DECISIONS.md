# FairLens India — decision log

Decisions are recorded here as they are made. Once an audit has run, audit
thresholds and planted penalties are frozen; later entries may document
implementation fixes but must not tune those values.

## D-001 (Phase 0) Python and dependencies
- Python 3.11 in a local `.venv`; FastAPI + Uvicorn for the sandbox, Streamlit
  for the dashboard, pytest for tests.
- The sandbox and auditor run as separate processes. The auditor talks to the
  sandbox only over HTTP and imports only `schemas.py` and the applicant
  generator.

## D-002 (Phase 0) Pre-registration
- `config.yaml` and `expected_findings.md` were committed before any audit.
- alpha = 0.05, Holm correction, materiality = 0.02 net flip rate, minimum 1,000
  pairs, minimum cell size 200, 2,000 natural pairs per single attribute,
  4,000 observational applicants, 500 pairs per intersectional cell.
- Seeds 1–5 are reserved for evaluation. The demo uses seed 42.

## D-003 (Phase 0) Paired statistics
- b = original approved, twin rejected; c = original rejected, twin approved.
- Net flip rate = (b − c) / n, oriented toward harm to the target group
  (original is from the comparison group, twin is from the target group).
- Exact two-sided McNemar test = two-sided binomial test of b successes in
  b + c trials at p = 0.5. The docstring states this and a test cross-checks it
  against `statsmodels.stats.contingency_tables.mcnemar`.
- 95% CI: **seeded percentile bootstrap** over the paired outcomes
  {harm, benefit, neither}, 4,000 resamples, seed derived from the finding id.
  Chosen because it needs no normal approximation and handles small discordant
  counts; a test checks it is close to the analytic Wald paired-difference CI
  for large samples.
- Holm adjustment is applied within each family: three single-attribute tests,
  then the 12 intersectional cell tests.
- Observational rate CIs use Wilson intervals; the gap CI uses the Newcombe
  hybrid score interval, cross-checked against `statsmodels`.

## D-004 (Phase 0) Target-group orientation
- For each single attribute, the target group is the group with the lowest
  observational approval rate; the comparison group is the highest. Twins flip
  from the comparison group to the target group. This makes positive net flip
  rate mean harm to the disadvantaged group.
- Any negative/contrary counterfactual effect is reported as-is; no flipping of
  signs after the fact.

## D-005 (Phase 0) Model 5 population design
- Female 50%, age 45+ 20%, rural 20%, independent; hotspot share ≈ 2.0%.
- Penalty 240 points in the hotspot. Expected cell net flip ≈ 0.6, so the
  diluted single-attribute gender net flip ≈ 0.02 × 0.6 = 0.012, below the
  0.02 materiality threshold. The intersectional scanner samples 500 pairs per
  cell (12 cells) so the rare cell still has power. Full arithmetic is in
  `expected_findings.md`.
- The pincode table has 12 synthetic pincodes: P1 and P2 each have 3 urban and
  1 rural; P3 has 4 urban. Weighted rural share = 0.5×0.25 + 0.3×0.25 + 0.2×0
  = 0.20.

## D-006 (Phase 0) Model 7 confounding
- Model 7's score is a monotone function of income only. A twin that changes
  gender, pincode, or name while income is fixed therefore gets the identical
  decision, so b = c = 0. Observational gaps arise because the generator gives
  P2, N2, and women lower mean income on purpose.

## D-007 (Phase 0) Honesty rules
- The LLM never computes numbers; it rewrites computed JSON. Number checking
  runs on every narrative and a deterministic template is the fallback.
- Rejected candidates remain in the report. No threshold, penalty, or model is
  changed after seeing audit output.

## D-008 (Phase 1) Demo port 8010
- Port 8000 was already occupied by an unrelated local service on the build
  machine, so the sandbox and dashboard defaults use 8010. This is an
  operational choice, not an audit parameter. `run.sh`, `run.ps1`, the UI
  default, and `config.yaml` agree.

## D-009 (Phase 2) Model 5 expectation miss — reported, not retuned
- First audit (seed 42) found the Model 5 hotspot at net flip 0.632 (kept), as
  expected. It also kept the single-attribute gender finding at net 0.0265,
  above the 0.02 materiality threshold, whereas `expected_findings.md` predicted
  ~0.012 and "immaterial".
- Cause: the pre-registration arithmetic multiplied the hotspot's 2% share of
  the whole population by the 50% female share, but the single-attribute probe
  samples male originals only. Among male-origin pairs, 4% are in the hotspot,
  so the expected diluted rate is 0.04 × 0.63 ≈ 0.025, not 0.012. The
  prediction was wrong, not the threshold.
- No threshold, penalty, population mix, or model was changed after seeing this.
  The miss is carried into Phase 6 and the final checklist. The hotspot remains
  the dominant finding (0.632 vs 0.0265).

## D-010 (Phase 3) Mitigation curve
- Group-wise offset is added to the returned score only for the affected
  segment; the configured approval threshold is re-applied. Fairness gap is the
  absolute difference between segment and comparison approval rates, so
  over-correction is visible (the gap rises again past the optimum).
- Accuracy is agreement with the generator's hidden true_repay on the mitigation
  sample. Recommended point = smallest gap among offsets with accuracy loss
  within the user's budget; ties go to the smaller offset.
- Rare intersectional segments use a stratified sample (1,000 segment + up to
  2,000 natural comparison applicants) so the slider is measurable. The curve
  records that sampling mode.

## D-011 (Phase 3) Certificate trust boundary
- Hash rule is exactly `sha256(prev_hash + canonical_json(payload))`, with a
  64-zero genesis hash. Verification also checks index order, prev-hash links,
  payload hashes, and that the duplicated `created_at` column matches the
  payload timestamp.
- A hash chain detects modification and reordering, not authorship: an attacker
  who can rewrite every row can recompute the chain. Signing (e.g. Ed25519) is
  future work. The UI states this limitation next to the verify result.

## D-012 (Phase 4) Narrative verification and UI sign-off
- The reporter receives computed JSON only; the payload excludes model
  coefficients and planted penalties. Every narrative number is normalised and
  checked against that JSON. A failed LLM draft is retried once, then replaced
  by a deterministic template that passes the same check.
- Streamlit sign-off requires a non-empty approver name. The certificate tab
  shows chain verification and a clearly labelled tamper demo. Notices are
  stored in session state across the rerun so the tamper result is visible.
- The sandbox process is launched through `sandbox.serve`; the auditor package
  never contains the scoring API's import path.

