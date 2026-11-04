# Evaluation

This page documents the binary COVID-Fact **reference benchmark** for the retrieval and classification pipeline. The live product is a general social-media claim checker that can also return `UNVERIFIED`; those live results are not scored here because no labelled social-media benchmark is available yet.

## Task and labels

The project uses the official COVID-Fact RTE data:

| Split | Rows | SUPPORTED | REFUTED |
|---|---:|---:|---:|
| train | 3,263 | 1,036 | 2,227 |
| dev | 419 | 130 | 289 |
| test | 401 | 130 | 271 |

The dataset label column is `label` for train/test and `entailment` for dev. Mapping is fixed:

- `entailment` → `SUPPORTED`
- `not_entailment` → `REFUTED`

## Modes

| Mode | Input to model | Purpose |
|---|---|---|
| `gold` | Dataset `sentence1` premise | Isolates the LLM's reasoning/classification ability |
| `retrieved` | Playwright-retrieved top-k sentences | End-to-end retrieval + reasoning |
| `claim_only` | No evidence | Baseline for parametric knowledge |

`gold` and `retrieved` use the evidence-grounded system prompt. `claim_only` uses a separate prompt that explicitly allows background knowledge.

## Prompt variants

- **Zero-shot:** system prompt plus evidence and claim; asks for one word.
- **Few-shot:** three examples from `train.tsv`, selected deterministically with seed 42. The selected set is class-balanced and never includes dev/test rows.

The strict system prompt is:

```text
You are a careful evidence-based fact checker for COVID-19 claims.
Decide whether the provided evidence SUPPORTS or REFUTES the claim.

Definitions:
- SUPPORTED: the evidence entails the claim.
- REFUTED: the evidence contradicts the claim.

Use only the provided evidence. Do not use outside knowledge.
Answer with exactly one word: SUPPORTED or REFUTED. Do not explain.
```

## Output parser

`llm_client.parse_dataset_label` accepts only `SUPPORTED` and `REFUTED`. It handles a bare label, a prefixed label such as `LABEL: SUPPORTED`, and punctuation. It rejects `True`, `False`, `Misleading`, `Unverifiable`, empty output, and responses that contain both labels ambiguously. Invalid outputs get one correction retry; if still invalid, they are recorded as `invalid` and excluded from accuracy/F1 denominators.

## Metrics

- Accuracy
- Macro F1 (primary balanced metric)
- Weighted F1
- Per-class precision, recall, F1, support
- Confusion matrix in `[[SUPPORTED, REFUTED]]` row/column order
- Invalid count and invalid rate
- Percentile bootstrap 95% confidence interval for accuracy (1,000 resamples)
- Exact McNemar test for paired model comparisons

## Results: gold evidence, full test split

Both models were run on all 401 test rows with both prompt variants. This is the main comparison.

| Model | Prompt | N | Accuracy | Macro F1 | Weighted F1 | Invalid | 95% CI |
|---|---|---:|---:|---:|---:|---:|---|
| LFM2.5 1.2B | few-shot | 401 | 64.3% | 0.6301 | 0.6548 | 0 | [59.6%, 68.8%] |
| Qwen3 0.6B | zero-shot | 401 | 54.6% | 0.5413 | 0.5578 | 0 | [50.1%, 59.4%] |
| LFM2.5 1.2B | zero-shot | 401 | 34.7% | 0.2812 | 0.2049 | 0 | [29.9%, 39.4%] |
| Qwen3 0.6B | few-shot | 401 | 33.9% | 0.2765 | 0.2016 | 0 | [29.4%, 38.7%] |

### Per-class metrics

| Model | Prompt | Class | Precision | Recall | F1 | Support |
|---|---|---|---:|---:|---:|---:|
| LFM2.5 1.2B | few-shot | SUPPORTED | 0.4667 | 0.7000 | 0.5600 | 130 |
| LFM2.5 1.2B | few-shot | REFUTED | 0.8107 | 0.6162 | 0.7002 | 271 |
| Qwen3 0.6B | zero-shot | SUPPORTED | 0.3870 | 0.6846 | 0.4944 | 130 |
| Qwen3 0.6B | zero-shot | REFUTED | 0.7602 | 0.4797 | 0.5882 | 271 |
| LFM2.5 1.2B | zero-shot | SUPPORTED | 0.3316 | 1.0000 | 0.4981 | 130 |
| LFM2.5 1.2B | zero-shot | REFUTED | 1.0000 | 0.0332 | 0.0643 | 271 |
| Qwen3 0.6B | few-shot | SUPPORTED | 0.3265 | 0.9769 | 0.4894 | 130 |
| Qwen3 0.6B | few-shot | REFUTED | 0.7500 | 0.0332 | 0.0636 | 271 |

### Confusion matrices

Rows are gold, columns are predicted, order `SUPPORTED`, `REFUTED`.

| Model | Prompt | Matrix |
|---|---|---|
| LFM2.5 1.2B | few-shot | `[[91, 39], [104, 167]]` |
| Qwen3 0.6B | zero-shot | `[[89, 41], [141, 130]]` |
| LFM2.5 1.2B | zero-shot | `[[130, 0], [262, 9]]` |
| Qwen3 0.6B | few-shot | `[[127, 3], [262, 9]]` |

### Paired comparison

LFM2.5 few-shot vs Qwen3 zero-shot:

- only LFM correct: 92
- only Qwen correct: 53
- exact McNemar p = **0.0015**

The difference is statistically significant at the 0.05 level, but the sample is a single test split and a single prompt seed.

### Dev sanity check

The full dev split was run for LFM2.5 (both prompts) before stopping the remaining Qwen dev runs to keep the fast path short:

