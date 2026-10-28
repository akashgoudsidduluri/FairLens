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
