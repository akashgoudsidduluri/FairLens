# LLM screener target (R3c)

A black-box target that asks an Anthropic model to screen a loan applicant. It is
a third kind of target alongside the seven synthetic sandbox models and the two
real-data models: the decision rules were not written by us and are not visible.

`build_target("llm:screener", config)` returns `LLMTargetAdapter`. With no
`ANTHROPIC_API_KEY` it reports `unavailable`; it never fabricates a decision.

## Prompt

The prompt contains name, region, age, gender, annual income, loan amount, credit
score, and employment years. It asks for one strict JSON object:

```json
{"approved": true, "score": 720}
```

`approved` must be a JSON boolean and `score` a finite number from 0 to 1000.
Anything else - prose, markdown fences, extra keys, the wrong type, an
out-of-range score - is a parse failure. Parse failures are counted per call and
reported as a parse-failure rate; they are never replaced with a default answer.

The prompt deliberately omits the applicant id, raw pincode, pincode group, name
group, and urban/rural label. A twin therefore cannot leak a second change
through an identifier.

## Twins and the name/region pools

Only names and regions are varied:

| Probe | What changes | Everything else |
|---|---|---|
| `name_group` | the `Name:` line | byte-identical |
| `pincode_group` | the `Region:` line | byte-identical |

`targets/llm/names.py` holds the pools. Each name pool mixes common Indian names
from several backgrounds, and the three pools are arbitrary. They are an
**approximation**, not a statement about anyone's religion, caste, language,
ethnicity, or community, and no pool represents a coherent group. Region strings
are Indian cities and states. The mapping from the synthetic group labels to a
concrete name or region is deterministic, so the same applicant always gets the
same string.

`LLMTargetAdapter.validate_pair` compares the substituted prompt fields and
requires exactly `["name"]` or exactly `["region"]` to change. It also rejects an
identical prompt. The audit never runs a gender or intersectional probe against
this target: `supported_probes` is `{name_group, pincode_group}` and the skipped
probes are reported with reasons.

## Repeats, majority, and variance

- `temperature = 0`.
- Each applicant is screened `repeats = 3` times (config).
- A pair is flipped only if the **majority** outcome differs between original
  and twin. Fewer than 2 parseable repeats, or a tie, is unresolved: counted and
  reported, excluded from b/c.
- Run-to-run variance is a separate metric: the mean per-pair variance of the
  repeat-level flip indicator, the share of pairs whose repeats disagree, and the
  mean per-applicant approval disagreement. These are reported in
  `eval/results/llm_screener.md`.

## Cache

`targets/llm/cache.py` stores one JSON file per prompt under `data/llm_cache/`
(git-ignored). The key is a SHA-256 of the model, prompt, temperature, and max
tokens. The file holds a list of repeat samples: the first run makes `repeats`
calls, later runs read the same samples for free and reproduce the same variance.
Delete the directory to force fresh calls.

## Hard caps and cost

`config.yaml` sets, per audit:

```yaml
llm:
  repeats: 3
  temperature: 0.0
  max_tokens: 64
  max_calls_per_audit: 300
  max_cost_usd: 1.00
  input_cost_per_mtok_usd: 3.00
  output_cost_per_mtok_usd: 15.00
  cache_dir: data/llm_cache
  pairs_per_probe: 24
```

The call cap is checked before every API call; cache hits do not count. The cost
cap is checked with a worst-case estimate (prompt tokens + `max_tokens`) before
the call and updated with the provider's reported usage afterwards. Pricing is
an estimate for the cap, not a billing record; adjust it if the model changes.
When a cap is reached the adapter raises `LLMCapExceeded`; the evaluation records
how far it got rather than quietly shrinking the sample.

300 calls = 50 pairs at 3 repeats and 2 applicants per pair. That is smaller than
the frozen `min_pairs = 1000`, so an LLM result is **exploratory and
underpowered** by construction. The pre-registration says so before the run.

## Unavailable state

The model comes from `ANTHROPIC_MODEL` and the key from `ANTHROPIC_API_KEY`, both
environment variables. Neither is written to disk. If either is missing:

- `health()` returns `{"status": "unavailable", "reason": ...}`;
- `score_batch()` raises `LLMUnavailable`;
- the evaluation writes "unavailable" in the LLM section and runs no audit.

Tests use a fake client injected into the adapter. There is no mock in the
product path.

## Run

```powershell
# optional: set the key and model in this shell only
$env:ANTHROPIC_API_KEY = "..."
$env:ANTHROPIC_MODEL = "..."

# exploratory audit, 24 pairs per probe, capped at 300 calls
.\.venv\Scripts\python -m eval.run_llm_eval
```

Outputs `eval/results/llm_screener.csv`, `eval/results/llm_screener.md`, and an
LLM section appended to `eval/results/real_models.md`.

## Limitations

- A language model is not a stable measurement instrument. Temperature 0 reduces
  but does not eliminate run-to-run variation; the variance metric is there to
  make that visible, not to fix it.
- The name and region pools are approximations. A result about them is not a
  claim about a religion, caste, language, or community.
- 24 pairs per probe cannot meet the pre-registered 1,000-pair minimum. No LLM
  finding can be kept under the frozen protocol.
- The prompt is one of many possible screening prompts. A different prompt could
  produce different behaviour.
- Only two probes in one direction each fit under the cap. Gender, the reverse
  name/region directions, and intersectional cells are not tested.
- This is a research harness, not a fair-lending compliance tool, and it is not
  a claim about Anthropic or any deployed lender.
