# Retrieval

## Goal

The retrieval layer replaces the earlier hosted search API with a local, Playwright-based pipeline. It must return enough grounded evidence for small models to make a binary COVID-Fact decision without using parametric memory.

## Search providers

| Priority | Provider | How it is accessed | Notes |
|---|---|---|---|
| 1 | Brave Search | Playwright, `search.brave.com` HTML | Primary; rate-limited during the 60-claim build |
| 2 | Google News RSS | HTTP RSS, no key | Fallback for news-style claims; handled 47/60 |
| 3 | Wikipedia API | HTTP JSON, no key | Last-resort encyclopedic fallback |

Bing and DuckDuckGo were tested and rejected:

- Bing returned unrelated, poisoned results to headless Playwright.
- DuckDuckGo's HTML endpoint returned an outage page.
- Startpage and Mojeek showed CAPTCHA/verification pages.

## Page fetching

`fetch_page_text()` uses Playwright to load a page, blocks images, media, fonts, and stylesheets, extracts readable text with `trafilatura`, and falls back to BeautifulSoup. URLs ending in PDFs, images, archives, or office files are skipped.

Pages are converted into sentences with `evidence.split_sentences`:

- split on sentence-ending punctuation;
- remove bullets and extra whitespace;
- drop sentences shorter than 20 characters;
- deduplicate normalized sentences;
- cap at 120 sentences per page.

## Ranking

`evidence.rank_sentences()`:

1. flattens page sentences and snippets into candidates;
2. embeds the claim and candidates with `sentence-transformers/all-MiniLM-L6-v2`;
3. normalizes vectors;
4. searches `faiss.IndexFlatIP` for cosine similarity;
5. returns the top `RETRIEVAL_TOP_K` sentences with source metadata.

If the embedding model cannot be loaded, a lexical-overlap fallback keeps the app usable. This fallback is a safety net, not the reported method.

## Caching

| Path | Purpose | Git |
|---|---|---|
| `cache/retrieval/search/` | Search result JSON cache | Ignored |
| `cache/retrieval/pages/` | Page text/sentence JSON cache | Ignored |
| `evaluation/retrieval_cache/` | Curated evaluation snapshots | Committed |

The cache key includes the query, result count, and page count. Default cache age is 7 days. Evaluation snapshots are compressed JSON (`.json.gz`) and store only the extracted sentences/snippets, not raw HTML.

## Commands

```powershell
# Smoke-test the live retrieval path
.\.venv\Scripts\python.exe -m retrieval "COVID-19 vaccines reduce hospitalisation" --max-pages 2 --no-cache

# Build a 60-example stratified test cache
.\.venv\Scripts\python.exe -m evaluation.build_retrieval_cache `
  --split test --sample 60 --sample-seed 42 --max-pages 2

# Resume an interrupted build (same command; existing items are skipped)
.\.venv\Scripts\python.exe -m evaluation.build_retrieval_cache `
  --split test --sample 60 --sample-seed 42 --max-pages 2
```

## Failure modes

- Search engines can rate-limit or block headless browsers. In the 60-claim build, only 8 claims resolved through Brave page text; 47 fell back to Google News RSS snippets and 5 returned no result.
- Some pages are paywalled or JavaScript-heavy; the extractor may return zero sentences. Search snippets are used as a fallback, so snippet-only evidence is not equivalent to full-page retrieval.
- Live retrieval is inherently time-sensitive. The report treats retrieval evaluation as a dated snapshot, not a permanent benchmark.
- A full 401-claim page-fetch run is expensive on a laptop; the fast path uses a 60-claim stratified sample and reports it as a sample, not as a full replacement for the paper's retrieval experiment.
