import requests
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
TAVILY_API_KEY = "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"

# Load embedding model once at startup (not every query)
print("Loading embedding model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')  # small, fast, 90MB
print("Ready!")

def search_web(claim: str) -> list:
    """Search web for evidence about the claim using Tavily"""
    
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": claim,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False
    }
    
    response = requests.post(url, json=payload)
    data = response.json()
    
    # Return as list of chunks instead of one big string
    chunks = []
    for result in data.get("results", []):
        chunks.append({
            "title": result["title"],
            "url": result["url"],
            "content": result["content"]
        })
    
    return chunks


def get_relevant_chunks(claim: str, chunks: list, top_k: int = 3) -> list:
    """Use FAISS to find the most relevant chunks for the claim"""
    
    if not chunks:
        return []
    
    # Convert claim and chunks to vectors
    claim_vector = embedder.encode([claim])
    chunk_texts = [c["content"] for c in chunks]
    chunk_vectors = embedder.encode(chunk_texts)
    
    # Build FAISS index
    dimension = chunk_vectors.shape[1]  # vector size (384 for MiniLM)
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(chunk_vectors, dtype=np.float32))
    
    # Search for top_k most relevant chunks
    distances, indices = index.search(
        np.array(claim_vector, dtype=np.float32), 
        min(top_k, len(chunks))  # don't ask for more than we have
    )
    
    # Return only the most relevant chunks
    relevant = [chunks[i] for i in indices[0]]
    return relevant


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
    """Full pipeline: search → semantic filter → LLM verdict"""
    
    # Step 1 — get evidence from web
    print("🔍 Searching web for evidence...")
    all_chunks = search_web(claim)
    print(f"   Found {len(all_chunks)} sources")
    
    # Step 2 — semantic search, keep only most relevant chunks
    print("🧠 Finding most relevant chunks...")
    relevant_chunks = get_relevant_chunks(claim, all_chunks, top_k=3)
    print(f"   Selected {len(relevant_chunks)} most relevant sources")
    
    # Step 3 — format evidence
    evidence = format_evidence(relevant_chunks)
    
    # Step 4 — send to Gemma
    print("🤖 Analysing with Gemma...")
    prompt = f"""You are a strict fact-checking assistant.
You must check the claim word-for-word against the evidence.
Pay close attention to partial truths — a claim can be MISLEADING if it is 
only partly correct or leaves out important details.

Respond with:
- Verdict: (True / False / Misleading / Unverifiable)
- Reason: (2-3 sentences based strictly on the evidence provided)
- Confidence: (High / Medium / Low)
- Sources used: (list the source titles you relied on)

Verdict definitions:
- True: the claim is FULLY accurate with no missing context
- False: the claim is factually wrong
- Misleading: the claim has partial truth but omits key details or exaggerates
- Unverifiable: evidence is insufficient to judge

Claim: {claim}

Evidence from web:
{evidence}

Important: Be strict. If the claim says "cricket" but reality is only 
"Test cricket", that is Misleading, not True. 
Base your verdict ONLY on the evidence. Do not use your own training knowledge."""

    payload = {
        "model": "gemma",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 400
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