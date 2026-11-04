# FACT_CHECKER Project Plan

Last updated: 2026-11-04

This file is the working plan and context record for the next development phase. It captures the current repository state, the new requirements, decisions already made, implementation phases, evaluation methodology, deliverables, and acceptance criteria. It is intentionally detailed so work can resume without losing context.

---

## 1. Current Project State

### 1.1 Repository

- Local workspace: `C:\Users\sayan\OneDrive\Documents\FACT_CHECKER`
- GitHub repository: `https://github.com/Darkstrike03/Fact-checker.git`
- Branch: `main`
- Local `main` tracks `origin/main`.
- Last synced commit: `01eea7f feat: add Gradio app and project proposal`
- The local folder is now a proper git repository. It was previously not a clone; GitHub had been updated manually.
- Current working tree has one untracked item: `RESOURCES/` (paper PDF and COVID-Fact TSV splits). This will be standardized to `resources/` and committed.

### 1.2 Existing tracked files

- `.env.example`
- `.gitignore`
- `Project.md`
- `advanced_rag.py`
- `app.py`
- `basic_rag.py`
- `fact_checker_bert/config.json`
- `fact_checker_bert/tokenizer.json`
- `fact_checker_bert/tokenizer_config.json`
- `fact_checker_final.py`
- `readme.md`
- `requirements.txt`

Ignored local/runtime items:

- `.env`
- `.venv/`
- `.gradio/`
- `fact_checker_bert/model.safetensors`
- `__pycache__/`

The BERT weights are not committed. They are hosted on HuggingFace:

- `https://huggingface.co/DarkStrike/fact-checker-bert`
- Local model file size: 437,958,624 bytes
- Local SHA-256: `4687c9144491097eddd1daa49dd6be29fefdeb4e834d22efc930ec6b7871ad9c`
- This matches the HuggingFace LFS object.

### 1.3 Existing pipeline

Current `app.py` is a Gradio UI that:

1. Loads `sentence-transformers/all-MiniLM-L6-v2`.
2. Loads the fine-tuned BERT classifier from `./fact_checker_bert`.
3. Runs BERT on the claim.
4. Uses an LLM with hosted search API to extract a search query.
5. Calls the hosted search API.
6. Uses FAISS to select relevant snippets.
7. Sends claim + evidence to a local LLM via LM Studio.
8. Displays `True / False / Misleading / Unverifiable`.

This plan replaces hosted search API with Playwright and changes the evaluated labels to the COVID-Fact dataset labels.

### 1.4 Previous security fix

- Hardcoded hosted search API keys were removed from tracked scripts and replaced with `os.getenv("SEARCH_API_KEY")`.
- `.env` is gitignored.
- The old hosted search API key remained in public git history and should be considered compromised. Since hosted search API is being removed, no new hosted search API key is needed.
- Do not reintroduce secrets into tracked files.

---

## 2. New Requirements

The project was previously considered complete, but new instructions require:

1. Make a comparative analysis of our results with the COVID-Fact dataset paper.
2. Explain the RAG pipeline clearly.
3. Align LLM-generated verdict labels with the original dataset labels. Do not invent custom labels. This is required for valid evaluation.
4. Show the overall pipeline framework for both the live RAG system and the evaluation system with clear diagrams.
5. Eliminate hosted search API and use a Playwright-based retrieval approach to avoid API/resource limitations.
6. Use the new small models and make the web UI usable.
7. Document future improvements:
   - Claim-type-aware fact checking.
   - Abstention-capable fact checking.
   - Poisoning prevention.

---

## 3. Locked Decisions

| Decision | Choice |
|---|---|
| First model | `liquid/lfm2.5-1.2b` |
| Second model | `qwen3-0.6b` |
| Model naming note | LM Studio currently does not list a Gemma 3 0.6B model. The available second model is Qwen3 0.6B. The model ID will remain configurable in case Gemma is loaded later. |
| Evaluation split | Full `test.tsv` = 401 rows |
| Prompt selection | Tune on `dev.tsv` = 419 rows, then evaluate once on test |
| Evidence modes | Gold evidence and Playwright-retrieved evidence |
| Resources | Commit paper PDF, TSV splits, and citation README |
| Future features | Document and leave hooks; do not mix into the binary paper comparison |
| Primary metric | Accuracy and macro F1, aligned to dataset labels |
| Primary labels | `SUPPORTED` and `REFUTED` only |
| Retrieval | Playwright + Bing/DuckDuckGo fallback + SBERT/FAISS evidence selection |
| UI | Update the existing Gradio app, not a full rewrite |
| Diagrams | Graphviz PNG/SVG plus Mermaid in Markdown |

