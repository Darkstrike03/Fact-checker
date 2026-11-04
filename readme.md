# Factly - Evidence-First Claim Checker

**4th Year Project | Dept. of Computer Science & Engineering | RCCIIT**

Faculty Supervisor: Dr. Anup Kumar Kolya

Factly is a retrieval-grounded fact-checking system for social-media claims. The system uses local Playwright-based web retrieval, SBERT + FAISS evidence ranking, and a small quantized model served by LM Studio. Live verdicts use **SUPPORTED**, **REFUTED**, or **UNVERIFIED**, always with an answer-first explanation and citations. COVID-Fact remains the labelled reference benchmark for evaluating the retrieval and classification pipeline.

## Stage demo: one command

Prerequisites: the `.venv` is installed and at least one supported model is already downloaded in LM Studio.

```powershell
python demo.py
```

The launcher automatically:

1. starts the LM Studio server if needed;
2. selects and preloads one model at a time;
3. starts the API and serves the Factly UI at `http://127.0.0.1:8000/ui/`;
4. warms up retrieval and the selected model with one sample claim;
5. opens the browser.

Keep the terminal open during the demo. Press **Ctrl+C** to stop the API and the LM Studio server together.

This path is local-only: no GitHub Pages, no tunnel, and no access-code typing.

## Optional hosted website

- Frontend: `https://darkstrike03.github.io/Fact-checker/`
- The hosted page connects to a laptop backend through a Cloudflare Quick Tunnel. Enter the current tunnel URL and shared access code in the site's **Connection settings**.
- Deployment, security, and troubleshooting steps: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

The Gemini-inspired interface is an original Factly design; it is not affiliated with or endorsed by Google.

The shared access code is a demo gate, not user authentication. See the [security model](docs/DEPLOYMENT.md#security-model) before sharing the tunnel URL.

## What it does

- Searches the web with Playwright (Brave Search primary, Google News RSS and Wikipedia fallbacks).
- Fetches and extracts page text with `trafilatura`, including publication dates when available.
- Ranks evidence sentences with `all-MiniLM-L6-v2` and FAISS cosine similarity.
- Sends the top five passages to one selected LM Studio model and asks for an answer-first verdict: **SUPPORTED**, **REFUTED**, or **UNVERIFIED**.
- Applies deterministic date, entity, source-count, and citation checks; unsupported model verdicts are downgraded to **UNVERIFIED**.
- Shows the answer, confidence, reason, citations, the five passages used, a wider set of retrieved candidates, and run metadata.
- Switches between supported models without ever loading both at once.
- Provides a reproducible evaluation harness for the official COVID-Fact splits.

## Results

The following numbers are from the labelled COVID-Fact reference benchmark, not a social-media benchmark. Full test split, gold evidence, 401 examples per configuration:

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
├── demo.py                        # One-command local stage demo
├── api.py                         # FastAPI backend and local UI host
├── app.py                         # Local Gradio UI
├── pipeline.py                    # Live orchestration + evidence selection
├── verification.py                # Date, entity, source, and citation guards
├── model_manager.py               # One-model-at-a-time LM Studio control
├── retrieval.py                   # Playwright search + page fetch
├── evidence.py                    # Sentence splitting + SBERT/FAISS ranking
├── llm_client.py                  # LM Studio client + live/dataset parsers
├── config.py                      # Paths, models, environment settings
├── basic_rag.py                   # Stage 1 CLI demo
├── advanced_rag.py                # Research CLI for model comparison
├── fact_checker_final.py          # Legacy CLI demo
├── docs/
│   ├── index.html                 # Factly static frontend
│   ├── app.js                     # Frontend logic
│   ├── styles.css                 # Gemini-inspired design
│   ├── DEPLOYMENT.md              # Pages + tunnel runbook
│   └── diagrams/                  # Architecture diagrams
├── scripts/                       # Backend, frontend, tunnel launchers
├── evaluation/
│   ├── evaluate_covidfact.py      # COVID-Fact runner
│   ├── build_retrieval_cache.py   # Playwright cache builder
│   ├── prompts.py                 # Zero-shot / few-shot / UI prompts
│   └── metrics.py                 # Metrics + bootstrap + McNemar
├── tests/                         # Existing parser/metric/evidence tests
└── resources/                     # COVID-Fact paper + official TSV splits
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
2. Download `liquid/lfm2.5-1.2b` and optionally `qwen3-0.6b`.
3. The one-command demo starts the local server and loads only the selected model.

Both model ids are configurable in `.env`:

```text
DEFAULT_MODEL=liquid/lfm2.5-1.2b
SECOND_MODEL=qwen3-0.6b
REASONING_EFFORT=none
```

`REASONING_EFFORT=none` is important for Qwen3; otherwise it can spend the whole completion budget on hidden reasoning tokens and return an empty answer.

### 3. Run the optional Gradio UI

```powershell
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:7860`. For phone access on the same Wi-Fi, use the LAN address printed in the console. Public sharing is disabled by default; set `GRADIO_SHARE=True` only when needed.

### 4. Run the one-command stage demo

```powershell
python demo.py
```

The script starts LM Studio, preloads one model, pre-warms the pipeline, serves the UI at `http://127.0.0.1:8000/ui/`, and opens the browser. Press **Ctrl+C** to stop everything it started. Select the other model from the UI to switch; Factly unloads the previous model first.

For the optional separate API/frontend and hosted-tunnel workflow, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### 5. Run the CLI demos

```powershell
.\.venv\Scripts\python.exe basic_rag.py
.\.venv\Scripts\python.exe advanced_rag.py
.\.venv\Scripts\python.exe fact_checker_final.py
```

### 6. Test retrieval directly

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
- [Deployment guide](docs/DEPLOYMENT.md)
- [Future work](docs/FUTURE_WORK.md)
- Diagrams: [live pipeline](docs/diagrams/live_pipeline.png), [evaluation pipeline](docs/diagrams/evaluation_pipeline.png), [system architecture](docs/diagrams/system_architecture.png)

## Limitations

- Full retrieval evaluation is a 60-example stratified sample in this fast-path run; the gold evaluation is full 401-example.
- Live search results are time-sensitive and depend on search-engine behavior.
- Small quantized models are highly prompt-sensitive; LFM benefits from few-shot examples while Qwen is hurt by the same examples.
- No human evaluation of reason/citation faithfulness was performed.
- No labelled social-media benchmark exists yet, so live social-media performance is qualitative; COVID-Fact is the reference stress test.
- Date and entity guards are deliberately conservative and can downgrade a true claim when sources omit a matching date or use synonyms.
- The public demo depends on the laptop staying online with LM Studio and the API running.
- Cloudflare Quick Tunnel URLs change on restart; users may need to update the backend URL in the site settings.
- The shared access code is a demo gate, not user authentication.

## Dataset and citation

Arkadiy Saakyan, Tuhin Chakrabarty, and Smaranda Muresan. 2021.
COVID-Fact: Fact Extraction and Verification of Real-World Claims on COVID-19 Pandemic.
ACL-IJCNLP 2021, pages 2116–2129.

- Paper: https://aclanthology.org/2021.acl-long.165/
- Official code/data: https://github.com/asaakyan/covidfact

The paper PDF and official TSV splits are included in `resources/`. See `resources/README.md` for the label mapping and citation.

## Hosted demo status

GitHub Pages is configured for the `/docs` folder. Push the latest revision to redeploy the static frontend, then start the Cloudflare Quick Tunnel and enter its URL in the site's connection settings. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
