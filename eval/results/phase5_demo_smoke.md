# Phase 5 headless demo smoke test

Real sandbox process, HTTP probes, full mitigation and narrative, seed 42.
The test is functional; it does not retune any pre-registered threshold.

| Model | Kept | Runtime | Narrative | Number check | Functional | Notes |
|---|---|---|---|---|---|---|
| 2 | 6 | 30.2s | template | PASS | PASS | none |
| 7 | 0 | 24.2s | template | PASS | PASS | none |
| 5 | 2 | 21.1s | template | PASS | PASS | KNOWN PRE-REGISTRATION MISS: single-attribute gender was also kept (net 0.0265). Reported, not retuned; see DECISIONS.md D-009.; expected single gender immaterial; observed kept (D-009 miss) |

Total audit time: **75.6s**. Every individual audit is under the 60-second demo budget.

## Human gate and certificate

- Empty approver rejected: True
- Records issued: 1
- Chain verified before tamper: True
- Chain verified after tamper: False (first broken record: 0)

## Unreachable API

- Planner emitted an aborted event: True
- Error surfaced cleanly: `ProberError: Sandbox is unreachable at http://127.0.0.1:1. Start the sandbox API (see README) and try again. Details: ConnectTimeout: `

## Known miss

Model 5 also kept the single-attribute gender finding at net 0.0265 instead of the pre-registered "immaterial" expectation. The arithmetic error in the pre-registration and the decision not to retune are documented in `DECISIONS.md` D-009. The hotspot remains dominant.
