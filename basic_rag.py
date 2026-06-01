import requests

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
TAVILY_API_KEY = "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"

def search_web(claim: str) -> str:
    """Search web for evidence about the claim using Tavily"""
    
    url = "https://api.tavily.com/search"
    
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": claim,
        "search_depth": "basic",       # basic = 1 credit, advanced = 2 credits
        "max_results": 5,              # top 5 sources
        "include_answer": False,       # we want raw results, not Tavily's summary
        "include_raw_content": False   # snippets are enough for now
    }
    
    response = requests.post(url, json=payload)
    data = response.json()
    
    # Format results into readable evidence text
    evidence = ""
    for i, result in enumerate(data.get("results", []), 1):
        evidence += f"\nSource {i}: {result['title']}\n"
        evidence += f"URL: {result['url']}\n"
        evidence += f"Content: {result['content']}\n"
        evidence += "-" * 50
    
    return evidence


def check_fact(claim: str) -> str:
    """Send claim + evidence to Gemma for verdict"""
    
    # Step 1 — get evidence from web
    print("🔍 Searching web for evidence...")
    evidence = search_web(claim)
    
    # Step 2 — build prompt with evidence
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

    # Step 3 — send to Gemma via LM Studio
    print("🤖 Analysing with Gemma...")
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
