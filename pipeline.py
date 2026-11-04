"""Live claim-checking pipeline: retrieve, rank evidence, classify with an LLM."""

from __future__ import annotations

import threading
from typing import Any

import config
import evidence
import llm_client
import model_manager
import retrieval
import verification
from evaluation import prompts

_bert_lock = threading.Lock()
_bert_bundle: dict[str, Any] | None = None


def get_bert_bundle() -> dict[str, Any]:
    """Load the optional BERT classifier lazily."""
    global _bert_bundle
    if _bert_bundle is None:
        with _bert_lock:
            if _bert_bundle is None:
                import torch
                from transformers import (
                    BertForSequenceClassification,
                    BertTokenizer,
                )

                tokenizer = BertTokenizer.from_pretrained(config.BERT_MODEL_PATH)
                model = BertForSequenceClassification.from_pretrained(
                    config.BERT_MODEL_PATH
                )
                model.eval()
                _bert_bundle = {
                    "tokenizer": tokenizer,
                    "model": model,
                    "torch": torch,
                }
    return _bert_bundle


def bert_classify(claim: str) -> dict[str, Any]:
    """Run the optional BERT screen. 1 maps to SUPPORTED, 0 to REFUTED."""
    bundle = get_bert_bundle()
    torch = bundle["torch"]
    tokenizer = bundle["tokenizer"]
    model = bundle["model"]
    inputs = tokenizer(
        claim,
        max_length=128,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.softmax(outputs.logits, dim=1)
        prediction = int(torch.argmax(probabilities, dim=1).item())
        confidence = float(probabilities[0][prediction].item())
    return {
        "label": "SUPPORTED" if prediction == 1 else "REFUTED",
        "confidence": confidence,
        "raw_prediction": prediction,
    }


def _fallback_candidates(
    retrieval_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Use search snippets when page extraction failed."""
    candidates: list[dict[str, Any]] = []
    for index, result in enumerate(retrieval_result.get("results", [])):
        snippet = result.get("snippet") or ""
        for sentence_index, sentence in enumerate(evidence.split_sentences(snippet)):
            candidates.append(
                {
                    "text": sentence,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "published_at": result.get("published_at", ""),
                    "page_index": index,
                    "sentence_index": sentence_index,
                }
            )
    return candidates


def retrieve_evidence(
    claim: str,
    top_k: int = config.DEFAULT_TOP_K,
    max_results: int = config.RETRIEVAL_MAX_RESULTS,
    max_pages: int = config.RETRIEVAL_MAX_PAGES,
    use_cache: bool = True,
) -> dict[str, Any]:
    retrieval_result = retrieval.search_and_fetch(
        claim,
        max_results=max_results,
        max_pages=max_pages,
        use_cache=use_cache,
    )
    candidates = evidence.build_candidates(retrieval_result.get("results", []))
    if not candidates:
        candidates = _fallback_candidates(retrieval_result)
    ranked = evidence.rank_sentences(
        claim,
        candidates,
        top_k=max(top_k, config.EVIDENCE_CANDIDATES),
    )
    selected = ranked[:top_k]
    evidence_text = evidence.format_evidence(selected)
    if not evidence_text:
        evidence_text = "[1] No retrieved evidence was available."
    return {
        "retrieval": retrieval_result,
        "selected": selected,
        "candidates": ranked,
        "evidence_text": evidence_text,
        "source_urls": [
            result.get("url", "")
            for result in retrieval_result.get("results", [])
            if result.get("url")
        ],
    }


def _classify(
    claim: str,
    evidence_text: str,
    model: str,
    temperature: float,
    timeout: int,
) -> dict[str, Any]:
    messages = prompts.build_live_messages(claim, evidence_text)
    first = llm_client.chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=280,
        timeout=timeout,
        retries=1,
    )
    parsed = llm_client.parse_live_response(first.content)
    raw_response = first.content
    retried = False
    if parsed["label"] is None:
        retried = True
        retry_messages = list(messages) + [
            {"role": "assistant", "content": raw_response or "(empty)"},
            {
                "role": "user",
                "content": (
                    "Invalid answer. Reply with exactly four lines:\n"
                    "LABEL: SUPPORTED, REFUTED, or UNVERIFIED\n"
                    "CONFIDENCE: HIGH, MEDIUM, or LOW\n"
                    "ANSWER: one or two sentences answering the claim.\n"
                    "REASON: one or two sentences with citations such as [1]."
                ),
            },
        ]
        second = llm_client.chat(
            retry_messages,
            model=model,
            temperature=temperature,
            max_tokens=280,
            timeout=timeout,
            retries=1,
        )
        raw_response = first.content + "\n--- retry ---\n" + second.content
        parsed = llm_client.parse_live_response(second.content)
    return {
        "label": parsed["label"],
        "confidence": parsed["confidence"],
        "answer": parsed["answer"],
        "citations": parsed["citations"],
        "raw_response": raw_response,
        "retried": retried,
        "latency_seconds": first.latency_seconds,
        "reason": parsed["reason"],
    }


def check_claim(
    claim: str,
    model: str | None = None,
    use_bert: bool = False,
    top_k: int = config.DEFAULT_TOP_K,
    max_results: int = config.RETRIEVAL_MAX_RESULTS,
    max_pages: int = config.RETRIEVAL_MAX_PAGES,
    use_cache: bool = True,
    temperature: float = 0.0,
    timeout: int = config.DEFAULT_LLM_TIMEOUT,
) -> dict[str, Any]:
    """Full live pipeline for one model."""
    claim = claim.strip()
    if not claim:
        raise ValueError("Claim cannot be empty.")

    model = model or config.DEFAULT_MODEL
    evidence_bundle = retrieve_evidence(
        claim,
        top_k=top_k,
        max_results=max_results,
        max_pages=max_pages,
        use_cache=use_cache,
    )
    checks = verification.analyze(claim, evidence_bundle["selected"])
    result: dict[str, Any] = {
        "claim": claim,
        "model": model,
        "evidence_text": evidence_bundle["evidence_text"],
        "selected_evidence": evidence_bundle["selected"],
        "candidates": evidence_bundle.get("candidates", []),
        "retrieval": evidence_bundle["retrieval"],
        "source_urls": evidence_bundle["source_urls"],
        "checks": checks,
        "bert": None,
    }

    if not evidence_bundle["selected"]:
        empty = verification.no_evidence_result()
        result.update(
            {
                "label": empty["label"],
                "confidence": empty["confidence"],
                "answer": empty["answer"],
                "reason": empty["reason"],
                "citations": empty["citations"],
                "raw_response": "",
                "retried": False,
                "latency_seconds": 0.0,
            }
        )
        if use_bert:
            try:
                result["bert"] = bert_classify(claim)
            except Exception as exc:  # noqa: BLE001 - optional component
                result["bert"] = {"error": str(exc)}
        return result

    try:
        classification = _classify(
            claim,
            evidence_bundle["evidence_text"],
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced in UI
        result.update(
            {
                "label": None,
                "confidence": "LOW",
                "answer": "",
                "citations": [],
                "reason": f"LM Studio error: {exc}",
                "raw_response": "",
                "retried": False,
                "latency_seconds": 0.0,
            }
        )
        if use_bert:
            try:
                result["bert"] = bert_classify(claim)
            except Exception as bert_exc:  # noqa: BLE001
                result["bert"] = {"error": str(bert_exc)}
        return result

    result.update(classification)
    result.update(
        verification.apply_guard(
            classification,
            checks,
            len(evidence_bundle["selected"]),
        )
    )
    if use_bert:
        try:
            result["bert"] = bert_classify(claim)
        except Exception as exc:  # noqa: BLE001 - optional component
            result["bert"] = {"error": str(exc)}
    return result


def compare_models(
    claim: str,
    models: list[str] | None = None,
    use_bert: bool = False,
    top_k: int = config.DEFAULT_TOP_K,
    max_results: int = config.RETRIEVAL_MAX_RESULTS,
    max_pages: int = config.RETRIEVAL_MAX_PAGES,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Retrieve evidence once, then run the same evidence past both models."""
    claim = claim.strip()
    if not claim:
        raise ValueError("Claim cannot be empty.")
    models = models or [config.DEFAULT_MODEL, config.SECOND_MODEL]
    evidence_bundle = retrieve_evidence(
        claim,
        top_k=top_k,
        max_results=max_results,
        max_pages=max_pages,
        use_cache=use_cache,
    )
    checks = verification.analyze(claim, evidence_bundle["selected"])
    outputs = []
    for model in models:
        if not evidence_bundle["selected"]:
            empty = verification.no_evidence_result()
            outputs.append(
                {
                    "model": model,
                    **empty,
                    "raw_response": "",
                    "retried": False,
                    "latency_seconds": 0.0,
                }
            )
            continue
        try:
            model_manager.ensure_only_model(model)
            classification = _classify(
                claim,
                evidence_bundle["evidence_text"],
                model=model,
                temperature=0.0,
                timeout=config.DEFAULT_LLM_TIMEOUT,
            )
            outputs.append(
                {
                    "model": model,
                    **classification,
                    **verification.apply_guard(
                        classification,
                        checks,
                        len(evidence_bundle["selected"]),
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            outputs.append(
                {
                    "model": model,
                    "label": None,
                    "confidence": "LOW",
                    "answer": "",
                    "citations": [],
                    "reason": f"LM Studio error: {exc}",
                    "raw_response": "",
                    "retried": False,
                    "latency_seconds": 0.0,
                }
            )
    return {
        "claim": claim,
        "evidence_bundle": evidence_bundle,
        "checks": checks,
        "models": outputs,
        "bert": bert_classify(claim) if use_bert else None,
    }