---

## 4. Environment and Model Inventory

### 4.1 LM Studio models currently exposed

`GET http://localhost:1234/api/v0/models` returned:

| Model ID | Architecture | Quantization | Context | State |
|---|---|---|---|---|
| `qwen3-0.6b` | qwen3 | Q3_K_L | 32,768 | not-loaded |
| `liquid/lfm2.5-1.2b` | lfm2 | Q4_K_M | 128,000 | not-loaded |
| `text-embedding-nomic-embed-text-v1.5` | nomic-bert | Q4_K_M | 2,048 | not-loaded |
| `whisper-tiny` | whisper | Q8_0 | n/a | not-loaded |

Both chat models support tool use. They must be loaded in LM Studio before evaluation, or LM Studio JIT loading must be enabled.

### 4.2 System tools

- Python 3.13.6 in `.venv`
- Git 2.53.0
- GitHub CLI authenticated as `Darkstrike03`
- Node 24.22.1 and npm/npx 11.6.0
- Graphviz installed at `C:\Program Files\Graphviz\bin\dot.exe`
- Google Chrome and Microsoft Edge installed
- Playwright is not installed yet
- `bs4`, `trafilatura`, `diskcache`, and `matplotlib` are not installed yet
- `pandas`, `scikit-learn`, `scipy`, `torch`, `transformers`, `sentence-transformers`, `faiss-cpu`, and `gradio` are installed

### 4.3 Existing requirements

```text
gradio==6.12.0
requests==2.33.1
numpy==2.4.4
sentence-transformers==5.4.0
faiss-cpu==1.13.2
torch==2.11.0
transformers==5.5.3
python-dotenv==1.2.4
```

### 4.4 Hardware constraint

Development machine is an 8 GB RAM Windows laptop without a GPU. Resource-conscious choices are required:

- Use small LLMs.
- Use Edge through Playwright instead of downloading another browser where possible.
- Block images/fonts/media in Playwright.
- Limit page fetches per claim.
- Cache retrieval results.
- Load one evaluation model at a time.
- Make BERT pre-screening optional or lazy-loaded in the UI.

---

## 5. COVID-Fact Dataset and Paper Facts

### 5.1 Local dataset files

The resources currently present are:

```text
resources/COVID_FACT_PAPER.pdf
resources/COVID_FACT_DATASET/train.tsv
resources/COVID_FACT_DATASET/dev.tsv
resources/COVID_FACT_DATASET/test.tsv
```

The TSV files are the official `RTE-covidfact` splits from the COVID-Fact repository.

### 5.2 Dataset statistics

| Split | Rows | SUPPORTED (`entailment`) | REFUTED (`not_entailment`) | Unique claims | Unique evidence sentences |
|---|---:|---:|---:|---:|---:|
| train | 3,263 | 1,036 | 2,227 | 3,259 | 1,035 |
| dev | 419 | 130 | 289 | 419 | 130 |
| test | 401 | 130 | 271 | 401 | 130 |

Additional statistics:

- Test claim length: mean 11.8 words, max 39 words.
- Test evidence length: mean 73.4 words, max 209 words.
- Train claim length: mean 12.1 words, max 40 words.
- Train evidence length: mean 72.6 words, max 363 words.
- No blank claim or evidence rows.
- The test set is imbalanced: 32.4% SUPPORTED and 67.6% REFUTED.

The majority-class baseline is approximately 67.6% accuracy with a macro F1 near 40.0.

### 5.3 Important dataset characteristics

- The negative claims are automatically generated counterclaims.
- Many counterclaims are subtle single-token or near-token mutations of the original claim.
- Examples include changing `sars-cov-2` to `chs-cov-2`, `aces-cov-2`, or `gps-cov-2`.
- This means the task rewards careful evidence comparison and can punish models that rely on surface plausibility or world knowledge.
- The dataset is a claim-evidence pair benchmark, not a general social-media claim benchmark.
- The TSV format is premise/evidence in `sentence1` and claim in `Sentence2`.
- The label column is named `label` in train/test and `entailment` in dev.
- The official dataset label semantics are:
  - `entailment` = claim is supported by the evidence = `SUPPORTED`
  - `not_entailment` = claim is contradicted/refuted by the evidence = `REFUTED`

### 5.4 Paper

Paper:

