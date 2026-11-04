"""Evaluate LM Studio models on the official COVID-Fact RTE splits."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import evidence as evidence_module
import llm_client
from evaluation import metrics, prompts


def slugify(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )


def load_split(split: str) -> list[dict[str, Any]]:
    path = config.DATASET_DIR / f"{split}.tsv"
    if not path.exists():
        raise FileNotFoundError(f"Dataset split not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        label_column = "label" if "label" in fieldnames else "entailment"
        for row_index, row in enumerate(reader):
            raw_label = (row.get(label_column) or "").strip().lower()
            gold = config.LABEL_MAP.get(raw_label)
            claim = (
                row.get("Sentence2")
                or row.get("sentence2")
                or row.get("claim")
                or ""
            ).strip()
            evidence_sentence = (row.get("sentence1") or "").strip()
            if not gold or not claim:
                continue
            rows.append(
                {
                    "id": str(row.get("index") or row_index),
                    "row_index": row_index,
                    "claim": claim,
                    "evidence": evidence_sentence,
                    "gold": gold,
                }
            )
    return rows


def sample_rows(
    rows: list[dict[str, Any]],
    sample_size: int | None,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Return a deterministic class-stratified sample."""
    if sample_size is None or sample_size >= len(rows):
        return rows
    if sample_size <= 0:
        return []

    rng = random.Random(seed)
    by_label: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_label.setdefault(row["gold"], []).append(row)
    for group in by_label.values():
        rng.shuffle(group)

    total = len(rows)
    selected: list[dict[str, Any]] = []
    labels = sorted(by_label)
    assigned = 0
    for index, label in enumerate(labels):
        group = by_label[label]
        if index == len(labels) - 1:
            take = sample_size - assigned
        else:
            take = round(sample_size * len(group) / total)
        take = max(0, min(take, len(group)))
        selected.extend(group[:take])
        assigned += take

    # If rounding left the sample short, fill from the largest remaining pool.
    if len(selected) < sample_size:
        selected_ids = {row["id"] for row in selected}
        for row in rows:
            if row["id"] not in selected_ids:
                selected.append(row)
            if len(selected) >= sample_size:
                break

    rng.shuffle(selected)
    return selected[:sample_size]


