# Retrieval cache snapshots

`covidfact_test_sample60.json.gz` is the dated Playwright retrieval snapshot used by the fast-path retrieval evaluation.

- Split: `test`
- Sample: 60 claims, stratified by gold label, seed 42
- Composition: 19 `SUPPORTED` / 41 `REFUTED`
- Pages fetched per claim: up to 2
- Build date: 2026-11-04
- Provider mix: 8 Brave page-text results, 47 Google News RSS snippet results, 5 failures
- Claims with at least one snippet: 55
- Claims with fetched page sentences: 8

The snapshot stores extracted sentences and snippets, not raw HTML. Because only 8 claims resolved through a fetched page, the retrieval evaluation is mostly a search-snippet check, not a full page-fetch benchmark.

Regenerate with:

```powershell
.\.venv\Scripts\python.exe -m evaluation.build_retrieval_cache `
  --split test --sample 60 --sample-seed 42 --max-pages 2
```