- Title: COVID-Fact: Fact Extraction and Verification of Real-World Claims on COVID-19 Pandemic
- Authors: Arkadiy Saakyan, Tuhin Chakrabarty, Smaranda Muresan
- Venue: ACL 2021
- ACL Anthology: `https://aclanthology.org/2021.acl-long.165/`
- arXiv: `https://arxiv.org/abs/2106.03794`
- Official code/data: `https://github.com/asaakyan/covidfact`

### 5.5 Paper results to compare against

Table 4, veracity prediction and COVID-FEVER:

| System | Training | Evidence | Accuracy | F1 |
|---|---|---|---:|---:|
| RoBERTa-large | Supervised on COVID-Fact | Gold evidence | 83.5 | 82.0 |
| RoBERTa-large | Supervised on COVID-Fact | Top-5 retrieved | 84.7 | 83.0 |
| RoBERTa-large | Supervised on COVID-Fact | Top-1 retrieved | 83.2 | 81.0 |
| RoBERTa-large | Supervised on COVID-Fact | Claim only | 67.5 | 40.0 |
| MNLI zero-shot | MNLI | Gold evidence | 61.3 | 64.2 |
| SciFact zero-shot | SciFact | Gold evidence | 56.9 | 57.0 |
| FEVER zero-shot | FEVER | Gold evidence | 48.3 | 47.0 |

Paper COVID-FEVER score with top-5 evidence: **43.3**.

Table 5, evidence retrieval:

| Evidence setting | Precision | Recall | F1 |
|---|---:|---:|---:|
| Top-5 | 22.27 | 52.37 | 31.25 |
| Top-3 | 24.77 | 45.14 | 31.99 |
| Top-1 | 29.68 | 29.93 | 29.80 |

The paper's F1 should be treated as macro F1 for comparison. The claim-only baseline of 67.5 accuracy and 40.0 F1 is consistent with a majority-class predictor under macro-F1.

---

## 6. Label Alignment Contract

This is non-negotiable for evaluation.

| Dataset TSV label | Paper label | Allowed LLM output |
|---|---|---|
| `entailment` | `SUPPORTED` | `SUPPORTED` |
| `not_entailment` | `REFUTED` | `REFUTED` |

Rules:

1. Evaluation prompts must instruct the LLM to output exactly one of `SUPPORTED` or `REFUTED`.
2. The parser accepts only those two labels after trimming and uppercasing.
3. `True`, `False`, `Misleading`, `Unverifiable`, `credible`, and `not_credible` must not be used as evaluation labels.
4. If the model output is invalid, retry once with a stricter prompt.
5. If the retry is still invalid, record `INVALID` and report it separately. Do not silently map an invented label to a dataset label.
6. Primary UI verdict must also use `SUPPORTED` or `REFUTED` to match the dataset and evaluation.
7. A separate explanation/reason field is allowed. It must not replace the label.
8. Any future abstention mode uses a separate `ABSTAIN` output and must be reported outside the main binary metric. It must not be mapped to either dataset label.
9. Few-shot examples must use examples from the training split and their original dataset labels.

Recommended evaluation prompt shape:

```text
You are a strict evidence-based fact checker.
Given the evidence and the claim, decide whether the claim is supported or refuted.
Use only the evidence. Do not use outside knowledge.
Respond with exactly one word: SUPPORTED or REFUTED.

Evidence:
...
Claim:
...
Label:
```

Recommended parser behavior:

```text
1. Strip whitespace and punctuation.
2. Uppercase.
3. If exactly SUPPORTED or REFUTED, accept.
4. Otherwise retry once with a stricter format instruction.
5. Otherwise record INVALID.
```

---

## 7. Target Architecture

```text
FACT_CHECKER/
|
+-- app.py                       # Gradio UI: live check, compare, pipeline, results
+-- config.py                    # env loading, model discovery, paths, constants
+-- llm_client.py                # LM Studio client, retries, model metadata, parsers
+-- retrieval.py                 # Playwright search, page extraction, cache
+-- evidence.py                  # sentence splitting, SBERT embeddings, FAISS ranking
+-- pipeline.py                  # end-to-end live fact-check pipeline
+-- basic_rag.py                 # stage demo, updated to use shared modules
+-- advanced_rag.py              # stage demo, updated to use shared modules
+-- fact_checker_final.py        # stage demo, updated to use shared modules
+-- evaluation/
|   +-- evaluate_covidfact.py    # CLI evaluation harness
|   +-- prompts.py               # dataset-aligned zero-shot/few-shot prompts
|   +-- metrics.py               # accuracy, macro F1, CIs, McNemar
|   +-- results/                 # predictions and summaries
+-- docs/
|   +-- REPORT.md                # comparative analysis
|   +-- ARCHITECTURE.md          # RAG explanation and diagrams
|   +-- FUTURE_WORK.md           # claim-type-aware, abstention, poisoning
|   +-- diagrams/
|       +-- live_pipeline.png
|       +-- live_pipeline.svg
|       +-- evaluation_pipeline.png
|       +-- evaluation_pipeline.svg
+-- resources/
|   +-- COVID_FACT_PAPER.pdf
|   +-- COVID_FACT_DATASET/
|   |   +-- train.tsv
|   |   +-- dev.tsv
|   |   +-- test.tsv
|   +-- README.md                # citation and label mapping
+-- tests/
|   +-- test_label_mapping.py
|   +-- test_parser.py
|   +-- test_metrics.py
|   +-- test_retrieval_parsing.py
+-- requirements.txt
+-- .env.example
+-- .gitignore
+-- README.md
+-- PLAN.md
```