| Model | Prompt | N | Accuracy | Macro F1 |
|---|---|---:|---:|---:|
| LFM2.5 1.2B | few-shot | 419 | 59.4% | 0.5836 |
| LFM2.5 1.2B | zero-shot | 419 | 33.7% | 0.2783 |

This agrees with the test ranking for LFM (few-shot > zero-shot) and was used to select the LFM configuration.

## Results: retrieved evidence sample

A deterministic class-stratified sample of **60 test claims** (19 SUPPORTED / 41 REFUTED after rounding, seed 42) was used for the fast-path retrieval check. Evidence was built with Playwright using Brave Search and up to two fetched pages per claim.

The cache build took 1,467 seconds and produced 60 items: 8 resolved with Brave page text, 47 fell back to Google News RSS snippets, and 5 returned no usable result. The run is therefore mostly a search-snippet upper bound rather than a full page-fetch benchmark. Five claims had no retrieved evidence; the model was still prompted and emitted a label for them.

| Model | Prompt | N | Accuracy | Macro F1 | Weighted F1 | Invalid | 95% CI |
|---|---|---:|---:|---:|---:|---:|---|
| LFM2.5 1.2B | few-shot | 60 | 71.7% | 0.6679 | 0.7145 | 0 | [60.0%, 83.3%] |
| Qwen3 0.6B | zero-shot | 60 | 58.3% | 0.5823 | 0.5899 | 0 | [45.0%, 71.7%] |

Per-class results:

| Model | Class | Precision | Recall | F1 | Support |
|---|---|---:|---:|---:|---:|
| LFM2.5 1.2B | SUPPORTED | 0.5556 | 0.5263 | 0.5405 | 19 |
| LFM2.5 1.2B | REFUTED | 0.7857 | 0.8049 | 0.7952 | 41 |
| Qwen3 0.6B | SUPPORTED | 0.4211 | 0.8421 | 0.5614 | 19 |
| Qwen3 0.6B | REFUTED | 0.8636 | 0.4634 | 0.6032 | 41 |

The retrieved run is not directly comparable to the full 401-example gold run because the sample is smaller, class-stratified, and mostly snippet-based. It does show that the end-to-end Playwright → SBERT/FAISS → LM Studio path runs without errors and that LFM2.5 few-shot remains the stronger configuration.

## Comparison with the COVID-Fact paper

| System | Accuracy | F1 |
|---|---:|---:|
| RoBERTa-large, gold evidence | 83.5% | 82.0 |
| RoBERTa-large, top-5 retrieved evidence | 84.7% | 83.0 |
| Claim-only classifier | 67.5% | 40.0 |
| COVID-FEVER transfer | 43.3% | - |
| This project: LFM2.5 1.2B few-shot, gold | 64.3% | 63.0 macro |
| This project: Qwen3 0.6B zero-shot, gold | 54.6% | 54.1 macro |
| This project: LFM2.5 1.2B few-shot, 60-claim retrieved sample | 71.7% | 66.8 macro |
| This project: Qwen3 0.6B zero-shot, 60-claim retrieved sample | 58.3% | 58.2 macro |

The small local models are far below the paper's fine-tuned RoBERTa-large. LFM2.5 few-shot is below the paper's claim-only **accuracy** baseline (64.3% vs 67.5%) but has a substantially higher **macro F1** (63.0 vs 40.0), meaning it is much less biased toward the majority class. The paper's claim-only baseline is not directly comparable as a macro-F1 number because the published table reports a single F1 value; the comparison is therefore indicative, not a formal head-to-head.

## Error analysis

- **Majority-class collapse:** LFM zero-shot predicts SUPPORTED for 390/401 examples and Qwen few-shot for 389/401. Both score near-zero REFUTED recall (0.033). This inflates apparent accuracy but produces useless balanced performance.
- **Few-shot sensitivity:** the three demonstration examples help LFM substantially (34.7% → 64.3%) but hurt Qwen (54.6% → 33.9%). Small models are highly prompt-sensitive.
- **Near-miss claims:** COVID-Fact test claims are often entity-swapped variants sharing the same premise, so lexical overlap alone is insufficient. The model must track the specific entity/number/relation that changed.
- **Gold evidence is a ceiling:** the gold run isolates classification from retrieval. The retrieved run is expected to be harder because page extraction and ranking add noise.
- **Invalid outputs:** neither model produced invalid labels on the test split after the strict parser and one retry; this validates the parser/prompt, not necessarily reasoning quality.
- **Latency:** mean per-example latency was about 3.3s for LFM and 2.4s for Qwen on this laptop, including prompt processing.

## Reproduction

```powershell
# Full test, gold evidence, both prompts, both models
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --mode gold --prompt both `
  --model liquid/lfm2.5-1.2b --model qwen3-0.6b

# Rebuild summary only
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact --summary-only

# 60-example retrieval sample
.\.venv\Scripts\python.exe -m evaluation.build_retrieval_cache `
  --split test --sample 60 --sample-seed 42 --max-pages 2
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --sample 60 --sample-seed 42 --mode retrieved `
  --prompt zero_shot --model qwen3-0.6b
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --sample 60 --sample-seed 42 --mode retrieved `
  --prompt few_shot --model liquid/lfm2.5-1.2b
```

## Limitations

- Only two small quantized models were tested; no fine-tuned transformer baseline was run locally.
- The retrieval evaluation is a 60-example sample, not the full 401-claim retrieval benchmark.
- Live web retrieval is time-sensitive; results depend on search-engine behavior on the run date.
- The test split was used for the final comparison; prompt selection for LFM used dev, while Qwen prompt behavior was checked on a small dev subset and the full test split was reported for transparency.
- No human evaluation of reasons or citations was performed.
