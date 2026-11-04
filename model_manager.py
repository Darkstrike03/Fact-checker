"""Keep exactly one LM Studio model loaded on memory-constrained machines."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DEFAULT_LMS_PATHS = (
    Path.home() / ".lmstudio" / "bin" / "lms.exe",
    Path.home() / ".lmstudio" / "bin" / "lms",
    Path.home() / ".cache" / "lm-studio" / "bin" / "lms",
)


class ModelManagerError(RuntimeError):
    """Raised when LM Studio's CLI cannot switch models."""


def _lms_path() -> str | None:
    configured = os.getenv("LMS_CLI", "").strip()
    if configured:
        return configured
    found = shutil.which("lms")
    if found:
        return found
    for candidate in _DEFAULT_LMS_PATHS:
        if candidate.exists():
            return str(candidate)
    return None


def lms_available() -> bool:
    return _lms_path() is not None


def _run(args: list[str], timeout: int) -> str:
    executable = _lms_path()
    if not executable:
        raise ModelManagerError("LM Studio CLI (lms) was not found.")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ModelManagerError(
            f"LM Studio CLI timed out after {timeout}s: lms {' '.join(args)}"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ModelManagerError(
            f"LM Studio CLI failed ({completed.returncode}): {detail[:300]}"
        )
    return completed.stdout or ""


def _entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("models", "data", "loaded", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(key in payload for key in ("modelKey", "identifier", "model", "id")):
            return [payload]
    return []


def _model_id(entry: dict[str, Any]) -> str:
    for key in ("modelKey", "identifier", "model", "id", "path"):
        value = entry.get(key)
        if value:
            return str(value)
    return ""


def _normalize(value: str) -> str:
    return str(value or "").strip().lower().replace("\\", "/")


def _same_model(left: str, right: str) -> bool:
    left_key = _normalize(left)
    right_key = _normalize(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_base = left_key.rsplit("/", 1)[-1]
    right_base = right_key.rsplit("/", 1)[-1]
    return left_base == right_base


def loaded_models() -> list[str]:
    if not lms_available():
        return []
    try:
        raw = _run(["ps", "--json"], timeout=20)
    except ModelManagerError:
        return []
    try:
        payload = json.loads(raw.strip() or "[]")
    except json.JSONDecodeError:
        return []
    models: list[str] = []
    for entry in _entries(payload):
        model = _model_id(entry)
        if model and model not in models:
            models.append(model)
    return models


def ensure_only_model(model: str) -> dict[str, Any]:
    """Unload every other model, then load the requested one if needed."""
    model = str(model or "").strip()
    if not model:
        raise ModelManagerError("No model was selected.")
    if not lms_available():
        return {
            "available": False,
            "model": model,
            "loaded": [],
            "switched": False,
            "reason": "LM Studio CLI not found; relying on LM Studio's lazy loading.",
        }

    with _LOCK:
        current = loaded_models()
        if (
            len(current) == 1
            and _same_model(current[0], model)
        ):
            return {
                "available": True,
                "model": model,
                "loaded": current,
                "switched": False,
            }

        if current:
            _run(["unload", "--all"], timeout=90)

        _run(["load", model, "-y"], timeout=180)
        after = loaded_models()
        selected_loaded = any(_same_model(item, model) for item in after)
        if len(after) > 1:
            _run(["unload", "--all"], timeout=90)
            raise ModelManagerError(
                "More than one model remained loaded after switching."
            )
        return {
            "available": True,
            "model": model,
            "loaded": after,
            "switched": True,
            "verified": selected_loaded,
        }
