# Architecture

## System overview

![System architecture](diagrams/system_architecture.png)

The project has two execution paths that share the same retrieval, evidence-ranking, and LLM code:

1. **Live path** (`app.py` → `pipeline.py`): a user enters a claim, Playwright searches the web, evidence is ranked, and two LM Studio models return dataset-aligned labels.
2. **Evaluation path** (`evaluation/`): the official COVID-Fact TSV splits are used with gold evidence, retrieved evidence, or a claim-only baseline, and results are written to JSONL and metrics tables.

`config.py` is the single source of truth for paths, model ids, retrieval settings, and label mappings.

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | Environment loading, paths, model ids, retrieval settings, `SUPPORTED`/`REFUTED` constants |
| `llm_client.py` | LM Studio OpenAI-compatible client, health check, strict label parser |
| `retrieval.py` | Playwright search and page fetch, Brave primary provider, fallbacks, on-disk cache |
| `evidence.py` | Sentence splitting, deduplication, SBERT embeddings, FAISS cosine ranking |
| `pipeline.py` | Live orchestration, optional BERT pre-screen, one-model and two-model checks |
| `app.py` | Gradio UI for live checks, pipeline diagram, evaluation summary, label policy |
| `evaluation/prompts.py` | Zero-shot, few-shot, claim-only, and UI prompts |
| `evaluation/evaluate_covidfact.py` | COVID-Fact runner, gold/retrieved/claim-only modes, incremental JSONL |
| `evaluation/build_retrieval_cache.py` | Reproducible Playwright retrieval cache builder |
| `evaluation/metrics.py` | Accuracy, macro/weighted F1, per-class P/R/F1, bootstrap CI, McNemar |
| `docs/generate_diagrams.py` | Generates the Graphviz diagrams in this folder |

## Live request flow

![Live pipeline](diagrams/live_pipeline.png)

1. `app.py` validates the claim and reads the selected model ids.
2. `pipeline.compare_models` retrieves evidence **once** and reuses it for both models.
3. `retrieval.search_and_fetch`:
   - searches Brave Search's HTML result page with Playwright;
   - falls back to Google News RSS and Wikipedia if Brave returns nothing;
   - fetches up to `RETRIEVAL_MAX_PAGES` pages with Playwright;
   - extracts readable text with `trafilatura`, then BeautifulSoup as a fallback.
4. `evidence.build_candidates` flattens page sentences and search snippets.
5. `evidence.rank_sentences` embeds the claim and candidates with `all-MiniLM-L6-v2`, normalizes them, and uses `faiss.IndexFlatIP` for cosine top-k.
6. `pipeline._classify` builds the strict UI prompt and calls LM Studio.
7. `llm_client.parse_dataset_label` accepts only `SUPPORTED` or `REFUTED`; invalid answers get one correction retry.
8. The UI displays the label, reason, selected evidence with URLs, optional BERT hint, and run metadata.

If no usable evidence is retrieved, the live path returns **No verdict** rather than guessing. This is a status, not a third dataset label.

## Evaluation flow

![Evaluation pipeline](diagrams/evaluation_pipeline.png)

The evaluator supports three evidence modes:

| Mode | Evidence shown to the model |
|---|---|
| `gold` | The dataset's `sentence1` premise |
| `retrieved` | Top-k sentences from the Playwright cache |
| `claim_only` | No evidence; a separate claim-only prompt |

Prompt variants are `zero_shot` and `few_shot`. Few-shot examples are drawn deterministically from `train.tsv` only; the test split is never used to construct prompts. Results are appended to JSONL after every example so interrupted runs can resume.

## Label policy

The official data uses `entailment` / `not_entailment`. The project maps them to:

| Dataset value | Project label |
|---|---|
| `entailment` | `SUPPORTED` |
| `not_entailment` | `REFUTED` |

Evaluation and the primary UI never emit `True`, `False`, `Misleading`, or `Unverifiable`. `ABSTAIN` is reserved for a future abstention mode and is not counted as a dataset label.

## Why Brave and Playwright

The earlier hosted search API was removed because the project needed a no-API-key, demonstrable retrieval layer that runs locally. Playwright provides the browser automation. During testing, Bing returned poisoned results to headless automation and DuckDuckGo's HTML endpoint was unavailable; Brave Search HTML returned relevant results reliably, so it is the primary provider.

## Operational notes

- LM Studio must be running at `http://localhost:1234`.
- `reasoning_effort=none` is sent by default because Qwen3 otherwise spends the whole completion budget on hidden reasoning tokens and returns empty content.
- The first request to an unloaded model is slower (JIT load); later requests are warm.
- Retrieval caches live under `cache/retrieval/` and are intentionally git-ignored.
- The curated evaluation cache lives under `evaluation/retrieval_cache/` and can be committed because it is the reproducible evidence snapshot used by the report.
