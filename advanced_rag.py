"""Stage 2 demo: compare two LM Studio models on the same retrieved evidence."""

from __future__ import annotations

import config
import pipeline


def check_fact(claim: str) -> dict:
    return pipeline.compare_models(
        claim,
        models=[config.DEFAULT_MODEL, config.SECOND_MODEL],
        top_k=5,
    )


def print_result(result: dict) -> None:
    bundle = result["evidence_bundle"]
    retrieval = bundle["retrieval"]
    print(f"\nSearch provider: {retrieval.get('provider')}")
    print(f"Evidence sentences: {len(bundle['selected'])}")
    for output in result["models"]:
        print(f"\n--- {output.get('model')} ---")
        print(f"LABEL: {output.get('label') or 'No verdict'}")
        print(f"REASON: {output.get('reason', '')}")

    print("\nEvidence:")
    for number, sentence in enumerate(bundle["selected"], start=1):
        print(f"[{number}] {sentence.get('title', '')}: {sentence.get('text', '')}")
        if sentence.get("url"):
            print(f"    {sentence['url']}")


if __name__ == "__main__":
    while True:
        claim = input("\nEnter a claim (or 'quit'): ").strip()
        if claim.lower() == "quit":
            break
        if not claim:
            continue
        try:
            print_result(check_fact(claim))
        except Exception as exc:  # noqa: BLE001 - CLI demo
            print(f"Error: {exc}")
