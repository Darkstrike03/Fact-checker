# Future work

## 1. Hosted frontend with laptop backend

This is the next deliverable after the current project scope. The intended user experience is simple:

1. Open the hosted website.
2. Start LM Studio on the laptop and load a model.
3. The website talks to a small backend running on the laptop.
4. The backend calls the existing `pipeline` and returns the result.

### Recommended deployment shape

```text
Browser (HTTPS)
      |
      v
Static frontend (GitHub Pages / Netlify / Vercel)
      |
      v  HTTPS API request
Cloudflare Tunnel or ngrok
      |
      v
FastAPI backend on the laptop (127.0.0.1:8000)
      |
      +--> pipeline.check_claim / compare_models
      +--> Playwright retrieval
      +--> LM Studio at 127.0.0.1:1234
```

The browser must call an **HTTPS API endpoint**, not `http://localhost:1234` directly. A page served over HTTPS cannot reliably call a plain HTTP localhost endpoint, and LM Studio's API should not be exposed to the internet directly.

### Backend API sketch

```text
GET  /health                 -> backend + LM Studio status
GET  /models                 -> available chat models
POST /check                  -> {claim, model, use_bert}
POST /compare                -> {claim, primary_model, secondary_model}
GET  /evaluation/summary     -> cached results markdown/json
```

Implementation notes:

- Keep `pipeline.py` as the single orchestration layer; the API should be a thin wrapper.
- Add an API token or simple auth header so the tunnel is not an open relay.
- Add per-IP rate limiting and a maximum claim length.
- Add request timeouts and return structured errors.
- Allow only the deployed frontend origin in CORS.
- Do not expose the LM Studio port or the Playwright browser debugging port.
- Add a health endpoint that reports whether LM Studio is reachable and which model is loaded.
- Keep the backend awake; laptop sleep or Wi-Fi changes will break the tunnel.
- Cloudflare Tunnel is preferred over ngrok for a stable hostname and no browser warning page.

### Frontend scope

- Claim input and model selector.
- Two-column comparison view for the two models.
- Label badges: `SUPPORTED` / `REFUTED`, plus a clear “No verdict” state when evidence is insufficient.
- Evidence cards with source title, URL, and selected sentences.
- Raw-output disclosure for debugging.
- Architecture/pipeline page and evaluation summary page.
- Loading states with a warning that live retrieval can take 20–40 seconds.

### Deployment checklist

- [ ] Add `api.py` with FastAPI endpoints around `pipeline`.
- [ ] Add CORS, auth, rate limiting, and request size limits.
- [ ] Add a static `frontend/` or separate frontend repository.
- [ ] Configure the backend URL through a frontend environment variable.
- [ ] Start LM Studio and load a model before opening the site.
- [ ] Run the tunnel and verify HTTPS from a phone on mobile data.
- [ ] Add a “backend offline” state to the frontend.

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