---

## 8. Implementation Phases

### Phase 0 - Baseline and safety

Tasks:

1. Standardize the resource folder name to lowercase `resources/`.
2. Commit or stage the paper PDF, TSV splits, and a resources README with citations.
3. Record the current commit and working tree state.
4. Update `.gitignore` for new runtime output:
   - `cache/`
   - `evaluation/results/raw/`
   - `playwright-report/`
   - `*.log`
5. Keep `.env`, `.venv`, `.gradio`, model weights, and caches ignored.

Acceptance criteria:

- `resources/` is tracked and lowercase.
- No secrets or large model weights are tracked.
- Current repo remains clean before feature work.

### Phase 1 - Shared configuration and LM Studio client

Tasks:

1. Create `config.py`:
   - Load `.env`.
   - Read `LM_STUDIO_URL`.
   - Read `DEFAULT_MODEL` with fallback `liquid/lfm2.5-1.2b`.
   - Read `BERT_MODEL_PATH`.
   - Read retrieval settings.
2. Create `llm_client.py`:
   - List models from `/v1/models`.
   - Read detailed metadata from `/api/v0/models`.
   - Filter out embedding and whisper models.
   - Provide `chat(messages, model, temperature, max_tokens)`.
   - Add timeout, retries, and clear error messages.
   - Add label parsing and retry logic for evaluation.
3. Add a health check that reports whether a model is loaded.
4. Keep model IDs configurable, not hardcoded.

Acceptance criteria:

- `python -c "from llm_client import list_chat_models; print(list_chat_models())"` returns both small models.
- A simple prompt can be sent to a loaded model.
- Missing model/error states are reported clearly.

### Phase 2 - COVID-Fact evaluation harness

Tasks:

1. Create dataset loader:
   - Handle `label` and `entailment` columns.
   - Map labels to `SUPPORTED` and `REFUTED`.
   - Validate no unknown labels.
2. Create dataset-aligned prompts:
   - Zero-shot.
   - Three-shot using train examples.
   - Separate evaluation prompt (label only) and UI prompt (label + short reason).
3. Create `evaluate_covidfact.py` CLI:
   - `--split {train,dev,test}`
   - `--mode {gold,retrieved,claim_only}`
   - `--model`
   - `--prompt {zero_shot,few_shot}`
   - `--limit`, `--offset`, `--resume`
   - `--temperature 0`
   - `--max-tokens`
   - `--retrieval-cache`
   - `--output`
4. Save raw predictions as JSONL with:
   - claim ID
   - claim text
   - evidence used
   - gold label
   - predicted label
   - raw model output
   - model ID
   - prompt variant and hash
   - latency
   - timestamp
5. Add resumability:
   - Skip already completed claim IDs when `--resume` is used.
   - Write incrementally to avoid losing a long run.
6. Add metrics:
   - Accuracy.
   - Macro F1 (primary).
   - Weighted F1.
   - Per-class precision, recall, F1.
   - Confusion matrix.
   - Support counts.
   - Invalid output rate.
   - 95% bootstrap confidence intervals.
   - McNemar test between models.
7. Tune prompts on dev:
   - Evaluate zero-shot and three-shot for both models on dev.
   - Select the best prompt per model by dev macro F1.
   - Freeze the selected prompt for test.
8. Evaluate on test:
   - LFM2.5-1.2B with gold evidence.
   - LFM2.5-1.2B with Playwright-retrieved evidence.
   - Qwen3-0.6B with gold evidence.
   - Qwen3-0.6B with Playwright-retrieved evidence.
   - Optional claim-only baseline for both models.
9. Write summary files:
   - `evaluation/results/summary.csv`
   - `evaluation/results/summary.md`
   - Per-run prediction JSONL files.

