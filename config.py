"""Shared configuration for the FACT_CHECKER project."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
LM_STUDIO_URL = os.getenv(
    "LM_STUDIO_URL", f"{LM_STUDIO_BASE_URL}/chat/completions"
)
LM_STUDIO_MODELS_URL = os.getenv(
    "LM_STUDIO_MODELS_URL", f"{LM_STUDIO_BASE_URL}/models"
)

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "liquid/lfm2.5-1.2b")
SECOND_MODEL = os.getenv("SECOND_MODEL", "qwen3-0.6b")
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "none")

RESOURCES_DIR = BASE_DIR / "resources"
DATASET_DIR = RESOURCES_DIR / "COVID_FACT_DATASET"
PAPER_PDF = RESOURCES_DIR / "COVID_FACT_PAPER.pdf"
PAPER_TEXT = RESOURCES_DIR / "COVID_FACT_PAPER.md"

CACHE_DIR = BASE_DIR / "cache"
RETRIEVAL_CACHE_DIR = CACHE_DIR / "retrieval"
EVALUATION_DIR = BASE_DIR / "evaluation"
RESULTS_DIR = EVALUATION_DIR / "results"
RAW_RESULTS_DIR = RESULTS_DIR / "raw"
DOCS_DIR = BASE_DIR / "docs"
DIAGRAMS_DIR = DOCS_DIR / "diagrams"
ASSETS_DIR = BASE_DIR / "assets"

LOCAL_BERT_DIR = BASE_DIR / "fact_checker_bert"
_bert_default = (
    str(LOCAL_BERT_DIR)
    if LOCAL_BERT_DIR.exists()
    else "DarkStrike/fact-checker-bert"
)
BERT_MODEL_PATH = os.getenv("BERT_MODEL_PATH", _bert_default)

PLAYWRIGHT_CHANNEL = os.getenv("PLAYWRIGHT_CHANNEL", "msedge")
RETRIEVAL_MAX_RESULTS = _env_int("RETRIEVAL_MAX_RESULTS", 5)
RETRIEVAL_MAX_PAGES = _env_int("RETRIEVAL_MAX_PAGES", 3)
RETRIEVAL_TIMEOUT_MS = _env_int("RETRIEVAL_TIMEOUT_MS", 15000)
RETRIEVAL_CACHE_DAYS = _env_int("RETRIEVAL_CACHE_DAYS", 7)

GRADIO_SERVER_NAME = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
GRADIO_SERVER_PORT = _env_int("GRADIO_SERVER_PORT", 7860)
GRADIO_SHARE = os.getenv("GRADIO_SHARE", "False").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

LABELS = ("SUPPORTED", "REFUTED")
LABEL_MAP = {
    "entailment": "SUPPORTED",
    "not_entailment": "REFUTED",
    "supported": "SUPPORTED",
    "refuted": "REFUTED",
}

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

DEFAULT_TOP_K = 5
DEFAULT_LLM_TIMEOUT = 180
DEFAULT_LLM_TEMPERATURE = 0.0


def ensure_directories() -> None:
    """Create runtime directories that are intentionally git-ignored."""
    for path in (
        CACHE_DIR,
        RETRIEVAL_CACHE_DIR,
        RESULTS_DIR,
        RAW_RESULTS_DIR,
        DOCS_DIR,
        DIAGRAMS_DIR,
        ASSETS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
