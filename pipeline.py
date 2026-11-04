"""Live claim-checking pipeline: retrieve, rank evidence, classify with an LLM."""

from __future__ import annotations

import threading
from typing import Any

import config
import evidence
import llm_client
import retrieval
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
    selected = evidence.rank_sentences(claim, candidates, top_k=top_k)
    evidence_text = evidence.format_evidence(selected)
    if not evidence_text:
        evidence_text = "[1] No retrieved evidence was available."
    return {
        "retrieval": retrieval_result,
        "selected": selected,
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
    messages = prompts.build_ui_messages(claim, evidence_text)
    first = llm_client.chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=120,
        timeout=timeout,
        retries=1,
    )
    label = llm_client.parse_dataset_label(first.content)
    raw_response = first.content
    retried = False
    if label is None:
        retried = True
        retry_messages = list(messages) + [
            {"role": "assistant", "content": raw_response or "(empty)"},
            {
                "role": "user",
                "content": (
                    "Invalid answer. Reply with exactly two lines:\n"
                    "LABEL: SUPPORTED or REFUTED\n"
                    "REASON: one short sentence."
                ),
            },
        ]
        second = llm_client.chat(
            retry_messages,
            model=model,
            temperature=temperature,
            max_tokens=120,
            timeout=timeout,
            retries=1,
        )
        raw_response = first.content + "\n--- retry ---\n" + second.content
        label = llm_client.parse_dataset_label(second.content)
    return {
        "label": label,
        "raw_response": raw_response,
        "retried": retried,
        "latency_seconds": first.latency_seconds,
        "reason": prompts.extract_reason(raw_response),
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
    result: dict[str, Any] = {
        "claim": claim,
        "model": model,
        "evidence_text": evidence_bundle["evidence_text"],
        "selected_evidence": evidence_bundle["selected"],
        "retrieval": evidence_bundle["retrieval"],
        "source_urls": evidence_bundle["source_urls"],
        "bert": None,
    }

    if not evidence_bundle["selected"]:
        result.update(
            {
                "label": None,
                "reason": (
                    "No usable evidence was retrieved. The evidence-only policy "
                    "does not allow a SUPPORTED/REFUTED verdict."
                ),
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
    outputs = []
    for model in models:
        if not evidence_bundle["selected"]:
            outputs.append(
                {
                    "model": model,
                    "label": None,
                    "reason": (
                        "No usable evidence was retrieved. The evidence-only "
                        "policy does not allow a SUPPORTED/REFUTED verdict."
                    ),
                    "raw_response": "",
                    "retried": False,
                    "latency_seconds": 0.0,
                }
            )
            continue
        try:
            outputs.append(
                {
                    "model": model,
                    **_classify(
                        claim,
                        evidence_bundle["evidence_text"],
                        model=model,
                        temperature=0.0,
                        timeout=config.DEFAULT_LLM_TIMEOUT,
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            outputs.append(
                {
                    "model": model,
                    "label": None,
                    "reason": f"LM Studio error: {exc}",
                    "raw_response": "",
                    "retried": False,
                    "latency_seconds": 0.0,
                }
            )
    return {
        "claim": claim,
        "evidence_bundle": evidence_bundle,
        "models": outputs,
        "bert": bert_classify(claim) if use_bert else None,
    }
