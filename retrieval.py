"""Playwright-based web retrieval used by the live fact-checking pipeline."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests

import config

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
SKIP_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
    ".zip",
    ".doc",
    ".docx",
)
BLOCKED_HOSTS = ("bing.com", "duckduckgo.com", "microsoft.com", "go.microsoft.com")

_browser = None
_playwright = None
_browser_lock = threading.RLock()


class RetrievalError(RuntimeError):
    """Raised when Playwright cannot retrieve web evidence."""


def _ensure_cache_dirs() -> None:
    (config.RETRIEVAL_CACHE_DIR / "search").mkdir(parents=True, exist_ok=True)
    (config.RETRIEVAL_CACHE_DIR / "pages").mkdir(parents=True, exist_ok=True)


def _cache_key(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _load_cache(path: Path, max_age_days: float | None) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if max_age_days is not None:
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            age_seconds = (
                datetime.now(timezone.utc) - fetched_at
            ).total_seconds()
            if age_seconds > max_age_days * 86400:
                return None
        return payload
    except Exception:
        return None


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _start_playwright():
    global _playwright, _browser
    with _browser_lock:
        if _browser is not None and _browser.is_connected():
            return _browser

        from playwright.sync_api import sync_playwright

        if _playwright is None:
            _playwright = sync_playwright().start()

        channels = [config.PLAYWRIGHT_CHANNEL, "msedge", "chrome", None]
        seen: set[str | None] = set()
        errors: list[str] = []
        for channel in channels:
            if channel in seen:
                continue
            seen.add(channel)
            try:
                launch_options: dict[str, Any] = {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                }
                if channel:
                    launch_options["channel"] = channel
                _browser = _playwright.chromium.launch(**launch_options)
                return _browser
            except Exception as exc:  # noqa: BLE001 - try the next channel
                errors.append(f"{channel or 'bundled chromium'}: {exc}")

        raise RetrievalError(
            "Could not launch a Playwright browser. Install one with "
            "`playwright install chromium` or install Microsoft Edge. "
            + " | ".join(errors[:2])
        )


def _new_context(browser):
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        java_script_enabled=True,
    )
    context.set_default_timeout(config.RETRIEVAL_TIMEOUT_MS)

    def _route(route):
        if route.request.resource_type in {
            "image",
            "media",
            "font",
            "stylesheet",
        }:
            route.abort()
        else:
            route.continue_()

    context.route("**/*", _route)
    return context


def _clean_result(url: str, title: str, snippet: str) -> dict[str, str] | None:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    if any(host in parsed.netloc.lower() for host in BLOCKED_HOSTS):
        return None
    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return None
    title = re.sub(r"\s+", " ", unescape(title or "")).strip()
    snippet = re.sub(r"\s+", " ", unescape(snippet or "")).strip()
    if not title:
        title = parsed.netloc
    return {"title": title, "url": url, "snippet": snippet}


def _search_brave(page, query: str, max_results: int) -> list[dict[str, str]]:
    """Search Brave's HTML result page, which is reliable under Playwright."""
    url = (
        "https://search.brave.com/search?q="
        + quote_plus(query)
        + "&source=web"
    )
    page.goto(url, wait_until="domcontentloaded", timeout=config.RETRIEVAL_TIMEOUT_MS)
    try:
        page.wait_for_selector(".snippet", timeout=8000)
    except Exception:
        pass

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    items = page.locator(".snippet")
    count = min(items.count(), max_results * 4)
    for index in range(count):
        item = items.nth(index)
        try:
            link = item.locator("a[href]").first
            href = link.get_attribute("href") or ""
        except Exception:
            continue
        title = ""
        try:
            title_locator = item.locator(".title").first
            if title_locator.count():
                title = title_locator.inner_text(timeout=2000)
        except Exception:
            pass
        if not title:
            try:
                title = link.inner_text(timeout=2000)
            except Exception:
                title = ""
        snippet = ""
        try:
            snippet_locator = item.locator(".generic-snippet .content").first
            if snippet_locator.count():
                snippet = snippet_locator.inner_text(timeout=2000)
        except Exception:
            pass
        cleaned = _clean_result(href, title, snippet)
        if cleaned and cleaned["url"] not in seen:
            seen.add(cleaned["url"])
            results.append(cleaned)
        if len(results) >= max_results:
            break
    return results


