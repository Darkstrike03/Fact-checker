import os
import socket
from pathlib import Path

from dotenv import load_dotenv
import gradio as gr
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import torch
from transformers import BertTokenizer, BertForSequenceClassification

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LOCAL_BERT_PATH = BASE_DIR / "fact_checker_bert"
BERT_MODEL_PATH = os.getenv(
    "BERT_MODEL_PATH",
    str(LOCAL_BERT_PATH)
    if (LOCAL_BERT_PATH / "model.safetensors").exists()
    else "DarkStrike/fact-checker-bert",
)
GRADIO_SERVER_NAME = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
GRADIO_SERVER_PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
GRADIO_SHARE = os.getenv("GRADIO_SHARE", "True").lower() in {"1", "true", "yes", "on"}

if not TAVILY_API_KEY:
    raise RuntimeError("TAVILY_API_KEY is missing. Copy .env.example to .env and set it.")


def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"

# --- Load models at startup ---
print("Loading embedding model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')

print("Loading BERT classifier...")
bert_tokenizer = BertTokenizer.from_pretrained(BERT_MODEL_PATH)
bert_model = BertForSequenceClassification.from_pretrained(BERT_MODEL_PATH)
bert_model.eval()
print("All models ready!\n")


def classify_claim(claim):
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
    return {"label": label, "confidence": round(confidence * 100, 1)}


def extract_search_query(claim):
    payload = {
        "model": "gemma",
        "messages": [{"role": "user", "content": f"""Extract the single most 
important factual claim from the text below and convert it into a short web 
search query of maximum 8 words. Return ONLY the search query, nothing else.
Text: {claim}"""}],
        "temperature": 0.1,
        "max_tokens": 30
    }
    response = requests.post(LM_STUDIO_URL, json=payload)
    return response.json()["choices"][0]["message"]["content"].strip()


def search_web(query):
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


def get_relevant_chunks(claim, chunks, top_k=3):
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


def format_evidence(chunks):
    evidence = ""
    for i, chunk in enumerate(chunks, 1):
        evidence += f"\nSource {i}: {chunk['title']}\n"
        evidence += f"URL: {chunk['url']}\n"
        evidence += f"Content: {chunk['content']}\n"
        evidence += "-" * 50
    return evidence


def check_fact_gradio(claim):
    """Main function called by Gradio — returns formatted results"""

    if not claim.strip():
        return "⚠️ Please enter a claim.", "", "", ""

    try:
        # Step 1 — BERT classifier
        classification = classify_claim(claim)
        bert_label = classification['label']
        bert_conf = classification['confidence']

        # Step 2 — extract query
        search_query = extract_search_query(claim)

        # Step 3 — search web
        all_chunks = search_web(search_query)

        # Step 4 — semantic search
        relevant_chunks = get_relevant_chunks(claim, all_chunks, top_k=3)

        # Step 5 — format evidence
        evidence = format_evidence(relevant_chunks)

        # Step 6 — sources for display
        sources_display = ""
        for i, chunk in enumerate(relevant_chunks, 1):
            sources_display += f"**{i}. {chunk['title']}**\n{chunk['url']}\n\n"

        # Step 7 — Gemma verdict
        prompt = f"""You are a strict fact-checking assistant.
You must check the claim word-for-word against the evidence.
Pay close attention to partial truths — a claim can be MISLEADING if it is
only partly correct or leaves out important details.

A pre-screening classifier has already labelled this claim as: {bert_label.upper()} 
with {bert_conf}% confidence. Use this as a hint but base 
your final verdict strictly on the evidence below.

Respond with EXACTLY this format:
VERDICT: (True / False / Misleading / Unverifiable)
REASON: (2-3 sentences based strictly on the evidence)
CONFIDENCE: (High / Medium / Low)

Verdict definitions:
- True: claim is FULLY accurate with no missing context
- False: claim is factually wrong
- Misleading: partial truth but omits key details or exaggerates
- Unverifiable: evidence is insufficient to judge

Claim: {claim}

Evidence from web:
{evidence}

Be strict. Base verdict ONLY on evidence provided."""

        payload = {
            "model": "gemma",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 300
        }

        response = requests.post(LM_STUDIO_URL, json=payload)
        raw_result = response.json()["choices"][0]["message"]["content"]

        # Parse verdict for color coding
        verdict = "Unverifiable"
        for line in raw_result.split('\n'):
            if line.startswith('VERDICT:'):
                verdict = line.replace('VERDICT:', '').strip()
                break

        # Color code the verdict
        verdict_colors = {
            "True": "✅ TRUE",
            "False": "❌ FALSE",
            "Misleading": "⚠️ MISLEADING",
            "Unverifiable": "❓ UNVERIFIABLE"
        }
        verdict_display = verdict_colors.get(verdict, f"❓ {verdict}")

        # BERT summary
        bert_icon = "🟢" if bert_label == "credible" else "🔴"
        bert_display = f"{bert_icon} BERT Pre-screen: {bert_label.upper()} ({bert_conf}%)\n🔍 Search query used: '{search_query}'"

        return verdict_display, raw_result, bert_display, sources_display

    except Exception as e:
        return "❌ Error", str(e), "", ""


# --- Gradio UI ---
with gr.Blocks(title="Fact Checker") as app:

    gr.Markdown("""
    # 🔍 Automated Fact Checker
    **Powered by Gemma + BERT + RAG (Tavily + FAISS)**
    
    Enter any social media claim and get a verdict backed by real web evidence.
    """)

    with gr.Row():
        with gr.Column(scale=3):
            claim_input = gr.Textbox(
                label="Enter Claim",
                placeholder="e.g. The Great Wall of China is visible from space...",
                lines=3
            )
            submit_btn = gr.Button("🔍 Check Fact", variant="primary", size="lg")

    with gr.Row():
        verdict_output = gr.Textbox(label="Verdict", lines=1)
        bert_output = gr.Textbox(label="BERT Pre-screen", lines=2)

    with gr.Row():
        full_output = gr.Textbox(label="Full Analysis", lines=8)

    with gr.Row():
        sources_output = gr.Markdown(label="Sources Used")

    # Examples
    gr.Examples(
        examples=[
            ["The Great Wall of China is visible from space with the naked eye"],
            ["Elon Musk founded Tesla"],
            ["Virat Kohli retired from cricket"],
            ["Albert Einstein failed mathematics in school"],
            ["The Titanic sank in 1912"],
        ],
        inputs=claim_input
    )

    submit_btn.click(
        fn=check_fact_gradio,
        inputs=claim_input,
        outputs=[verdict_output, full_output, bert_output, sources_output]
    )

if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print(f"Gradio bind address: http://{GRADIO_SERVER_NAME}:{GRADIO_SERVER_PORT}")
    print(f"Open from this PC: http://127.0.0.1:{GRADIO_SERVER_PORT}")
    print(f"Open from your phone on the same Wi-Fi: http://{lan_ip}:{GRADIO_SERVER_PORT}")
    if GRADIO_SHARE:
        print("Gradio share link enabled for external/mobile access.")

    app.launch(
        server_name=GRADIO_SERVER_NAME,
        server_port=GRADIO_SERVER_PORT,
        share=GRADIO_SHARE
    )
    