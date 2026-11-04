"""FastAPI backend for the hosted Factly frontend."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import config
import llm_client
import pipeline

APP_NAME = "Factly API"
APP_VERSION = "1.0.0"
MAX_REQUEST_BYTES = 16_384
MIN_ACCESS_CODE_LENGTH = 16

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.API_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Access-Code"],
    max_age=600,
)


@app.middleware("http")
async def reject_oversized_bodies(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > MAX_REQUEST_BYTES
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length."}
                )
            if too_large:
                return JSONResponse(
                    status_code=413, content={"detail": "Request body too large."}
                )
    return await call_next(request)


_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for", ""
    )
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_loopback(request: Request) -> bool:
    if request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for"):
        return False
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def _require_access_code(
    request: Request,
    x_access_code: str | None = Header(default=None, alias="X-Access-Code"),
) -> None:
    if config.LOCAL_DEMO and _is_loopback(request):
        return
    expected = config.ACCESS_CODE
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API access code is not configured. Set ACCESS_CODE in .env.",
        )
    if len(expected) < MIN_ACCESS_CODE_LENGTH:
        raise HTTPException(
            status_code=503,
            detail=(
                "API access code is too short. "
                f"Use at least {MIN_ACCESS_CODE_LENGTH} characters."
            ),
        )
    if not x_access_code or not hmac.compare_digest(x_access_code, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing access code.")


def _rate_limit(request: Request) -> None:
    now = time.monotonic()
    key = _client_ip(request)
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and now - bucket[0] >= config.API_RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= config.API_RATE_LIMIT:
            retry_after = max(
                1, int(config.API_RATE_WINDOW - (now - bucket[0]))
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


class ClaimRequest(BaseModel):
    claim: str = Field(
        ...,
        min_length=3,
        max_length=config.API_MAX_CLAIM_CHARS,
        description="COVID-19 claim to check.",
    )
    model: str | None = Field(default=None, max_length=160)
    use_bert: bool = False

    @field_validator("claim")
    @classmethod
    def clean_claim(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Claim is too short.")
        if len(cleaned) > config.API_MAX_CLAIM_CHARS:
            raise ValueError(
                f"Claim is longer than {config.API_MAX_CLAIM_CHARS} characters."
            )
        return cleaned


class CompareRequest(BaseModel):
    claim: str = Field(
        ...,
        min_length=3,
        max_length=config.API_MAX_CLAIM_CHARS,
        description="COVID-19 claim to check.",
    )
    primary_model: str | None = Field(default=None, max_length=160)
    secondary_model: str | None = Field(default=None, max_length=160)
    use_bert: bool = False

    @field_validator("claim")
    @classmethod
    def clean_claim(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Claim is too short.")
        if len(cleaned) > config.API_MAX_CLAIM_CHARS:
            raise ValueError(
                f"Claim is longer than {config.API_MAX_CLAIM_CHARS} characters."
            )
        return cleaned


def _public_evidence(evidence_bundle: dict[str, Any]) -> dict[str, Any]:
    retrieval = evidence_bundle.get("retrieval") or {}
    selected = []
    raw_selected = evidence_bundle.get("selected") or evidence_bundle.get(
        "selected_evidence"
    ) or []
    for item in raw_selected:
        selected.append(
            {
                "text": item.get("text", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "score": item.get("score"),
                "page_index": item.get("page_index"),
                "sentence_index": item.get("sentence_index"),
            }
        )
    return {
        "text": evidence_bundle.get("evidence_text", ""),
        "selected": selected,
        "provider": retrieval.get("provider"),
        "cached": bool(retrieval.get("cached")),
        "pages": len(retrieval.get("results") or []),
        "error": retrieval.get("error"),
    }


def _public_model_output(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": output.get("model", ""),
        "label": output.get("label"),
        "reason": output.get("reason", ""),
        "latency_seconds": output.get("latency_seconds", 0.0),
        "retried": bool(output.get("retried")),
        "raw_response": output.get("raw_response", ""),
    }


def _serialize_check(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": result.get("claim", ""),
        "mode": "check",
        "models": [_public_model_output(result)],
        "evidence": _public_evidence(result),
        "bert": result.get("bert"),
    }


def _serialize_compare(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": result.get("claim", ""),
        "mode": "compare",
        "models": [_public_model_output(item) for item in result.get("models", [])],
        "evidence": _public_evidence(result.get("evidence_bundle") or {}),
        "bert": result.get("bert"),
    }


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing result file: {path.name}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/")
def index() -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", dependencies=[Depends(_rate_limit)])
def health() -> dict[str, Any]:
    started = time.perf_counter()
    lm_studio: dict[str, Any]
    try:
        models = llm_client.list_models(timeout=4)
        chat_models = llm_client.list_chat_models(timeout=4)
        lm_studio = {
            "reachable": True,
            "chat_models": chat_models,
            "model_count": len(models),
        }
    except Exception:  # noqa: BLE001 - health must not raise
        logger.exception("LM Studio health check failed")
        lm_studio = {
            "reachable": False,
            "chat_models": [],
        }
    return {
        "status": "ok",
        "version": APP_VERSION,
        "local_demo": config.LOCAL_DEMO,
        "access_code_configured": bool(config.ACCESS_CODE),
        "lm_studio": lm_studio,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }


@app.get("/models", dependencies=[Depends(_rate_limit)])
def models() -> dict[str, Any]:
    try:
        chat_models = llm_client.list_chat_models(timeout=5)
    except Exception:  # noqa: BLE001 - return fallbacks instead
        chat_models = []
    fallbacks = [config.DEFAULT_MODEL, config.SECOND_MODEL]
    merged = list(dict.fromkeys([*chat_models, *fallbacks]))
    return {
        "models": merged,
        "default": config.DEFAULT_MODEL,
        "secondary": config.SECOND_MODEL,
    }


@app.get("/evaluation/summary")
def evaluation_summary() -> dict[str, Any]:
    gold = _load_json(config.RESULTS_DIR / "summary.json")
    retrieval = _load_json(
        config.RESULTS_DIR / "retrieval_sample" / "summary.json"
    )
    return {
        "gold": gold,
        "retrieval_sample": retrieval,
        "paper": {
            "roberta_gold_accuracy": 0.835,
            "roberta_gold_f1": 82.0,
            "roberta_top5_accuracy": 0.847,
            "roberta_top5_f1": 83.0,
            "claim_only_accuracy": 0.675,
            "claim_only_f1": 40.0,
            "covid_fever_accuracy": 0.433,
        },
    }


@app.post(
    "/check",
    dependencies=[Depends(_rate_limit), Depends(_require_access_code)],
)
async def check(request: ClaimRequest) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                pipeline.check_claim,
                request.claim,
                model=request.model,
                use_bert=request.use_bert,
            ),
            timeout=config.API_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The fact check timed out. Try a shorter claim or retry.",
        ) from exc
    except Exception:  # noqa: BLE001 - do not expose internal errors to clients
        logger.exception("Fact-check pipeline failed")
        raise HTTPException(
            status_code=502,
            detail="The fact-check pipeline failed. Please retry.",
        ) from None
    return _serialize_check(result)


@app.post(
    "/compare",
    dependencies=[Depends(_rate_limit), Depends(_require_access_code)],
)
async def compare(request: CompareRequest) -> dict[str, Any]:
    primary = request.primary_model or config.DEFAULT_MODEL
    secondary = request.secondary_model or config.SECOND_MODEL
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                pipeline.compare_models,
                request.claim,
                models=[primary, secondary],
                use_bert=request.use_bert,
            ),
            timeout=config.API_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The fact check timed out. Try a shorter claim or retry.",
        ) from exc
    except Exception:  # noqa: BLE001 - do not expose internal errors to clients
        logger.exception("Fact-check pipeline failed")
        raise HTTPException(
            status_code=502,
            detail="The fact-check pipeline failed. Please retry.",
        ) from None
    return _serialize_compare(result)


app.mount("/ui", StaticFiles(directory=config.DOCS_DIR, html=True), name="ui")
