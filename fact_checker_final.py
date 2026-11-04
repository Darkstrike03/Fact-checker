"""Final CLI demo: optional BERT screen plus the Playwright RAG pipeline."""

from __future__ import annotations

import config
import pipeline


def check_fact(claim: str, model: str = config.DEFAULT_MODEL) -> dict:
    return pipeline.check_claim(claim, model=model, use_bert=True, top_k=5)


def print_result(result: dict) -> None:
    bert = result.get("bert")
    if bert and "error" not in bert:
        print(
            f"BERT hint: {bert['label']} ({bert['confidence']:.1%} confidence)"
        )
    elif bert:
        print(f"BERT hint unavailable: {bert['error']}")

    print(f"\nLABEL: {result.get('label') or 'No verdict'}")
    print(f"REASON: {result.get('reason', '')}")
    print(f"MODEL: {result.get('model')}")
    print("\nEvidence:")
    for number, sentence in enumerate(result.get("selected_evidence", []), start=1):
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
