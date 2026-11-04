# Factly deployment guide

This guide covers the local one-command stage demo and the optional hosted frontend.

## Local stage demo

Run this from the project root:

```powershell
python demo.py
```

The launcher:

1. finds `lms.exe` and starts the LM Studio server if needed;
2. selects and preloads one model (`liquid/lfm2.5-1.2b` by default);
3. starts FastAPI and serves the UI at `http://127.0.0.1:8000/ui/`;
4. runs one warm-up `/check` request;
5. opens the browser.

Press **Ctrl+C** to stop the API and the LM Studio server together. The command needs no tunnel, GitHub Pages, or access code. Choosing another model from the UI calls `/models/select`, which unloads the current model before loading the new one.

`demo.py` sets `LOCAL_DEMO=true` for its API process. Loopback requests skip the access-code prompt; requests arriving through a tunnel still require the configured code.

## Optional hosted architecture

This path runs the hosted Factly frontend on GitHub Pages and the live fact-checking backend on the laptop.

```text
Browser (HTTPS)
      |
      v
GitHub Pages static site
      |
      v  HTTPS request with X-Access-Code
Cloudflare Quick Tunnel
      |
      v
FastAPI on 127.0.0.1:8000
      |
      +--> Playwright retrieval
      +--> SBERT + FAISS evidence ranking
      +--> LM Studio on 127.0.0.1:1234
```

The browser never calls LM Studio directly. LM Studio and the Playwright browser stay local.

## Prerequisites

- Windows laptop with Python 3.11+ and Microsoft Edge
- LM Studio with `liquid/lfm2.5-1.2b` and `qwen3-0.6b`
- `cloudflared` for the public tunnel
- `gh` CLI logged in to GitHub, or access to the repository settings

## 1. Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If Edge is not installed, install Playwright's Chromium fallback:

```powershell
.\.venv\Scripts\playwright.exe install chromium
```

Create `.env` from `.env.example` and set at least:

```text
ACCESS_CODE=your-shared-demo-code
API_ALLOWED_ORIGINS=https://darkstrike03.github.io,http://127.0.0.1:5500
```

The access code is a shared demo gate, not user authentication. Do not reuse a real password.

## 2. Start LM Studio

1. Open LM Studio.
2. Load a chat model.
3. Start the local server on port `1234`.
4. Confirm `http://127.0.0.1:1234/v1/models` responds.

## 3. Start the backend

```powershell
.\scripts\start_backend.ps1
```

Or directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The API is bound to `127.0.0.1`; it is not reachable from the LAN without the tunnel.

## 4. Test the frontend locally

```powershell
.\scripts\start_frontend.ps1
```

Open `http://127.0.0.1:5500/`, choose **Connection settings**, and enter:

- Backend URL: `http://127.0.0.1:8000`
- Access code: the value of `ACCESS_CODE`

Run one check before deploying.

## 5. Publish the static site

The site lives in `docs/` so GitHub Pages can serve it without a build step.

1. Push the repository to `main`.
2. Open **Settings → Pages**.
3. Set **Source** to **Deploy from a branch**.
4. Select branch `main` and folder `/docs`.
5. Save.

Expected URL:

```text
https://darkstrike03.github.io/Fact-checker/
```

If using the GitHub CLI, try:

```powershell
gh api --method POST repos/Darkstrike03/Fact-checker/pages `
  -f "source[branch]=main" `
  -f "source[path]=/docs"
```

If the Pages API rejects the request, enable Pages manually in the repository settings.

## 6. Start the public tunnel

```powershell
.\scripts\start_tunnel.ps1
```

Or directly:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Copy the generated `https://…trycloudflare.com` URL.

Quick Tunnel URLs are temporary and change every time the tunnel restarts. For the demo:

1. Open the hosted site.
2. Choose **Connection settings**.
3. Paste the current tunnel URL and the access code.
4. Save and run a check.

If you want all visitors to get the current URL automatically, update `docs/config.js`:

```js
apiBaseUrl: "https://your-current-tunnel.trycloudflare.com",
```