Expected run size:

- Dev prompt tuning: 419 rows x 2 models x 2 prompt variants = 1,676 calls.
- Test: 401 rows x 2 models x 2 evidence modes = 1,604 calls.
- Total: approximately 3,280 LLM calls, plus one-time retrieval cache construction.
- Use small batches and resume support.

Acceptance criteria:

- All evaluation outputs use only `SUPPORTED`/`REFUTED` as labels.
- Test metrics are computed on the full 401-row test set.
- Paper comparison table is generated with paper values and our values.
- No test-set tuning is performed.

### Phase 3 - Playwright retrieval

Tasks:

1. Add dependencies:
   - `playwright`
   - `beautifulsoup4`
   - `trafilatura`
   - `pandas`
   - `scikit-learn`
   - `tqdm`
2. Install Playwright package.
3. Use installed Microsoft Edge via `channel="msedge"` to avoid a separate Chromium download. Keep Chromium as a fallback.
4. Implement `retrieval.py`:
   - Search provider 1: Bing HTML.
   - Search provider 2: DuckDuckGo HTML as fallback.
   - Extract title, URL, and snippet.
   - Deduplicate result URLs and domains.
   - Fetch top pages with Playwright.
   - Block images, fonts, media, and unnecessary resources.
   - Extract page text with `trafilatura` or a BeautifulSoup fallback.
   - Limit text length and page count.
   - Add timeouts and retry policy.
5. Implement query construction:
   - For evaluation, use the raw claim as the search query to match the paper's Google-query style.
   - For live UI, optionally use LLM query extraction but keep it configurable.
6. Implement caching:
   - Cache key: provider + query + max results + max pages.
   - Store JSON under `cache/retrieval/`.
   - Support TTL for live mode.
   - Support cache-only mode for evaluation.
   - Commit the final test retrieval cache used for reported results.
7. Implement evidence selection in `evidence.py`:
   - Split page text into sentences.
   - Embed claim and candidate sentences with `all-MiniLM-L6-v2`.
   - Rank with cosine similarity using FAISS.
   - Select top 5 sentences for evaluation and top 3 for UI display.
   - Preserve source title, URL, sentence text, and score.
8. Remove hosted search API:
   - Remove all hosted search API imports, constants, payloads, and requirements.
   - Remove `SEARCH_API_KEY` from `.env.example` and local `.env`.
   - Remove hosted search API from README and code.
   - Verify with a repository-wide search for the removed provider.
9. Update legacy scripts:
   - `basic_rag.py`, `advanced_rag.py`, and `fact_checker_final.py` should import the shared retrieval module.
   - They must not call hosted search API.
   - They can remain simple stage demos.

Acceptance criteria:

- A sample claim returns at least one usable result and source.
- Retrieval works without a hosted search API key.
- Cache can reproduce the same evidence set.
- No hosted search API references remain in the repository.

### Phase 4 - UI integration

Tasks:

1. Update `app.py`:
   - Model dropdown populated from LM Studio `/v1/models`.
   - Default model: `liquid/lfm2.5-1.2b`.
   - Primary verdict: `SUPPORTED` or `REFUTED` only.
   - Show short reason separately.
   - Show source cards with title, URL, selected sentences, and scores.
   - Show retrieval metadata: query, number of sources, number of selected sentences, latency.
   - Add a side-by-side model comparison mode using the same cached evidence.
   - Add a Pipeline tab with the architecture diagram.
   - Add an Evaluation Results tab with the paper comparison table.
2. Make BERT pre-screening optional or lazy-loaded.
3. Keep the UI usable on 8 GB RAM.
4. Ensure examples use dataset-aligned labels.
5. Add clear error messages for:
   - LM Studio not running.
   - Model not loaded.
   - No web results.
   - Browser launch failure.
   - Invalid model output.

Acceptance criteria:

- UI starts with the small models.
- A claim runs end-to-end without hosted search API.
- Both models can be compared side by side.
- Labels match dataset labels.
- Sources are visible and clickable.

### Phase 5 - Diagrams and documentation

Tasks:

1. Create live pipeline diagram:
   - User claim.
   - Optional claim-type hook.
   - Query extraction.
   - Playwright search.
   - Page extraction.
   - Sentence splitting.
   - SBERT embeddings.
   - FAISS ranking.
   - LLM reasoning.
   - Dataset-aligned label.
   - Optional future ABSTAIN.
   - UI with evidence and sources.
2. Create evaluation pipeline diagram:
   - COVID-Fact TSV.
   - Gold evidence branch.
   - Playwright retrieval branch.
   - Prompt templates.
   - LFM2.5 and Qwen3.
   - Label parser.
   - Metrics.
   - Paper comparison.