def load_retrieval_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Retrieval cache not found: {path}")
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    items = payload.get("items", payload)
    if isinstance(items, list):
        return {str(item.get("id", index)): item for index, item in enumerate(items)}
    return {str(key): value for key, value in items.items()}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl_line(handle, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def _retrieved_evidence(
    cache_item: dict[str, Any] | None,
    claim: str,
    top_k: int,
) -> tuple[str, list[str], bool]:
    if not cache_item:
        return (
            "[1] No retrieved evidence was available.",
            [],
            True,
        )
    pages = cache_item.get("results") or []
    candidates = evidence_module.build_candidates(pages)
    if not candidates:
        for page_index, page in enumerate(pages):
            for sentence_index, sentence in enumerate(
                evidence_module.split_sentences(page.get("snippet", ""))
            ):
                candidates.append(
                    {
                        "text": sentence,
                        "title": page.get("title", ""),
                        "url": page.get("url", ""),
                        "page_index": page_index,
                        "sentence_index": sentence_index,
                    }
                )
    selected = evidence_module.rank_sentences(claim, candidates, top_k=top_k)
    if not selected:
        return (
            "[1] No retrieved evidence was available.",
            [page.get("url", "") for page in pages if page.get("url")],
            True,
        )
    return (
        evidence_module.format_evidence(selected),
        [page.get("url", "") for page in pages if page.get("url")],
        False,
    )


def _messages_for(
    mode: str,
    claim: str,
    evidence_text: str,
    prompt_variant: str,
    few_shot_examples: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    examples = few_shot_examples if prompt_variant == "few_shot" else None
    if mode == "claim_only":
        return prompts.build_claim_only_messages(claim, examples)
    return prompts.build_eval_messages(claim, evidence_text, examples)


def _predict(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    raw_response = ""
    retry_response = ""
    predicted = None
    error = None
    retried = False

    try:
        first = llm_client.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=1,
        )
        raw_response = first.content
        predicted = llm_client.parse_dataset_label(raw_response)
        if predicted is None:
            retried = True
            retry_messages = list(messages) + [
                {"role": "assistant", "content": raw_response or "(empty)"},
                {
                    "role": "user",
                    "content": (
                        "Your answer was invalid. Reply with exactly one word: "
                        "SUPPORTED or REFUTED."
                    ),
                },
            ]
            second = llm_client.chat(
                retry_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                retries=1,
            )
            retry_response = second.content
            predicted = llm_client.parse_dataset_label(retry_response)
    except Exception as exc:  # noqa: BLE001 - stored per example
        error = str(exc)

    return {
        "predicted": predicted,
        "raw_response": raw_response,
        "retry_response": retry_response,
        "retried": retried,
        "error": error,
        "latency_seconds": time.perf_counter() - started,
    }


def _output_path(
    split: str,
    model: str,
    prompt_variant: str,
    mode: str,
    output_dir: Path,
) -> Path:
    name = f"{split}_{slugify(model)}_{prompt_variant}_{mode}.jsonl"
    return output_dir / name


def _write_summary(
    results_dir: Path,
    raw_dir: Path | None = None,
) -> list[dict[str, Any]]:
    raw_dir = raw_dir or (results_dir / "raw")
    records: list[dict[str, Any]] = []
    if raw_dir.exists():
        for path in sorted(raw_dir.glob("*.jsonl")):
            records.extend(_read_jsonl(path))
    summaries = metrics.summarize_records(records)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.md").write_text(
        metrics.format_summary_markdown(summaries),
        encoding="utf-8",
    )
    (results_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summaries


def run_experiment(
    split: str,
    rows: list[dict[str, Any]],
    model: str,
    prompt_variant: str,
    mode: str,
    retrieval_cache: dict[str, dict[str, Any]] | None,
    few_shot_examples: list[dict[str, str]] | None,
    output_dir: Path,
    top_k: int,
    temperature: float,
    max_tokens: int,
    timeout: int,
    limit: int | None,
    resume: bool,
) -> dict[str, Any]:
    output_path = _output_path(split, model, prompt_variant, mode, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = _read_jsonl(output_path) if resume else []
    processed = {str(record.get("id")) for record in existing}
    if not resume and output_path.exists():
        output_path.unlink()

    if limit is not None:
        rows = rows[:limit]

    total = len(rows)
    print(
        f"\nRunning {split} | {model} | {prompt_variant} | {mode} | "
        f"{total} examples -> {output_path}",
        flush=True,
    )
    started = time.perf_counter()
    written = 0
    with output_path.open("a", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            if str(row["id"]) in processed:
                continue

            retrieval_empty = False
            source_urls: list[str] = []
            if mode == "gold":
                evidence_text = evidence_module.evidence_from_gold(row["evidence"])
            elif mode == "retrieved":
                cache_item = (retrieval_cache or {}).get(str(row["id"]))
                evidence_text, source_urls, retrieval_empty = _retrieved_evidence(
                    cache_item,
                    row["claim"],
                    top_k=top_k,
                )
            else:
                evidence_text = ""

            messages = _messages_for(
                mode,
                row["claim"],
                evidence_text,
                prompt_variant,
                few_shot_examples,
            )
            prediction = _predict(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            record = {
                "split": split,
                "id": row["id"],
                "row_index": row["row_index"],
                "claim": row["claim"],
                "gold": row["gold"],
                "gold_evidence": row["evidence"],
                "evidence": evidence_text,
                "source_urls": source_urls,
                "retrieval_empty": retrieval_empty,
                "model": model,
                "prompt": prompt_variant,
                "mode": mode,
                "temperature": temperature,
                "predicted": prediction["predicted"],
                "correct": prediction["predicted"] == row["gold"],
                "raw_response": prediction["raw_response"],
                "retry_response": prediction["retry_response"],
                "retried": prediction["retried"],
                "error": prediction["error"],
                "latency_seconds": round(prediction["latency_seconds"], 4),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _write_jsonl_line(handle, record)
            written += 1
            if index % 10 == 0 or index == total or prediction["predicted"] is None:
                elapsed = time.perf_counter() - started
                rate = index / elapsed if elapsed else 0.0
                print(
                    f"  [{index}/{total}] gold={row['gold']} "
                    f"pred={prediction['predicted']} "
                    f"{rate:.2f} ex/s",
                    flush=True,
                )

    records = _read_jsonl(output_path)
    summary = metrics.compute_metrics(
        [record["gold"] for record in records],
        [record.get("predicted") for record in records],
    )
    print(
        f"Finished {mode}/{prompt_variant}: {written} new, "
        f"accuracy={summary['accuracy']:.1%}, "
        f"macro_f1={summary['macro_f1']:.4f}, invalid={summary['invalid']}",
        flush=True,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a small LM Studio model on COVID-Fact."
    )
    parser.add_argument("--split", choices=("train", "dev", "test"), default="test")
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        help="Model id; repeat to evaluate multiple models.",
    )
    parser.add_argument(
        "--prompt",
        choices=("zero_shot", "few_shot", "both"),
        default="zero_shot",
    )
    parser.add_argument(
        "--mode",
        choices=("gold", "retrieved", "claim_only", "all"),
        default="gold",
    )
    parser.add_argument(
        "--retrieval-cache",
        type=Path,
        default=None,
        help="Compressed JSON cache built by evaluation/build_retrieval_cache.py",
    )
    parser.add_argument("--top-k", type=int, default=config.DEFAULT_TOP_K)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Deterministic class-stratified sample size (for retrieval runs).",
    )
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--few-shot", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=config.DEFAULT_LLM_TIMEOUT)
    parser.add_argument("--output-dir", type=Path, default=config.RAW_RESULTS_DIR)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only rebuild summary.md from existing raw JSONL files.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config.ensure_directories()
    rows = load_split(args.split)
    print(f"Loaded {len(rows)} {args.split} examples from {config.DATASET_DIR}")
    if args.sample:
        rows = sample_rows(rows, args.sample, seed=args.sample_seed)
        print(
            f"Using stratified sample of {len(rows)} examples "
            f"(seed={args.sample_seed})"
        )

    if args.summary_only:
        summaries = _write_summary(config.RESULTS_DIR)
        print(metrics.format_summary_markdown(summaries))
        return

    if args.dry_run:
        for row in rows[:5]:
            print(row)
        print(f"Valid rows: {len(rows)}")
        return

    models = args.model or [config.DEFAULT_MODEL]
    prompt_variants = (
        ["zero_shot", "few_shot"] if args.prompt == "both" else [args.prompt]
    )
    modes = (
        ["gold", "retrieved", "claim_only"]
        if args.mode == "all"
        else [args.mode]
    )

    if "retrieved" in modes:
        if args.retrieval_cache:
            cache_path = args.retrieval_cache
        else:
            suffix = f"_sample{args.sample}" if args.sample else ""
            cache_path = (
                config.EVALUATION_DIR
                / "retrieval_cache"
                / f"covidfact_{args.split}{suffix}.json.gz"
            )
        if not cache_path.exists():
            raise SystemExit(
                f"Retrieval cache missing: {cache_path}\n"
                "Build it first with:\n"
                f"  .venv\\Scripts\\python.exe -m evaluation.build_retrieval_cache "
                f"--split {args.split}"
            )
        retrieval_cache = load_retrieval_cache(cache_path)
        print(f"Loaded retrieval cache with {len(retrieval_cache)} items: {cache_path}")
    else:
        retrieval_cache = None

    few_shot_examples = (
        prompts.load_few_shot_examples(
            config.DATASET_DIR / "train.tsv",
            n_examples=args.few_shot,
            seed=args.seed,
        )
        if "few_shot" in prompt_variants
        else None
    )

    for model in models:
        for prompt_variant in prompt_variants:
            for mode in modes:
                run_experiment(
                    split=args.split,
                    rows=rows,
                    model=model,
                    prompt_variant=prompt_variant,
                    mode=mode,
                    retrieval_cache=retrieval_cache,
                    few_shot_examples=few_shot_examples,
                    output_dir=args.output_dir,
                    top_k=args.top_k,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                    limit=args.limit,
                    resume=not args.no_resume,
                )

    summaries = _write_summary(config.RESULTS_DIR)
    if args.output_dir.resolve() != config.RAW_RESULTS_DIR.resolve():
        _write_summary(args.output_dir, raw_dir=args.output_dir)
    print("\n" + metrics.format_summary_markdown(summaries))


if __name__ == "__main__":
    main()