def _search_google_news(query: str, max_results: int) -> list[dict[str, str]]:
    """Fallback search using Google News RSS (no API key)."""
    import xml.etree.ElementTree as ET

    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=config.RETRIEVAL_TIMEOUT_MS / 1000,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    results: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = re.sub(
            r"<[^>]+>",
            " ",
            item.findtext("description") or "",
        )
        cleaned = _clean_result(link, title, description)
        if cleaned:
            results.append(cleaned)
        if len(results) >= max_results:
            break
    return results


def _search_wikipedia(query: str, max_results: int) -> list[dict[str, str]]:
    """Last-resort encyclopedic fallback for well-established claims."""
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
        "&utf8=1&srlimit="
        + str(max_results)
        + "&srsearch="
        + quote_plus(query)
    )
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=config.RETRIEVAL_TIMEOUT_MS / 1000,
    )
    response.raise_for_status()
    payload = response.json()
    results: list[dict[str, str]] = []
    for item in payload.get("query", {}).get("search", []):
        title = item.get("title", "")
        snippet = re.sub(r"<[^>]+>", " ", item.get("snippet", ""))
        page_url = "https://en.wikipedia.org/wiki/" + quote_plus(
            title.replace(" ", "_")
        )
        cleaned = _clean_result(page_url, title, snippet)
        if cleaned:
            results.append(cleaned)
        if len(results) >= max_results:
            break
    return results


def search_web(
    query: str,
    max_results: int = config.RETRIEVAL_MAX_RESULTS,
    use_cache: bool = True,
    max_age_days: float | None = config.RETRIEVAL_CACHE_DAYS,
) -> dict[str, Any]:
    """Search Bing, then DuckDuckGo, using cached results when available."""
    _ensure_cache_dirs()
    cache_path = config.RETRIEVAL_CACHE_DIR / "search" / f"{_cache_key('search', query, max_results)}.json"
    if use_cache:
        cached = _load_cache(cache_path, max_age_days)
        if cached is not None:
            cached["cached"] = True
            return cached

    browser = _start_playwright()
    errors: list[str] = []
    payload: dict[str, Any] = {
        "query": query,
        "results": [],
        "provider": None,
        "cached": False,
        "error": None,
    }

    # Brave is the primary provider because it works under headless Playwright.
    context = _new_context(browser)
    page = context.new_page()
    try:
        results = _search_brave(page, query, max_results)
        if results:
            payload.update(
                {"results": results, "provider": "brave", "error": None}
            )
    except Exception as exc:  # noqa: BLE001 - fallback providers below
        errors.append(f"brave: {exc}")
    finally:
        context.close()

    if not payload["results"]:
        for provider, search_function in (
            ("google_news", _search_google_news),
            ("wikipedia", _search_wikipedia),
        ):
            try:
                results = search_function(query, max_results)
                if results:
                    payload.update(
                        {"results": results, "provider": provider, "error": None}
                    )
                    break
                errors.append(f"{provider}: no results")
            except Exception as exc:  # noqa: BLE001 - try the next provider
                errors.append(f"{provider}: {exc}")

    if errors and not payload["results"]:
        payload["error"] = " | ".join(errors)

    if use_cache:
        _save_cache(cache_path, payload)
    return payload


