"""Metrics and statistical comparisons for the COVID-Fact evaluation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

import config

LABELS = list(config.LABELS)


def compute_metrics(
    gold_labels: Iterable[str],
    predicted_labels: Iterable[str | None],
) -> dict[str, Any]:
    gold = list(gold_labels)
    predictions = list(predicted_labels)
    if len(gold) != len(predictions):
        raise ValueError("Gold and predicted label lists must have equal length")

    valid_indices = [
        index
        for index, prediction in enumerate(predictions)
        if prediction in config.LABELS
    ]
    invalid = len(predictions) - len(valid_indices)
    valid_gold = [gold[index] for index in valid_indices]
    valid_pred = [predictions[index] for index in valid_indices]

    if not valid_gold:
        return {
            "n": len(gold),
            "n_valid": 0,
            "invalid": invalid,
            "invalid_rate": invalid / len(gold) if gold else 0.0,
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "weighted_f1": 0.0,
            "per_class": {},
            "confusion_matrix": [[0, 0], [0, 0]],
            "majority_baseline": 0.0,
        }

    precision, recall, f1, support = precision_recall_fscore_support(
        valid_gold,
        valid_pred,
        labels=LABELS,
        zero_division=0,
    )
    macro_f1 = float(np.mean(f1))
    weighted_f1 = float(
        np.average(f1, weights=support) if np.sum(support) else 0.0
    )
    matrix = confusion_matrix(valid_gold, valid_pred, labels=LABELS).tolist()
    counts = {label: valid_gold.count(label) for label in LABELS}
    majority = max(counts.values()) / len(valid_gold)

    per_class = {}
    for index, label in enumerate(LABELS):
        per_class[label] = {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }

    return {
        "n": len(gold),
        "n_valid": len(valid_gold),
        "invalid": invalid,
        "invalid_rate": invalid / len(gold) if gold else 0.0,
        "accuracy": float(accuracy_score(valid_gold, valid_pred)),
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "majority_baseline": float(majority),
        "label_counts": counts,
    }


def bootstrap_ci(
    gold_labels: Iterable[str],
    predicted_labels: Iterable[str | None],
    metric: Callable[[list[str], list[str | None]], float] | None = None,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    """Percentile bootstrap confidence interval for accuracy."""
    gold = list(gold_labels)
    predictions = list(predicted_labels)
    if not gold:
        return {"low": 0.0, "high": 0.0}

    if metric is None:
        def metric(gold_subset, pred_subset):  # noqa: ANN001
            return compute_metrics(gold_subset, pred_subset)["accuracy"]

    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(n_bootstrap):
        indices = rng.integers(0, len(gold), size=len(gold))
        gold_subset = [gold[index] for index in indices]
        pred_subset = [predictions[index] for index in indices]
        values.append(float(metric(gold_subset, pred_subset)))
    return {
        "low": float(np.percentile(values, 2.5)),
        "high": float(np.percentile(values, 97.5)),
    }


def mcnemar_test(
    gold_labels: Iterable[str],
    predictions_a: Iterable[str | None],
    predictions_b: Iterable[str | None],
) -> dict[str, Any]:
    """Exact McNemar test for two classifiers on the same examples."""
    gold = list(gold_labels)
    pred_a = list(predictions_a)
    pred_b = list(predictions_b)
    if len(gold) != len(pred_a) or len(gold) != len(pred_b):
        raise ValueError("All label lists must have equal length")

    correct_a = [pred == target for pred, target in zip(pred_a, gold)]
    correct_b = [pred == target for pred, target in zip(pred_b, gold)]
    only_a = sum(1 for a, b in zip(correct_a, correct_b) if a and not b)
    only_b = sum(1 for a, b in zip(correct_a, correct_b) if b and not a)

    try:
        from scipy.stats import binomtest

        p_value = binomtest(
            min(only_a, only_b),
            only_a + only_b,
            0.5,
        ).pvalue if (only_a + only_b) else 1.0
    except Exception:
        p_value = None

    return {
        "only_a_correct": only_a,
        "only_b_correct": only_b,
        "p_value": float(p_value) if p_value is not None else None,
    }


def summarize_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group raw JSONL records by experiment and compute metrics."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (
            record.get("split", "unknown"),
            record.get("model", "unknown"),
            record.get("prompt", "unknown"),
            record.get("mode", "unknown"),
        )
        groups[key].append(record)

    summaries = []
    for (split, model, prompt, mode), group in sorted(groups.items()):
        gold = [record["gold"] for record in group]
        predictions = [record.get("predicted") for record in group]
        metrics = compute_metrics(gold, predictions)
        metrics.update(
            {
                "split": split,
                "model": model,
                "prompt": prompt,
                "mode": mode,
                "bootstrap_accuracy_ci": bootstrap_ci(gold, predictions),
            }
        )
        summaries.append(metrics)
    return summaries


def format_summary_markdown(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "No evaluation records found.\n"

    lines = [
        "# COVID-Fact evaluation summary",
        "",
        "| Split | Model | Prompt | Mode | N | Acc | Macro F1 | Weighted F1 | Invalid | 95% CI |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for summary in summaries:
        ci = summary.get("bootstrap_accuracy_ci", {})
        lines.append(
            "| {split} | {model} | {prompt} | {mode} | {n_valid} | {accuracy:.1%} | "
            "{macro_f1:.4f} | {weighted_f1:.4f} | {invalid} | "
            "[{low:.1%}, {high:.1%}] |".format(
                split=summary["split"],
                model=summary["model"],
                prompt=summary["prompt"],
                mode=summary["mode"],
                n_valid=summary["n_valid"],
                accuracy=summary["accuracy"],
                macro_f1=summary["macro_f1"],
                weighted_f1=summary["weighted_f1"],
                invalid=summary["invalid"],
                low=ci.get("low", 0.0),
                high=ci.get("high", 0.0),
            )
        )

    lines.extend(
        [
            "",
            "## Per-class metrics",
            "",
            "| Split | Model | Prompt | Mode | Class | P | R | F1 | Support |",
            "|---|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        for label in LABELS:
            metrics = summary["per_class"].get(label, {})
            lines.append(
                "| {split} | {model} | {prompt} | {mode} | {label} | {precision:.4f} | "
                "{recall:.4f} | {f1:.4f} | {support} |".format(
                    split=summary["split"],
                    model=summary["model"],
                    prompt=summary["prompt"],
                    mode=summary["mode"],
                    label=label,
                    precision=metrics.get("precision", 0.0),
                    recall=metrics.get("recall", 0.0),
                    f1=metrics.get("f1", 0.0),
                    support=metrics.get("support", 0),
                )
            )

    lines.extend(
        [
            "",
            "## Paper reference values (COVID-Fact, ACL 2021)",
            "",
            "- RoBERTa-large with gold evidence: 83.5% accuracy / 82.0 F1 (Table 4).",
            "- RoBERTa-large with top-5 retrieved evidence: 84.7% accuracy / 83.0 F1.",
            "- Claim-only classifier: 67.5% accuracy / 40.0 macro F1.",
            "- COVID-FEVER transfer: 43.3% accuracy.",
            "- Top-5 retrieval: P 22.27 / R 52.37 / F1 31.25 (Table 5).",
            "",
        ]
    )
    return "\n".join(lines)
