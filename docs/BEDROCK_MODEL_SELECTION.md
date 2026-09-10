# Bedrock Model Selection

## Non-negotiable rules

1. **Never hardcode a model ID without verifying it is `ACTIVE`.** The Bedrock model lifecycle includes `ACTIVE`, `LEGACY`, and `EOL`. A `LEGACY` model can be removed with limited notice. An `EOL` model returns an error on invoke.
2. **Verify at deploy time, not build time.** The spec explicitly forbids picking a model based on this document alone — the doc gives a *procedure*, not a final answer.
3. **Choose based on measured behavior for our task**, not on marketing benchmarks.

---

## Procedure (run this at the start of Day 1)

### Step 1 — List currently ACTIVE Anthropic models in your deploy region

```bash
export AWS_REGION=ap-south-1

aws bedrock list-foundation-models \
  --region $AWS_REGION \
  --by-inference-type ON_DEMAND \
  --by-provider Anthropic \
  --query "modelSummaries[?modelLifecycle.status=='ACTIVE'].[modelId,modelName,inferenceTypesSupported]" \
  --output table
```

Repeat for `--by-provider Amazon` if you want to consider Nova models. Repeat for `us-east-1` if `ap-south-1` returns nothing usable.

### Step 2 — Enable model access

Bedrock → Model access → request the models from Step 1 you want to test. Wait for `Access granted`.

### Step 3 — Benchmark on 5 test documents

Use `scripts/evaluate.py --model-benchmark` (added in the next batch) which runs the extraction prompt against:

1. Clean English printed record
2. Clean Hindi printed record
3. Mixed printed+handwritten record
4. Poor-quality scan
5. Deliberately ambiguous record (missing area)

For each model, record:

- **Structured output success rate** — did the model return valid JSON matching the schema?
- **Field extraction accuracy** — vs. ground truth in `data/test_scenarios.json`
- **Refusal / hallucination rate** — did it invent a Khasra number?
- **p50 / p99 latency**
- **Input+output token cost** per document

### Step 4 — Pick two models

- **Primary** (`BEDROCK_MODEL_ID_PRIMARY`): the cheapest model that passes structured output ≥ 95% and field accuracy ≥ 85% on the 5 test docs.
- **Fallback** (`BEDROCK_MODEL_ID_FALLBACK`): the highest-accuracy model, used only when the primary returns low field confidence or refuses.

The extraction Lambda calls the fallback automatically when the primary's own reported field confidence is below a threshold (default `0.6`).

---

## As-of-January-2026 candidate shortlist (informational only — MUST verify ACTIVE status)

> This section will go stale. Do NOT use these IDs without running Step 1 first.

| Candidate | Why consider | Why maybe not |
|---|---|---|
| `anthropic.claude-haiku-4-5-*` (Haiku 4.5) | Cheapest Anthropic. Good structured JSON. Low latency. | Multilingual (Hindi) accuracy sometimes lower than Sonnet on messy scans. |
| `anthropic.claude-sonnet-4-6-*` (Sonnet 4.6) | Strong on multilingual + ambiguous docs. Best hallucination resistance. | 5–10× cost of Haiku. Slower. |
| `amazon.nova-lite-*` / `amazon.nova-pro-*` | Very cheap; in-region availability in `ap-south-1` is usually strong. | Hindi extraction quality on scanned documents varies — test before committing. |

**Do not pick Claude Opus for this workload.** The task is structured extraction from short OCR text — Opus is overkill and blows the cost budget.

---

## Model invocation contract

The extraction Lambda always calls Bedrock like this (pseudo-code):

```python
response = bedrock.converse(
    modelId=os.environ["BEDROCK_MODEL_ID_PRIMARY"],
    system=[{"text": SYSTEM_PROMPT}],
    messages=[{"role": "user", "content": [{"text": build_user_prompt(ocr_text)}]}],
    inferenceConfig={
        "temperature": 0.0,       # deterministic for extraction
        "maxTokens": 1500,
        "topP": 0.1,
    },
    # If the chosen model supports it, ask for JSON via tool-use:
    toolConfig={
        "tools": [{"toolSpec": {
            "name": "record_extraction",
            "description": "Return the extracted land-record fields.",
            "inputSchema": {"json": RECORD_JSON_SCHEMA},
        }}],
        "toolChoice": {"tool": {"name": "record_extraction"}},
    },
)
```

Using tool-use for JSON output is more reliable than "return only JSON" prompting on every model we've seen. If the chosen model does not support tools, we fall back to a strict JSON prompt with a post-parse validator that retries once on failure.

**Extraction confidence** is computed application-side from:

- did the model return valid JSON on the first try? (+0.2)
- how many non-null fields? (proportional)
- did the model set `"null"` or `null` for missing values (following the prompt)? (+0.1)

We **never** ask the model to invent a confidence number. See `VALIDATION_RULES.md`.

---

## Cost guardrail

At Day 1 end, run:

```bash
python scripts/estimate_cost.py --daily-documents 50 --model $BEDROCK_MODEL_ID_PRIMARY
```

If the estimated monthly Bedrock cost exceeds $10, either:

1. Switch to a cheaper primary model, or
2. Reduce the prompt token size (trim OCR text to first N chars for very long documents), or
3. Cache repeated invocations by OCR-text hash (a real production concern; skip for hackathon unless you're over budget)
