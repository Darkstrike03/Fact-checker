"""Build a reproducible Playwright retrieval cache for a COVID-Fact split."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import retrieval
from evaluation.evaluate_covidfact import load_split, sample_rows


def load_existing(path: Path, split: str) -> dict[str, Any]:
    if path.exists():
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "split": split,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": {},
    }


def save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = Path(str(path) + ".tmp")
    if path.suffix == ".gz":
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    else:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Playwright evidence cache for COVID-Fact."
    )
    parser.add_argument("--split", choices=("train", "dev", "test"), default="test")
    parser.add_argument("--max-results", type=int, default=config.RETRIEVAL_MAX_RESULTS)
    parser.add_argument("--max-pages", type=int, default=config.RETRIEVAL_MAX_PAGES)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Deterministic class-stratified sample size.",
    )
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Default: evaluation/retrieval_cache/covidfact_<split>.json.gz",
    )
    parser.add_argument("--force", action="store_true", help="Refetch existing items.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass HTTP cache.")
    args = parser.parse_args()

    config.ensure_directories()
    suffix = f"_sample{args.sample}" if args.sample else ""
    output_path = args.output or (
        config.EVALUATION_DIR
        / "retrieval_cache"
        / f"covidfact_{args.split}{suffix}.json.gz"
    )
    rows = load_split(args.split)
    if args.sample:
        rows = sample_rows(rows, args.sample, seed=args.sample_seed)
        print(
            f"Using stratified sample of {len(rows)} examples "
            f"(seed={args.sample_seed})"
        )
    if args.limit is not None:
        rows = rows[: args.limit]

    payload = load_existing(output_path, args.split)
    payload.setdefault("items", {})
    payload["config"] = {
        "max_results": args.max_results,
        "max_pages": args.max_pages,
        "split": args.split,
    }

    print(
        f"Retrieval cache: {output_path}\n"
        f"Split: {args.split} | rows: {len(rows)} | existing: {len(payload['items'])}"
    )

    started = time.perf_counter()
    fetched = 0
    skipped = 0
    for index, row in enumerate(rows, start=1):
        key = str(row["id"])
        if key in payload["items"] and not args.force:
            skipped += 1
            continue

        result = retrieval.search_and_fetch(
            row["claim"],
            max_results=args.max_results,
            max_pages=args.max_pages,
            use_cache=not args.no_cache,
        )
        payload["items"][key] = {
            "id": key,
            "claim": row["claim"],
            "provider": result.get("provider"),
            "results": result.get("results", []),
            "error": result.get("error"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        fetched += 1

        if fetched % 5 == 0:
            save_cache(output_path, payload)
        if index % 10 == 0 or index == len(rows):
            elapsed = time.perf_counter() - started
            rate = fetched / elapsed if elapsed else 0.0
            print(
                f"  [{index}/{len(rows)}] fetched={fetched} skipped={skipped} "
                f"{rate:.2f} claims/s",
                flush=True,
            )
        if args.sleep:
            time.sleep(args.sleep)

    save_cache(output_path, payload)

    providers = Counter(
        item.get("provider") or "failed" for item in payload["items"].values()
    )
    with_pages = sum(
        1
        for item in payload["items"].values()
        if any(page.get("sentences") for page in item.get("results", []))
    )
    errors = sum(1 for item in payload["items"].values() if item.get("error"))
    summary = {
        "output": str(output_path),
        "split": args.split,
        "items": len(payload["items"]),
        "with_page_sentences": with_pages,
        "errors": errors,
        "providers": dict(providers),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