3. Render diagrams with Graphviz to PNG and SVG.
4. Add Mermaid versions to Markdown.
5. Write `docs/ARCHITECTURE.md`:
   - Explain RAG in plain language.
   - Explain each stage and why it exists.
   - Explain the label-alignment contract.
   - Include both diagrams.
6. Write `docs/REPORT.md`:
   - Dataset description and split statistics.
   - Methodology.
   - Label alignment.
   - Results tables.
   - Paper comparison.
   - Confidence intervals and significance tests.
   - Error analysis.
   - Limitations.
7. Write `docs/FUTURE_WORK.md`.
8. Update `README.md`:
   - New setup instructions.
   - Playwright setup.
   - Model IDs.
   - Evaluation commands.
   - Results summary.
   - Links to diagrams and report.
9. Add `resources/README.md` with citation and label mapping.

Acceptance criteria:

- Both diagrams exist as PNG/SVG and render clearly.
- Diagrams appear in README, architecture doc, report, and UI Pipeline tab.
- RAG pipeline explanation is understandable to a reader without deep LLM background.
- Report clearly states the paper comparison is not apples-to-apples because the paper uses supervised RoBERTa-large while this project uses zero/few-shot small LLMs.

### Phase 6 - Tests, verification, and Git

Tasks:

1. Add unit tests:
   - Label mapping.
   - Parser acceptance/rejection/retry.
   - Metrics on known confusion matrices.
   - HTML search-result parsing with local fixtures.
2. Add smoke test:
   - 10 rows per split/mode.
3. Run full evaluation.
4. Verify:
   - A repository-wide search for the removed provider returns nothing.
   - `.env` is ignored.
   - Model weights are ignored.
   - `resources/` is tracked.
   - `python -m py_compile` passes for all Python files.
   - Unit tests pass.
   - UI starts.
   - No secrets are tracked.
5. Commit in logical chunks:
   - Resources and citations.
   - Shared config/LLM client.
   - Evaluation harness.
   - Playwright retrieval.
   - UI integration.
   - Documentation and diagrams.
   - Results and report.
6. Push to `origin main`.

Acceptance criteria:

- Clean git status.
- Remote `main` matches local.
- All required deliverables are present.
- Reproducible evaluation instructions are documented.

---

## 9. Comparative Analysis Methodology

### 9.1 Fairness caveats

The paper's best model is a supervised RoBERTa-large fine-tuned on COVID-Fact. Our models are small local LLMs used zero-shot or few-shot. This is not a controlled architecture comparison. The report must state:

- Paper model: supervised, 355M parameters, trained on 3,263 COVID-Fact examples.
- Our models: 0.6B and 1.2B quantized local LLMs, no task-specific fine-tuning.
- Paper retrieval: Google top-5 + SBERT, fixed dataset snapshot.
- Our retrieval: Bing/DuckDuckGo + Playwright + SBERT, live web and cached.
- Therefore, differences reflect both model capacity and training regime.

### 9.2 Comparisons to report

1. Gold evidence:
   - Paper RoBERTa-large vs our LFM2.5 and Qwen3.
   - This isolates veracity reasoning.
2. Retrieved evidence:
   - Paper top-5 vs our Playwright top-5.
   - This measures the end-to-end pipeline.
3. Claim-only:
   - Paper claim-only baseline vs our models without evidence.
   - This checks whether models use evidence or rely on claim plausibility.
4. Retrieval quality:
   - Number of successful retrievals.
   - Average sources and sentences.
   - Optional approximate evidence precision/recall/F1 using a calibrated matcher.
5. Error analysis:
   - Sample 20-30 errors.
   - Categorize as retrieval failure, evidence reasoning failure, surface-token shortcut, commonsense/causal reasoning failure, or label confusion.
   - Compare qualitatively with the paper's error analysis.

### 9.3 Optional approximate COVID-FEVER

Exact COVID-FEVER reproduction is not possible with the TSV-only resources because:

- The paper used a fixed Google search snapshot.
- The paper's gold evidence sets may contain multiple sentences; the TSV pair format provides one evidence sentence per row.
- Live web content changes.

If implemented:

1. Match each retrieved sentence to the gold `sentence1` using normalized token F1 or SBERT cosine.
2. Calibrate the match threshold on dev.
3. Compute approximate evidence precision, recall, and F1.
4. Compute approximate COVID-FEVER = correct label AND at least one matched evidence sentence.
5. Label the metric clearly as approximate and not directly comparable to the paper's exact 43.3.

