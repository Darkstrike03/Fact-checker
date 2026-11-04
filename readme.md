# COVID-Fact Evidence Checker

**4th Year Project | Dept. of Computer Science & Engineering | RCCIIT**

Faculty Supervisor: Dr. Anup Kumar Kolya

A retrieval-grounded fact-checking system for COVID-19 claims. The system uses local Playwright-based web retrieval, SBERT + FAISS evidence ranking, and two small quantized models served by LM Studio. Verdicts use the COVID-Fact dataset labels **SUPPORTED** and **REFUTED** only.

## What it does

- Searches the web with Playwright (Brave Search primary, Google News RSS and Wikipedia fallbacks).
- Fetches and extracts page text with `trafilatura`.
- Ranks evidence sentences with `all-MiniLM-L6-v2` and FAISS cosine similarity.
- Sends the same evidence to two LM Studio models and asks for a strict binary label.
- Shows the label, short reason, selected evidence with URLs, optional BERT hint, and run metadata.
- Returns **No verdict** when no usable evidence is found instead of inventing a label.
- Provides a reproducible evaluation harness for the official COVID-Fact splits.

## Results

Full test split, gold evidence, 401 examples per configuration:

| Model | Prompt | Accuracy | Macro F1 | Invalid |
|---|---|---:|---:|---:|
| LFM2.5 1.2B | few-shot | 64.3% | 0.6301 | 0 |
| Qwen3 0.6B | zero-shot | 54.6% | 0.5413 | 0 |
| LFM2.5 1.2B | zero-shot | 34.7% | 0.2812 | 0 |
| Qwen3 0.6B | few-shot | 33.9% | 0.2765 | 0 |

On the 60-claim retrieval sample (19 SUPPORTED / 41 REFUTED), LFM2.5 few-shot scored **71.7% / 0.6679 macro F1** and Qwen3 zero-shot scored **58.3% / 0.5823**. That run is mostly search-snippet evidence (8 Brave page-text results, 47 Google News snippets, 5 failures), so it is a pilot result rather than a full page-fetch benchmark.

For comparison, the COVID-Fact paper reports 83.5% accuracy / 82.0 F1 for RoBERTa-large with gold evidence and 67.5% / 40.0 for a claim-only classifier. The small local models are much less accurate than the fine-tuned RoBERTa, but LFM2.5 few-shot has substantially higher macro F1 than the paper's claim-only baseline. See [docs/EVALUATION.md](docs/EVALUATION.md) and [docs/REPORT.md](docs/REPORT.md) for details and limitations.

## Project structure

```text
FACT_CHECKER/
├── app.py                         # Gradio UI
├── pipeline.py                    # Live orchestration
├── retrieval.py                   # Playwright search + page fetch
├── evidence.py                    # Sentence splitting + SBERT/FAISS ranking
├── llm_client.py                  # LM Studio client + strict label parser
├── config.py                      # Paths, models, environment settings
├── basic_rag.py                   # Stage 1 CLI demo
├── advanced_rag.py                # Two-model comparison CLI
├── fact_checker_final.py          # CLI demo with optional BERT screen
├── evaluation/
│   ├── evaluate_covidfact.py      # COVID-Fact runner
│   ├── build_retrieval_cache.py   # Playwright cache builder
│   ├── prompts.py                 # Zero-shot / few-shot / UI prompts
│   └── metrics.py                 # Metrics + bootstrap + McNemar
├── tests/                         # Unit tests
├── docs/                          # Report, architecture, diagrams, future work
├── resources/                     # COVID-Fact paper + official TSV splits
└── fact_checker_bert/             # Optional local BERT weights
```

## Quick start

### 1. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Playwright uses the installed Microsoft Edge browser by default. If Edge is unavailable, install Chromium:

```powershell
.\.venv\Scripts\playwright.exe install chromium
```

### 2. LM Studio

1. Install LM Studio.
2. Download/load `liquid/lfm2.5-1.2b` and `qwen3-0.6b`.
3. Start the local server on `http://localhost:1234`.
4. Keep LM Studio running while using the app.