Then commit and push. Visitors still enter the access code themselves.

## 7. Verify from a phone

1. Disable Wi-Fi and use mobile data.
2. Open the GitHub Pages URL.
3. Set the tunnel URL and access code.
4. Run a claim and confirm the two model verdicts and source cards appear.

## Security model

Factly is a **research demo**, not a production authentication system.

- `ACCESS_CODE` is a shared demo gate, not a user account or password. The API requires at least 16 characters, but anyone who has the code can call `/check` and `/compare`.
- The hosted page stores the backend URL and access code in browser `localStorage`. Use a dedicated demo code and rotate it if it is shared beyond the demo audience.
- Failed authentication attempts count toward the per-IP rate limit. The limiter is in-memory and single-process, so it is not a defense against distributed abuse.
- `LOCAL_DEMO=true` skips the access code only for requests whose socket address is loopback and which do not carry forwarding headers. It does not bypass auth for tunneled traffic.
- `/health`, `/models`, and `/evaluation/summary` are public so the frontend can show status and results. `/check` and `/compare` require the access code.
- CORS restricts browser calls to the configured origins, but CORS is not authentication. Non-browser clients can call the tunnel directly if they know the URL and code.
- Cloudflare terminates TLS for the Quick Tunnel and can see request and response bodies. Do not submit sensitive or personal claims. A named tunnel with Cloudflare Access is the upgrade path if real access control is needed.
- Retrieved web pages are untrusted input to the language models. A malicious page could contain prompt-injection text or misleading evidence; the system can still return a wrong verdict.
- The API returns generic pipeline errors to clients and logs details locally. LM Studio stays on localhost.
- The frontend uses a strict Content-Security-Policy, renders untrusted text with `textContent`, and only opens `http`/`https` source links with `noopener noreferrer`.
- No third-party JavaScript is loaded. Google Fonts is the only external frontend dependency.
- Quick Tunnel URLs are public and unguessable, but they are not access control and change on restart. The API also binds to localhost and rejects oversized request bodies.

### Residual risks

- Shared-code leakage through screenshots, browser storage, or a compromised machine.
- Availability: laptop sleep, Wi-Fi changes, LM Studio crashes, or tunnel restarts take the demo offline.
- Prompt injection or false evidence from live search results.
- No human review of every generated reason and citation.
- Rate limiting can be bypassed with many source IPs.

## Security checklist

- [ ] `ACCESS_CODE` is at least 16 characters and is not a real account password.
- [ ] `API_ALLOWED_ORIGINS` contains only the GitHub Pages origin and local test origins.
- [ ] LM Studio is bound to localhost and never exposed by the tunnel.
- [ ] The API binds to `127.0.0.1`, not `0.0.0.0`.
- [ ] Rate limits are enabled (`API_RATE_LIMIT`, `API_RATE_WINDOW`).
- [ ] `.env` is never committed.
- [ ] The shared code is not posted in screenshots or public chat.
- [ ] The laptop is awake, online, and plugged in during the demo.
- [ ] Cloudflare Quick Tunnel downtime is expected; the site shows a clear offline state.

## Troubleshooting

| Symptom | Check |
|---|---|
| `Backend offline` | API process, tunnel URL, and `API_ALLOWED_ORIGINS` |
| `401` | Access code in the site settings matches `ACCESS_CODE` |
| `503 API access code is not configured` | Set `ACCESS_CODE` in `.env` and restart the API |
| `429` | Wait for the rate-limit window, or raise `API_RATE_LIMIT` |
| `504` | Live retrieval exceeded `API_REQUEST_TIMEOUT`; retry or shorten the claim |
| LM Studio offline | Start the LM Studio server and load a chat model |
| GitHub Pages 404 | Pages source must be branch `main`, folder `/docs` |
| CORS error | Add the exact frontend origin to `API_ALLOWED_ORIGINS` |
| Cloudflare 524 | The origin took too long; reduce retrieval pages or retry |

## Shutdown

Stop the tunnel, the API, and LM Studio when finished. Stop the local static server if it is running. The GitHub Pages site remains available but will show the backend as offline.
