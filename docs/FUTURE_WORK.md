# Future work

## 1. Hosted frontend with laptop backend

Status: **implemented locally; GitHub Pages and public-tunnel verification remain**.

The Factly static frontend lives in `docs/`, the FastAPI wrapper is `api.py`, and the runbook is `docs/DEPLOYMENT.md`.

### Deployment shape

```text
Browser (HTTPS)
      |
      v
GitHub Pages static frontend (docs/)
      |
      v  HTTPS API request + X-Access-Code
Cloudflare Quick Tunnel
      |
      v
FastAPI backend on the laptop (127.0.0.1:8000)
      |
      +--> pipeline.check_claim / compare_models
      +--> Playwright retrieval
      +--> LM Studio at 127.0.0.1:1234
```

The browser calls the tunnel endpoint, never LM Studio directly. The API binds to localhost, uses a shared access code, per-IP rate limiting, a maximum claim length, request timeouts, and a CORS allowlist.

### Implemented

- [x] `api.py` with `/health`, `/models`, `/evaluation/summary`, `/check`, and `/compare`.
- [x] CORS, access-code authentication, rate limiting, and request size limits.
- [x] Static `docs/` frontend with a Gemini-inspired original design.
- [x] Backend URL and access code configurable in the site settings.
- [x] Evaluation summary page and architecture page.
- [x] “Backend offline” and loading states.
- [x] Local startup scripts and deployment guide.
- [x] Local mocked and real-API browser tests.

### Remaining deployment checks

- [ ] Enable GitHub Pages from `main` / `/docs`.
- [ ] Start the Cloudflare Quick Tunnel.
- [ ] Verify the hosted site from a phone on mobile data.
- [ ] Replace the local demo access code with a deployment code.
- [ ] Confirm LM Studio and the API stay awake for the demo window.

## 2. Evaluation improvements

- Run the full 401-claim retrieved-evidence benchmark, not only the 60-example sample.
- Evaluate `claim_only` for both models on the full test split.
- Add a properly fine-tuned transformer baseline on the same splits.
- Run multiple few-shot seeds and report mean ± standard deviation.
- Add calibration metrics and an abstention threshold.
- Add retrieval metrics (precision/recall/F1 against the gold evidence) alongside end-to-end label metrics.
- Include a second annotator or human spot-check of reasons and citations.
- Cache multiple retrieval snapshots and report date-stamped results.

## 3. Model and prompt improvements

- Test additional small instruction models (Gemma 3 1B, Llama 3.2 1B, Phi-3.5-mini).
- Compare prompt formats: label-only, label plus short reason, and structured JSON.
- Add a verifier prompt that checks entity/number substitutions explicitly.
- Add self-consistency voting across a few temperature samples.
- Add a retrieval query rewriter for long or complex claims.
- Add an evidence sufficiency check before classification.

## 4. Product features

- User accounts and saved checks.
- Shareable result links with evidence snapshots.
- WhatsApp/Telegram bot frontend.
- Multilingual claims and evidence.
- Browser extension or share-sheet integration.
- Admin dashboard for evaluation runs and cache health.
- Optional local-only mode that never sends claims to a hosted service.

## 5. Hooks already present

The current code already leaves room for these extensions:

- model ids and backend URL are environment-configured in `config.py`;
- `pipeline.check_claim` and `pipeline.compare_models` are reusable from an API;
- retrieval caching is isolated in `retrieval.py`;
- evaluation prompts and metrics are separate modules;
- `ABSTAIN` is reserved in the label policy and is not mapped to a dataset label;
- the BERT screen is optional and lazy-loaded;
- the evaluation summary is available to the UI as Markdown.
