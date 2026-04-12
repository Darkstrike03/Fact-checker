import requests
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import torch
from transformers import BertTokenizer, BertForSequenceClassification

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
TAVILY_API_KEY = "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"
BERT_MODEL_PATH = "https://huggingface.co/DarkStrike/fact-checker-bert"  # folder you just downloaded

# --- Load models at startup ---
print("Loading embedding model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')

print("Loading BERT classifier...")
bert_tokenizer = BertTokenizer.from_pretrained(BERT_MODEL_PATH)
bert_model = BertForSequenceClassification.from_pretrained(BERT_MODEL_PATH)
bert_model.eval()  # inference mode, no training
print("Ready!\n")


def classify_claim(claim: str) -> dict:
    """
    BERT gatekeeper — runs before RAG pipeline.
    Returns whether claim is worth checking and confidence.
    """
    inputs = bert_tokenizer(
        claim,
        max_length=128,
        padding='max_length',
        truncation=True,
        return_tensors='pt'
    )

    with torch.no_grad():
        outputs = bert_model(**inputs)
        probabilities = torch.softmax(outputs.logits, dim=1)
        prediction = torch.argmax(probabilities, dim=1).item()
        confidence = probabilities[0][prediction].item()

    label = "credible" if prediction == 1 else "not_credible"

    return {
        "label": label,
        "confidence": round(confidence * 100, 1),
        "raw": prediction
    }


def extract_search_query(claim: str) -> str:
    """Ask Gemma to extract a clean short search query from the claim"""

    payload = {
        "model": "gemma",
        "messages": [
            {
                "role": "user",
                "content": f"""Extract the single most important factual claim 
from the text below and convert it into a short web search query of 
maximum 8 words. Return ONLY the search query, nothing else.

Text: {claim}"""
            }
        ],
        "temperature": 0.1,
        "max_tokens": 30
    }

    response = requests.post(LM_STUDIO_URL, json=payload)
    query = response.json()["choices"][0]["message"]["content"].strip()
    print(f"   Search query: '{query}'")
    return query


def search_web(query: str) -> list:
    """Search web for evidence using Tavily"""

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False
    }

    response = requests.post(url, json=payload)
    data = response.json()

    chunks = []
    for result in data.get("results", []):
        chunks.append({
            "title": result["title"],
            "url": result["url"],
            "content": result["content"]
        })

    return chunks


def get_relevant_chunks(claim: str, chunks: list, top_k: int = 3) -> list:
    """Use FAISS to find most relevant chunks for the claim"""

    if not chunks:
        return []

    claim_vector = embedder.encode([claim])
    chunk_texts = [c["content"] for c in chunks]
    chunk_vectors = embedder.encode(chunk_texts)

    dimension = chunk_vectors.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(chunk_vectors, dtype=np.float32))

    distances, indices = index.search(
        np.array(claim_vector, dtype=np.float32),
        min(top_k, len(chunks))
    )

    return [chunks[i] for i in indices[0]]


def format_evidence(chunks: list) -> str:
    """Format chunks into readable evidence string"""

    evidence = ""
    for i, chunk in enumerate(chunks, 1):
        evidence += f"\nSource {i}: {chunk['title']}\n"
        evidence += f"URL: {chunk['url']}\n"
        evidence += f"Content: {chunk['content']}\n"
        evidence += "-" * 50
    return evidence


def check_fact(claim: str) -> str:
    """Full pipeline: BERT gate → extract query → search → semantic filter → LLM verdict"""

    # Step 1 — BERT classifier as gatekeeper
    print("🤖 Running BERT classifier...")
    classification = classify_claim(claim)
    print(f"   BERT says: {classification['label']} ({classification['confidence']}% confidence)")

    # Step 2 — decide whether to proceed
    if classification['confidence'] > 85 and classification['label'] == "not_credible":
        # Very high confidence it's false — still verify but flag it
        print("   ⚠️  BERT flagged as likely not credible — verifying with RAG...")
    elif classification['confidence'] > 85 and classification['label'] == "credible":
        print("   ✅ BERT flagged as likely credible — verifying with RAG...")
    else:
        print("   🔍 BERT is uncertain — verifying with RAG...")

    # Step 3 — extract clean search query
    print("✂️  Extracting search query...")
    search_query = extract_search_query(claim)

    # Step 4 — search web
    print("🔍 Searching web for evidence...")
    all_chunks = search_web(search_query)
    print(f"   Found {len(all_chunks)} sources")

    # Step 5 — semantic search
    print("🧠 Finding most relevant chunks...")
    relevant_chunks = get_relevant_chunks(claim, all_chunks, top_k=3)
    print(f"   Selected {len(relevant_chunks)} most relevant sources")

    # Step 6 — format evidence
    evidence = format_evidence(relevant_chunks)

    # Step 7 — send to Gemma with BERT context included
    print("💬 Analysing with Gemma...")
    prompt = f"""You are a strict fact-checking assistant.
You must check the claim word-for-word against the evidence.
Pay close attention to partial truths — a claim can be MISLEADING if it is
only partly correct or leaves out important details.

A pre-screening classifier has already labelled this claim as: {classification['label'].upper()} 
with {classification['confidence']}% confidence. Use this as a hint but base 
your final verdict strictly on the evidence below.

Respond with:
- Verdict: (True / False / Misleading / Unverifiable)
- Reason: (2-3 sentences based strictly on the evidence provided)
- Confidence: (High / Medium / Low)
- Classifier hint: (what BERT predicted and whether evidence agrees)
- Sources used: (list the source titles you relied on)

Verdict definitions:
- True: the claim is FULLY accurate with no missing context
- False: the claim is factually wrong
- Misleading: the claim has partial truth but omits key details or exaggerates
- Unverifiable: evidence is insufficient to judge

Claim: {claim}

Evidence from web:
{evidence}

Important: Be strict. Base your verdict ONLY on the evidence.
Do not use your own training knowledge."""

    payload = {
        "model": "gemma",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 500
    }

    response = requests.post(LM_STUDIO_URL, json=payload)
    result = response.json()

    return result["choices"][0]["message"]["content"]


# --- Run it ---
if __name__ == "__main__":
    while True:
        claim = input("\nEnter a claim (or 'quit'): ")
        if claim.lower() == "quit":
            break
        print("\n--- Fact Check Result ---")
        print(check_fact(claim))
        print("\n--- End ---")