If the matcher is not reliable on dev, omit the approximate score and explain why.

---

## 10. Retrieval Design Details

### 10.1 Search providers

Primary:

- Bing HTML search results.

Fallback:

- DuckDuckGo HTML search results.

Avoid:

- Google scraping due to CAPTCHA and terms-of-service issues.

### 10.2 Browser settings

- Playwright with installed Microsoft Edge (`channel="msedge"`) by default.
- Headless mode.
- Block image, media, and font requests.
- Set a realistic user agent.
- Use one browser instance and a fresh page/context per query where needed.
- Timeouts: 10-15 seconds per page.
- Limit to 5 results and 3 fetched pages per claim for evaluation; make configurable.
- Add small delays between page fetches.
- Cache aggressively.

### 10.3 Content extraction

- Prefer `trafilatura` for main article text.
- Fall back to BeautifulSoup text extraction.
- Normalize whitespace.
- Remove navigation/boilerplate where possible.
- Split into sentences with a deterministic regex or lightweight sentence splitter.
- Keep source title and URL with every sentence.

### 10.4 Caching

- Path: `cache/retrieval/`.
- Key: SHA-256 of provider, query, max results, and max pages.
- Store JSON with timestamp, results, page text excerpts, and selected sentences.
- Live mode TTL: configurable, default 7 days.
- Evaluation mode: cache-only and pinned.
- Commit the final test retrieval cache used for the report, compressed if large.

### 10.5 Evidence ranking

- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Dot product or L2 FAISS index.
- Select top 5 sentences for evaluation.
- Select top 3 sentences for UI display.
- Include source and score with each selected sentence.

---

## 11. UI Design Details

Tabs:

1. `Check Claim`
   - Claim input.
   - Model dropdown.
   - Primary label.
   - Explanation.
   - Sources and selected evidence.
   - Latency and retrieval metadata.
2. `Compare Models`
   - Same claim and cached evidence for both models.
   - Side-by-side labels, reasons, and latencies.
3. `Pipeline`
   - Live pipeline diagram.
   - Short explanation of each stage.
   - Label-alignment table.
4. `Evaluation Results`
   - Paper comparison table.
   - Model comparison table.
   - Confusion matrices.
   - Caveats.

UI label rules:

- Primary label is `SUPPORTED` or `REFUTED`.
- Do not show `True`, `False`, `Misleading`, or `Unverifiable` as primary labels.
- If a future abstention mode is enabled, show `ABSTAIN` as a separate state and explain that it is not a dataset label.

Memory rules:

- Lazy-load BERT.
- Allow disabling the BERT pre-screen.
- Load one LLM at a time for evaluation.
- Use the existing embedding model once at startup.

---

## 12. Future Work Hooks

### 12.1 Claim-type-aware fact checking

Goal:

- Different claim types need different evidence and prompts.

Possible claim types:

- Scientific/medical.
- Statistical/numerical.
- Causal.
- Policy/government.
- General social media claim.

Design hooks:

- `classify_claim_type(claim) -> str`
- Retrieval source preferences per type.
- Prompt templates per type.
- Use COVID-Fact `flair` metadata if the full JSONL is added later.
- Report per-type accuracy and macro F1.

### 12.2 Abstention-capable fact checking

Goal:

- Avoid forced binary answers when evidence is insufficient or conflicting.

Design hooks:

- `AbstentionPolicy` interface.
- Output `ABSTAIN` when:
  - No retrieval results.
  - Evidence is contradictory.
  - Model confidence is below a calibrated threshold.
  - Evidence does not address the claim.
- Evaluate with coverage, selective accuracy, and risk-coverage curves.
- Report abstention separately from binary dataset metrics.
- Do not map `ABSTAIN` to `SUPPORTED` or `REFUTED`.

### 12.3 Poisoning prevention

Goal:

- Protect the pipeline from adversarial or low-quality retrieved content.

Design hooks:

- Source credibility scoring.
- Domain allowlist/denylist.
- Multiple-source agreement.
- Retrieval provenance and timestamps.
- Prompt-injection sanitization.
- Delimit evidence clearly and instruct the model to ignore instructions inside evidence.
- Cache integrity checks.
- Optional human review for high-risk claims.

---

## 13. Git and Repository Rules

- Do not commit:
  - `.env`
  - `.venv/`
  - `.gradio/`
  - model weights
  - `__pycache__/`
  - raw intermediate caches
  - logs
- Commit:
  - `resources/` PDF and TSVs
  - `resources/README.md`
  - source code
  - tests
  - docs and diagrams
  - final retrieval cache used for reported results
  - evaluation summary and small prediction files
