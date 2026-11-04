"""Stage 1 demo: Playwright retrieval plus one LM Studio verdict."""

from __future__ import annotations

import config
import pipeline


def check_fact(claim: str, model: str = config.DEFAULT_MODEL) -> dict:
    return pipeline.check_claim(claim, model=model, top_k=3)


def print_result(result: dict) -> None:
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
