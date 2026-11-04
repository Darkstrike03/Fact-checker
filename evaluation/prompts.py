"""Prompt templates for the strict COVID-Fact binary evaluation."""

from __future__ import annotations

import csv
import random
import re
from pathlib import Path
from typing import Any

import config

CLAIM_ONLY_SYSTEM_PROMPT = """You are a careful fact checker for COVID-19 claims.
You are given only a claim, with no retrieved evidence. Use your background
knowledge to decide whether the claim is SUPPORTED or REFUTED.

Answer with exactly one word: SUPPORTED or REFUTED. Do not explain."""

EVAL_SYSTEM_PROMPT = """You are a careful evidence-based fact checker for COVID-19 claims.
Decide whether the provided evidence SUPPORTS or REFUTES the claim.

Definitions:
- SUPPORTED: the evidence entails the claim.
- REFUTED: the evidence contradicts the claim.

Use only the provided evidence. Do not use outside knowledge.
Answer with exactly one word: SUPPORTED or REFUTED. Do not explain."""

UI_SYSTEM_PROMPT = """You are a careful evidence-based fact checker for COVID-19 claims.
Use only the provided evidence to decide whether the claim is SUPPORTED or REFUTED.

Definitions:
- SUPPORTED: the evidence entails the claim.
- REFUTED: the evidence contradicts the claim.

Answer in exactly this format, with no extra text:
LABEL: SUPPORTED
REASON: one short sentence grounded in the evidence."""


def _format_example(example: dict[str, str]) -> list[dict[str, str]]:
    evidence = example.get("evidence", "").strip()
    claim = example.get("claim", "").strip()
    label = example.get("label", "").strip()
    return [
        {
            "role": "user",
            "content": f"Evidence:\n[1] COVID-Fact evidence: {evidence}\n\nClaim:\n{claim}\n\nAnswer:",
        },
        {"role": "assistant", "content": label},
    ]


def load_few_shot_examples(
    split_path: Path | None = None,
    n_examples: int = 3,
    seed: int = 42,
) -> list[dict[str, str]]:
    """Select a small, deterministic, class-balanced set from the train split."""
    path = split_path or (config.DATASET_DIR / "train.tsv")
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            label = row.get("label") or row.get("entailment") or ""
            label = config.LABEL_MAP.get(label.strip().lower())
            claim = (row.get("Sentence2") or row.get("sentence2") or "").strip()
            evidence = (row.get("sentence1") or "").strip()
            if not label or not claim or not evidence:
                continue
            if not (20 <= len(claim) <= 140 and 40 <= len(evidence) <= 220):
                continue
            if "\n" in claim or "\n" in evidence:
                continue
            rows.append(
                {"claim": claim, "evidence": evidence, "label": label}
            )

    random.Random(seed).shuffle(rows)
    supported = [row for row in rows if row["label"] == "SUPPORTED"]
    refuted = [row for row in rows if row["label"] == "REFUTED"]

    selected: list[dict[str, str]] = []
    supported_target = max(1, n_examples // 3)
    refuted_target = max(1, n_examples - supported_target)
    selected.extend(supported[:supported_target])
    selected.extend(refuted[:refuted_target])
    random.Random(seed).shuffle(selected)
    return selected[:n_examples]


def build_eval_messages(
    claim: str,
    evidence: str,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": EVAL_SYSTEM_PROMPT}
    ]
    for example in few_shot_examples or []:
        messages.extend(_format_example(example))
    messages.append(
        {
            "role": "user",
            "content": (
                f"Evidence:\n{evidence.strip()}\n\n"
                f"Claim:\n{claim.strip()}\n\n"
                "Answer:"
            ),
        }
    )
    return messages


def build_claim_only_messages(
    claim: str,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CLAIM_ONLY_SYSTEM_PROMPT}
    ]
    for example in few_shot_examples or []:
        messages.append(
            {"role": "user", "content": f"Claim:\n{example['claim']}\n\nAnswer:"}
        )
        messages.append({"role": "assistant", "content": example["label"]})
    messages.append(
        {"role": "user", "content": f"Claim:\n{claim.strip()}\n\nAnswer:"}
    )
    return messages


def build_ui_messages(claim: str, evidence: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": UI_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Evidence:\n{evidence.strip()}\n\n"
                f"Claim:\n{claim.strip()}\n\n"
                "Return the LABEL and REASON now."
            ),
        },
    ]


def extract_reason(text: str) -> str:
    """Extract a short reason from the UI response, falling back to the text."""
    if not text:
        return ""
    match = re.search(
        r"(?:REASON|EXPLANATION)\s*[:\-]\s*(.+)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    reason = match.group(1).strip() if match else text.strip()
    reason = re.sub(r"\s+", " ", reason)
    return reason[:500]
