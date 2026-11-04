"""Sentence splitting and semantic evidence ranking (SBERT + FAISS)."""

from __future__ import annotations

import re
import threading
from html import unescape
from typing import Any, Iterable

import config

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WHITESPACE = re.compile(r"\s+")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_embedder = None
_embedder_lock = threading.Lock()


def clean_text(text: str) -> str:
    return _WHITESPACE.sub(" ", unescape(str(text or ""))).strip()


def split_sentences(text: str, min_chars: int = 20, max_sentences: int = 120) -> list[str]:
    """Split page text into clean, deduplicated candidate evidence sentences."""
    text = clean_text(text)
    if not text:
        return []

    raw_parts = _SENTENCE_BOUNDARY.split(text)
    sentences: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        part = _BULLET_PREFIX.sub("", part).strip()
        if len(part) < min_chars:
            continue
        key = re.sub(r"[^a-z0-9]+", "", part.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        sentences.append(part)
        if len(sentences) >= max_sentences:
            break
    return sentences


def get_embedder():
    """Lazily load the sentence-transformer so imports and tests stay cheap."""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                from sentence_transformers import SentenceTransformer

                _embedder = SentenceTransformer(config.EMBEDDING_MODEL, device="cpu")
    return _embedder


def build_candidates(pages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten retrieved pages into sentence candidates with source metadata."""
    candidates: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        sentences = page.get("sentences") or []
        for sentence_index, sentence in enumerate(sentences):
            sentence = clean_text(sentence)
            if len(sentence) < 20:
                continue
            candidates.append(
                {
                    "text": sentence,
                    "title": clean_text(page.get("title", "")),
                    "url": page.get("url", ""),
                    "published_at": page.get("published_at", ""),
                    "page_index": page_index,
                    "sentence_index": sentence_index,
                }
            )
    return candidates


def rank_sentences(
    claim: str,
    candidates: Iterable[dict[str, Any]],
    top_k: int = config.DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Rank candidate sentences against a claim with cosine similarity."""
    candidates = list(candidates)
    if not candidates:
        return []

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", "", candidate["text"].lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    if len(deduped) <= top_k:
        for candidate in deduped:
            candidate["score"] = 0.0
        return deduped

    try:
        import faiss
        import numpy as np

        embedder = get_embedder()
        texts = [candidate["text"] for candidate in deduped]
        vectors = embedder.encode(
            texts,
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        query = embedder.encode(
            [claim],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")

        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        scores, indices = index.search(query, min(top_k, len(deduped)))

        ranked: list[dict[str, Any]] = []
        for score, index_value in zip(scores[0], indices[0]):
            if int(index_value) < 0:
                continue
            candidate = dict(deduped[int(index_value)])
            candidate["score"] = float(score)
            ranked.append(candidate)
        return ranked
    except Exception:
        # A deterministic lexical fallback keeps the app usable if the embedding
        # model cannot be downloaded.
        claim_terms = {
            term
            for term in re.findall(r"[a-z0-9]+", claim.lower())
            if len(term) > 3
        }

        def overlap(candidate: dict[str, Any]) -> float:
            terms = set(re.findall(r"[a-z0-9]+", candidate["text"].lower()))
            if not claim_terms:
                return 0.0
            return len(claim_terms & terms) / len(claim_terms)

        ranked = sorted(deduped, key=overlap, reverse=True)[:top_k]
        for candidate in ranked:
            candidate["score"] = overlap(candidate)
        return ranked


def format_evidence(
    sentences: Iterable[dict[str, Any]],
    max_chars: int = 7000,
) -> str:
    """Format ranked sentences as numbered evidence blocks for the LLM."""
    lines: list[str] = []
    total = 0
    for number, sentence in enumerate(sentences, start=1):
        title = sentence.get("title") or "Untitled source"
        text = sentence.get("text", "")
        published = str(sentence.get("published_at", "")).strip()
        date_prefix = f" ({published})" if published else ""
        line = f"[{number}]{date_prefix} {title}: {text}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def evidence_from_gold(evidence_sentence: str, title: str = "COVID-Fact evidence") -> str:
    """Format the dataset's gold premise as one evidence block."""
    return f"[1] {title}: {clean_text(evidence_sentence)}"