Both model ids are configurable in `.env`:

```text
DEFAULT_MODEL=liquid/lfm2.5-1.2b
SECOND_MODEL=qwen3-0.6b
REASONING_EFFORT=none
```

`REASONING_EFFORT=none` is important for Qwen3; otherwise it can spend the whole completion budget on hidden reasoning tokens and return an empty answer.

### 3. Run the UI

```powershell
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:7860`. For phone access on the same Wi-Fi, use the LAN address printed in the console. Public sharing is disabled by default; set `GRADIO_SHARE=True` only when needed.

### 4. Run the CLI demos

```powershell
.\.venv\Scripts\python.exe basic_rag.py
.\.venv\Scripts\python.exe advanced_rag.py
.\.venv\Scripts\python.exe fact_checker_final.py
```

### 5. Test retrieval directly

```powershell
.\.venv\Scripts\python.exe -m retrieval "COVID-19 vaccines reduce hospitalisation" --max-pages 2 --no-cache
```

## Evaluation

The dataset files are in `resources/COVID_FACT_DATASET/`:

- `train.tsv`: 3,263 rows
- `dev.tsv`: 419 rows
- `test.tsv`: 401 rows

Label mapping:

| Dataset value | Output label |
|---|---|
| `entailment` | `SUPPORTED` |
| `not_entailment` | `REFUTED` |

Run the full test gold evaluation:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --mode gold --prompt both `
  --model liquid/lfm2.5-1.2b --model qwen3-0.6b
```

Rebuild the summary from existing raw JSONL files:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact --summary-only
```

Build and use a 60-example retrieval sample:

```powershell
.\.venv\Scripts\python.exe -m evaluation.build_retrieval_cache `
  --split test --sample 60 --sample-seed 42 --max-pages 2

.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --sample 60 --sample-seed 42 --mode retrieved `
  --prompt few_shot --model liquid/lfm2.5-1.2b

.\.venv\Scripts\python.exe -m evaluation.evaluate_covidfact `
  --split test --sample 60 --sample-seed 42 --mode retrieved `
  --prompt zero_shot --model qwen3-0.6b
```

Evaluation details, per-class metrics, confidence intervals, and the McNemar comparison are in [docs/EVALUATION.md](docs/EVALUATION.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover strict label parsing, dataset integrity, metric calculations, and evidence utility functions.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation methodology and results](docs/EVALUATION.md)
- [Retrieval design](docs/RETRIEVAL.md)
- [Full project report draft](docs/REPORT.md)
- [Future work and hosted frontend plan](docs/FUTURE_WORK.md)
- Diagrams: [live pipeline](docs/diagrams/live_pipeline.png), [evaluation pipeline](docs/diagrams/evaluation_pipeline.png), [system architecture](docs/diagrams/system_architecture.png)

## Limitations

- Full retrieval evaluation is a 60-example stratified sample in this fast-path run; the gold evaluation is full 401-example.
- Live search results are time-sensitive and depend on search-engine behavior.
- Small quantized models are highly prompt-sensitive; LFM benefits from few-shot examples while Qwen is hurt by the same examples.
- No human evaluation of reason/citation faithfulness was performed.
- The optional BERT screen is a hint only; its local weights do not expose explicit `id2label` metadata.

## Dataset and citation

Arkadiy Saakyan, Tuhin Chakrabarty, and Smaranda Muresan. 2021.
COVID-Fact: Fact Extraction and Verification of Real-World Claims on COVID-19 Pandemic.
ACL-IJCNLP 2021, pages 2116–2129.

- Paper: https://aclanthology.org/2021.acl-long.165/
- Official code/data: https://github.com/asaakyan/covidfact

The paper PDF and official TSV splits are included in `resources/`. See `resources/README.md` for the label mapping and citation.

## Next deliverable

The planned next step is a hosted static frontend with the laptop as the backend: a small FastAPI service around `pipeline.py`, exposed through Cloudflare Tunnel or ngrok, with LM Studio running locally. See [docs/FUTURE_WORK.md](docs/FUTURE_WORK.md) for the API sketch, security checklist, and deployment plan.