- Use logical commits.
- Do not force-push.
- Do not rewrite history unless explicitly requested.
- Verify remote `main` matches local after pushing.

---

## 14. Verification Checklist

### Code

- [ ] `python -m py_compile` passes for all Python files.
- [ ] No removed-provider references remain in code or docs.
- [ ] No hardcoded API keys.
- [ ] `.env` ignored.
- [ ] Model weights ignored.
- [ ] Legacy scripts still run using shared retrieval.
- [ ] UI starts with both small models.

### Data and evaluation

- [ ] Train/dev/test row counts match 3,263 / 419 / 401.
- [ ] Label mapping is exactly `entailment -> SUPPORTED`, `not_entailment -> REFUTED`.
- [ ] Evaluation outputs only allowed labels.
- [ ] Invalid outputs are tracked.
- [ ] Dev tuning is separated from test evaluation.
- [ ] Full test evaluation completes for both models and both evidence modes.
- [ ] Confidence intervals are reported.
- [ ] Paper comparison table includes the official paper numbers.
- [ ] Approximate COVID-FEVER is clearly labeled as approximate or omitted with an explanation.

### Retrieval

- [ ] Playwright retrieval works without hosted search API.
- [ ] Bing primary and DuckDuckGo fallback are implemented.
- [ ] Browser blocking and timeout settings are active.
- [ ] Retrieval cache is reproducible.
- [ ] Final retrieval cache is committed.
- [ ] Sources and selected evidence are displayed.

### Documentation

- [ ] `PLAN.md` up to date.
- [ ] `README.md` updated.
- [ ] `docs/ARCHITECTURE.md` includes RAG explanation and diagrams.
- [ ] `docs/REPORT.md` includes comparative analysis.
- [ ] `docs/FUTURE_WORK.md` includes all three future directions.
- [ ] `resources/README.md` includes citation and label mapping.
- [ ] Diagrams render as PNG/SVG and are embedded correctly.

### Git

- [ ] `git status` clean.
- [ ] Local `main` equals `origin/main`.
- [ ] All intended files are tracked.
- [ ] No secrets or large weights are tracked.
- [ ] Final commit messages are clear.

---

## 15. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Search engine bot detection or CAPTCHA | Use Bing first, DuckDuckGo fallback, low request volume, caching, and clear failure reporting. |
| Live web changes make results irreproducible | Commit the final retrieval cache and report the cache date. |
| Playwright + LLMs exceed 8 GB RAM | Use Edge, block media, limit pages, load one model at a time, lazy-load BERT. |
| Small models are much weaker than paper's RoBERTa | Report the gap honestly; explain supervised vs zero/few-shot difference. |
| Model outputs invented labels | Strict prompt, parser allowlist, one retry, record INVALID, report coverage. |
| Dataset counterclaims are subtle token mutations | Include error analysis; do not overclaim generalization. |
| Exact COVID-FEVER cannot be reproduced | Use optional approximate metric with calibration, or omit and explain. |
| Resources folder case mismatch on Windows | Standardize to lowercase `resources/` before committing. |
| LM Studio models not loaded | Add health checks and clear instructions; support JIT loading if available. |
| Repository size grows | Commit only final cache/summary, not raw intermediate caches; keep model weights out. |

---

## 16. Execution Order

1. Create this plan file.
2. Standardize and commit resources.
3. Build shared config and LM Studio client.
4. Build dataset loader, label parser, prompts, and metrics.
5. Run dev prompt tuning for both models.
6. Run gold-evidence test evaluation.
7. Build Playwright retrieval and evidence selection.
8. Build and commit the test retrieval cache.
9. Run retrieved-evidence test evaluation.
10. Update the Gradio UI.
11. Create diagrams and documentation.
12. Run tests and verification.
13. Commit and push.

---

## 17. Context for the Next Session

If work resumes later, read this file first. The most important constraints are:

- Use only `SUPPORTED` and `REFUTED` as the evaluated verdict labels.
- The dataset mapping is `entailment -> SUPPORTED` and `not_entailment -> REFUTED`.
- Do not use `True`, `False`, `Misleading`, or `Unverifiable` in evaluation.
- Tune on dev, evaluate on test.
- Compare against the paper's Table 4 and Table 5 with explicit fairness caveats.
- hosted search API must be completely removed.
- Playwright retrieval must be cached for reproducibility.
- The final UI must show dataset-aligned labels and evidence sources.
- Future features are documented and hooked, not mixed into the binary comparison.
