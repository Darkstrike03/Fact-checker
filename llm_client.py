"""Small LM Studio OpenAI-compatible client used by the app and evaluation."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

import config


class LMStudioError(RuntimeError):
    """Raised when LM Studio cannot satisfy a request."""


@dataclass
class ChatResult:
    content: str
    model: str
    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def list_models(timeout: int = 15) -> list[dict[str, Any]]:
    """Return the OpenAI-compatible model list from LM Studio."""
    try:
        response = requests.get(config.LM_STUDIO_MODELS_URL, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        raise LMStudioError(
            f"Could not reach LM Studio at {config.LM_STUDIO_MODELS_URL}: {exc}"
        ) from exc

    models = payload.get("data", payload if isinstance(payload, list) else [])
    return [model for model in models if isinstance(model, dict)]


def _is_chat_model(model: dict[str, Any]) -> bool:
    model_type = str(model.get("type", "")).lower()
    model_id = str(model.get("id", "")).lower()
    excluded = ("embed", "whisper", "tts", "rerank", "clip")
    if any(token in model_id for token in excluded):
        return False
    if model_type and model_type not in {"llm", "vlm", "chat", "text"}:
        return False
    return bool(model.get("id"))


def list_chat_models(timeout: int = 15) -> list[str]:
    """Return model ids suitable for text chat, preferring loaded models first."""
    try:
        models = list_models(timeout=timeout)
    except LMStudioError:
        return []

    loaded = [
        str(model["id"])
        for model in models
        if _is_chat_model(model) and str(model.get("state", "")).lower() == "loaded"
    ]
    available = [
        str(model["id"])
        for model in models
        if _is_chat_model(model)
    ]
    result: list[str] = []
    for model_id in loaded + available:
        if model_id not in result:
            result.append(model_id)
    return result


def get_model_info(model_id: str) -> dict[str, Any] | None:
    for model in list_models():
        if str(model.get("id")) == model_id:
            return model
    return None


def health_check() -> dict[str, Any]:
    """Return a small diagnostic dictionary for the UI/CLI."""
    try:
        models = list_models()
        chat_models = list_chat_models()
        return {
            "reachable": True,
            "url": config.LM_STUDIO_MODELS_URL,
            "models": models,
            "chat_models": chat_models,
        }
    except LMStudioError as exc:
        return {
            "reachable": False,
            "url": config.LM_STUDIO_MODELS_URL,
            "error": str(exc),
            "models": [],
            "chat_models": [],
        }


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = config.DEFAULT_LLM_TEMPERATURE,
    max_tokens: int = 32,
    timeout: int = config.DEFAULT_LLM_TIMEOUT,
    retries: int = 1,
    extra_body: dict[str, Any] | None = None,
) -> ChatResult:
    """Send a chat completion request to LM Studio.

    LM Studio loads an unloaded model on the first request (JIT loading), which
    can take longer than a warm request. One retry is therefore enabled by
    default for transient connection errors.
    """
    payload: dict[str, Any] = {
        "model": model or config.DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if config.REASONING_EFFORT:
        # Qwen3 otherwise spends the entire completion budget on hidden
        # reasoning tokens and returns an empty content field.
        payload["reasoning_effort"] = config.REASONING_EFFORT
    if extra_body:
        payload.update(extra_body)

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            response = requests.post(
                config.LM_STUDIO_URL,
                headers=_headers(),
                data=json.dumps(payload),
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            usage = body.get("usage") or {}
            return ChatResult(
                content=str(content).strip(),
                model=str(body.get("model") or payload["model"]),
                latency_seconds=time.perf_counter() - started,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
        except Exception as exc:  # noqa: BLE001 - retried below
            last_error = exc
            if attempt < retries:
                time.sleep(1.0 + attempt)

    raise LMStudioError(
        f"LM Studio chat request failed for model {payload['model']}: {last_error}"
    )


def chat_text(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = config.DEFAULT_LLM_TEMPERATURE,
    max_tokens: int = 32,
    timeout: int = config.DEFAULT_LLM_TIMEOUT,
    retries: int = 1,
) -> ChatResult:
    return chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        retries=retries,
    )


_LABEL_PATTERN = re.compile(r"\b(SUPPORTED|REFUTED)\b", re.IGNORECASE)
_LIVE_LABEL_PATTERN = re.compile(
    r"\b(SUPPORTED|REFUTED|UNVERIFIED)\b", re.IGNORECASE
)


def parse_live_label(text: str) -> str | None:
    """Parse a three-way live label without weakening dataset evaluation."""
    if not text:
        return None

    upper = text.upper()
    for label in config.LIVE_LABELS:
        if re.search(rf"(?:LABEL|VERDICT|ANSWER)\s*[:\-]\s*{label}\b", upper):
            return label

    if re.search(r"\b(?:INSUFFICIENT|NOT ENOUGH)\s+EVIDENCE\b", upper):
        return "UNVERIFIED"

    compact = re.sub(r"[^A-Z]", "", upper)
    if compact in config.LIVE_LABELS:
        return compact

    matches = _LIVE_LABEL_PATTERN.findall(upper)
    unique = {match.upper() for match in matches}
    if len(unique) == 1:
        return unique.pop()
    return None


def parse_dataset_label(text: str) -> str | None:
    """Parse a strict SUPPORTED/REFUTED answer.

    Only the two dataset-aligned labels are accepted. This deliberately rejects
    True/False/Misleading/Unverifiable and explanations that do not contain a
    single unambiguous label.
    """
    if not text:
        return None

    upper = text.upper()
    for label in config.LABELS:
        if re.search(rf"(?:LABEL|VERDICT|ANSWER)\s*[:\-]\s*{label}\b", upper):
            return label

    compact = re.sub(r"[^A-Z]", "", upper)
    if compact in config.LABELS:
        return compact

    matches = _LABEL_PATTERN.findall(upper)
    unique = {match.upper() for match in matches}
    if len(unique) == 1:
        return unique.pop()
    return None


def _parse_live_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current = ""
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(
            r"^(LABEL|CONFIDENCE|ANSWER|REASON|WHY|CITATIONS?)\s*[:\-]\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            current = match.group(1).upper()
            if current == "WHY":
                current = "REASON"
            if current.startswith("CITATION"):
                current = "CITATIONS"
            fields[current] = match.group(2).strip()
        elif current in {"ANSWER", "REASON", "CITATIONS"}:
            fields[current] = f"{fields[current]} {line}".strip()
    return fields


def parse_confidence(text: str) -> str:
    upper = (text or "").upper().strip()
    if upper in {"HIGH", "MEDIUM", "MODERATE", "LOW"}:
        return "MEDIUM" if upper == "MODERATE" else upper
    match = re.search(
        r"(?:CONFIDENCE|CERTAINTY)\s*[:\-]\s*(HIGH|MEDIUM|MODERATE|LOW)",
        upper,
    )
    if match:
        value = match.group(1)
        return "MEDIUM" if value == "MODERATE" else value
    return "MEDIUM"


def extract_citations(text: str) -> list[int]:
    citations: set[int] = set()
    for group in re.findall(r"\[([0-9,;\s]+)\]", text or ""):
        for part in re.split(r"[,;\s]+", group):
            if part.isdigit():
                number = int(part)
                if 1 <= number <= 99:
                    citations.add(number)
    return sorted(citations)


def parse_live_response(text: str) -> dict[str, Any]:
    fields = _parse_live_fields(text)
    label = parse_live_label(fields.get("LABEL", "") or text)
    confidence = parse_confidence(fields.get("CONFIDENCE", "") or text)
    answer = fields.get("ANSWER", "").strip()
    reason = fields.get("REASON", "").strip()
    if not answer:
        answer = fields.get("WHY", "").strip() or reason or (text or "").strip()
    if not reason:
        reason = answer
    citations = extract_citations(f"{answer} {reason} {fields.get('CITATIONS', '')}")
    return {
        "label": label,
        "confidence": confidence,
        "answer": answer[:800],
        "reason": reason[:800],
        "citations": citations,
    }


def normalize_label(value: str) -> str | None:
    key = str(value).strip().lower()
    return config.LABEL_MAP.get(key)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: str, value: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def iter_jsonl(path: str) -> Iterable[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