def _extract_text_from_html(html: str, url: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        if extracted and len(extracted.strip()) >= 80:
            return extracted
    except Exception:
        pass

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for element in soup(
            ["script", "style", "noscript", "nav", "footer", "header", "aside"]
        ):
            element.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:
        return ""


def fetch_page_text(
    url: str,
    use_cache: bool = True,
    max_age_days: float | None = config.RETRIEVAL_CACHE_DAYS,
) -> dict[str, Any]:
    """Fetch a page and return trafilatura-extracted text plus sentences."""
    _ensure_cache_dirs()
    parsed = urlparse(url)
    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return {"url": url, "text": "", "sentences": [], "error": "unsupported file type"}

    cache_path = config.RETRIEVAL_CACHE_DIR / "pages" / f"{_cache_key('page', url)}.json"
    if use_cache:
        cached = _load_cache(cache_path, max_age_days)
        if cached is not None:
            cached["cached"] = True
            return cached

    browser = _start_playwright()
    context = _new_context(browser)
    page = context.new_page()
    payload: dict[str, Any] = {
        "url": url,
        "text": "",
        "sentences": [],
        "error": None,
        "cached": False,
    }
    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=config.RETRIEVAL_TIMEOUT_MS,
        )
        page.wait_for_timeout(500)
        html = page.content()
        text = _extract_text_from_html(html, url)[:30000]
        from evidence import split_sentences

        payload["text"] = text
        payload["sentences"] = split_sentences(text)
    except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
        payload["error"] = str(exc)
    finally:
        context.close()

    if use_cache and payload["sentences"]:
        _save_cache(cache_path, payload)
    return payload


def search_and_fetch(
    query: str,
    max_results: int = config.RETRIEVAL_MAX_RESULTS,
    max_pages: int = config.RETRIEVAL_MAX_PAGES,
    use_cache: bool = True,
    max_age_days: float | None = config.RETRIEVAL_CACHE_DAYS,
) -> dict[str, Any]:
    """Search for a claim and fetch the top pages' candidate sentences."""
    _ensure_cache_dirs()
    cache_path = (
        config.RETRIEVAL_CACHE_DIR
        / "search"
        / f"{_cache_key('evidence', query, max_results, max_pages)}.json"
    )
    if use_cache:
        cached = _load_cache(cache_path, max_age_days)
        if cached is not None:
            cached["cached"] = True
            return cached

    search = search_web(
        query,
        max_results=max_results,
        use_cache=use_cache,
        max_age_days=max_age_days,
    )
    payload: dict[str, Any] = {
        "query": query,
        "provider": search.get("provider"),
        "results": [],
        "error": search.get("error"),
        "cached": False,
    }

    pages_to_fetch = (
        search.get("results", [])
        if max_pages <= 0
        else search.get("results", [])[:max_pages]
    )
    for result in pages_to_fetch:
        if max_pages <= 0:
            payload["results"].append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("snippet", ""),
                    "sentences": [],
                    "error": None,
                }
            )
            continue
        page = fetch_page_text(
            result["url"],
            use_cache=use_cache,
            max_age_days=max_age_days,
        )
        payload["results"].append(
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
                "sentences": page.get("sentences", []),
                "error": page.get("error"),
            }
        )

    if use_cache and payload["results"]:
        _save_cache(cache_path, payload)
    return payload


def close_browser() -> None:
    """Close the shared browser and Playwright driver."""
    global _browser, _playwright
    with _browser_lock:
        try:
            if _browser is not None:
                _browser.close()
        except Exception:
            pass
        try:
            if _playwright is not None:
                _playwright.stop()
        except Exception:
            pass
        _browser = None
        _playwright = None


atexit.register(close_browser)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Playwright retrieval.")
    parser.add_argument("query", help="Claim or search query")
    parser.add_argument("--max-results", type=int, default=config.RETRIEVAL_MAX_RESULTS)
    parser.add_argument("--max-pages", type=int, default=config.RETRIEVAL_MAX_PAGES)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    result = search_and_fetch(
        args.query,
        max_results=args.max_results,
        max_pages=args.max_pages,
        use_cache=not args.no_cache,
    )
    print(
        json.dumps(
            {
                "query": result["query"],
                "provider": result["provider"],
                "error": result["error"],
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "results": [
                    {
                        "title": item["title"],
                        "url": item["url"],
                        "sentences": len(item["sentences"]),
                        "error": item["error"],
                    }
                    for item in result["results"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
