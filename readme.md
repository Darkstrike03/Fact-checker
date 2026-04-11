# 🔍 Automated Fact Checker — Social Media Claims
**4th Year Project | Dept. of Computer Science & Engineering | RCCIIT**
Faculty Supervisor: Dr. Anup Kumar Kolya

---

## 📌 Project Overview

This project is an end-to-end automated fact-checking system for social media claims. It uses a **Retrieval-Augmented Generation (RAG)** pipeline to verify claims by fetching real-time web evidence and reasoning over it using a local Large Language Model (LLM).

The system is designed to go beyond simple LLM fact-checking (which relies on training memory and can hallucinate) by grounding every verdict in **live retrieved evidence from the web**.

---

## 🧠 Architecture

The full planned pipeline has 4 layers:

```
User inputs a social media claim
            ↓
┌─────────────────────────────┐
│  Layer 1: Classifier        │  ← Fine-tuned BERT (Step 4, Kaggle)
│  Is this even a claim?      │
│  Categories:                │
│  - Not a claim (skip)       │
│  - Racist / harmful         │
│  - Misleading               │
│  - Needs verification       │
└─────────────────────────────┘
            ↓ (only if verifiable)
┌─────────────────────────────┐
│  Layer 2: Query Extraction  │  ← Gemma extracts clean search query
│  Long claim → short query   │
└─────────────────────────────┘
            ↓
┌─────────────────────────────┐
│  Layer 3: Web Search (RAG)  │  ← Tavily API fetches real evidence
│  Returns top 5 sources      │
└─────────────────────────────┘
            ↓
┌─────────────────────────────┐
│  Layer 4: Semantic Search   │  ← sentence-transformers + FAISS
│  Picks top 3 relevant chunks│
│  from retrieved sources     │
└─────────────────────────────┘
            ↓
┌─────────────────────────────┐
│  Layer 5: LLM Reasoning     │  ← Gemma 2B / Gemma 3 4B via LM Studio
│  claim + evidence → verdict │
└─────────────────────────────┘
            ↓
    Verdict + Reason + Confidence + Sources
```

---

## ✅ Progress Tracker

| Step | Description | Status |
|------|-------------|--------|
| Step 1 | Local LLM setup (Gemma via LM Studio) | ✅ Done |
| Step 2 | Web search integration (Tavily API) | ✅ Done |
| Step 3 | Semantic search (sentence-transformers + FAISS) | ✅ Done |
| Step 3.5 | Query extraction for long/complex claims | ✅ Done |
| Step 4 | BERT classifier fine-tuned (69% accuracy, F1: 0.69) | ✅ Done |
| Step 5 | Web UI (in progress) | 🔄 Pending |

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Core LLM | Gemma 2B / Gemma 3 4B (via LM Studio) | Reasoning and verdict generation |
| Web Search | Tavily API | Real-time evidence retrieval |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Converting text to vectors |
| Vector Search | FAISS (`faiss-cpu`) | Finding most relevant evidence chunks |
| Classifier | BERT (fine-tuning planned) | Claim gating and pre-classification |
| Language | Python 3.x | Everything |

---

## 💻 Local Setup

### Prerequisites

- Python 3.8+
- [LM Studio](https://lmstudio.ai/) installed with **Gemma 2B or Gemma 3 4B** downloaded
- A free [Tavily API key](https://tavily.com) (1,000 free searches/month)

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/fact-checker.git
cd fact-checker

# Install dependencies
pip install requests sentence-transformers faiss-cpu numpy
```

### LM Studio Setup

1. Open LM Studio
2. Download **Gemma 2B** or **Gemma 3 4B** model
3. Go to the **Local Server** tab (the `<->` icon)
4. Load the model and click **Start Server**
5. Server runs at `http://localhost:1234` — keep it running

### API Key Setup

Open `basic_rag.py` and replace:
```python
TAVILY_API_KEY = "your-tavily-api-key-here"
```
with your actual Tavily key from the dashboard.

### Run

```bash
python basic_rag.py
```

---

## 📁 File Structure

```
fact-checker/
│
├── basic_rag.py          # Main pipeline (Steps 1-3)
├── README.md             # This file
│
├── classifier/           # Step 4 — BERT fine-tuning (Kaggle)
│   ├── train.py          # Fine-tuning script (coming soon)
│   └── model/            # Saved model weights (coming soon)
│
└── datasets/             # Training data for classifier
    └── (coming soon)
```

---

## 🔬 How It Works — Step by Step

### Step 1 — Query Extraction
For long or complex claims, Gemma first extracts a clean 6-8 word search query. This prevents Tavily from returning 0 results on dense claims.

```
Input:  "The Haber-Bosch process which won Fritz Haber the 1918 Nobel Prize..."
Output: "Haber Bosch process Nobel Prize ammonia synthesis"
```

### Step 2 — Web Search (Tavily)
The clean query is sent to Tavily which returns top 5 real web sources with titles, URLs, and content snippets.

### Step 3 — Semantic Search (FAISS)
The claim and all retrieved chunks are converted to vectors using `all-MiniLM-L6-v2`. FAISS finds the top 3 most semantically relevant chunks. This filters noise and keeps the LLM context focused.

### Step 4 — LLM Verdict (Gemma)
The claim + top 3 evidence chunks are sent to Gemma with a strict prompt. The model must base its verdict **only on the provided evidence**, not its training memory.

### Output Format
```
- Verdict:    True / False / Misleading / Unverifiable
- Reason:     2-3 sentences based strictly on evidence
- Confidence: High / Medium / Low
- Sources:    List of source titles used
```

### Verdict Definitions
| Verdict | Meaning |
|---------|---------|
| True | Claim is fully accurate with no missing context |
| False | Claim is factually wrong |
| Misleading | Claim has partial truth but omits key details or exaggerates |
| Unverifiable | Evidence is insufficient to judge |

---

## 🧪 Test Cases & Results

| Claim | Expected | Result | Notes |
|-------|----------|--------|-------|
| "Earth is flat" | False | ✅ False | High confidence, scientific sources |
| "Virat Kohli resigned from cricket" | Misleading | ✅ Misleading | Only retired from Test cricket |
| "Mamata Banerjee is dead" | False | ✅ False | Web sources confirm she is alive |
| Long Haber-Bosch claim | Misleading | ✅ Misleading | Query extraction fixed 0-source issue |

---

## ⚠️ Known Issues & Fixes Applied

### Issue 1 — Long claims returning 0 sources
**Problem:** Tavily couldn't parse very long, complex claims as search queries.
**Fix:** Added a query extraction step where Gemma first converts the claim into a short search query before hitting Tavily.

### Issue 2 — Partial truths being marked as True
**Problem:** "Virat Kohli resigned from cricket" was marked True (he only retired from Test cricket).
**Fix:** Added explicit verdict definitions and a strict warning in the prompt forcing the model to treat partial truths as Misleading.

### Issue 3 — RAM constraints on 8GB laptop
**Problem:** Gemma + sentence-transformers together are heavy on low-RAM machines.
**Fix:** Load embedding model once at startup (not per query). Close all browser tabs and background apps when running.

---

## 🗺️ Roadmap

### Current Phase (Local Pipeline)
- [x] LLM working locally via LM Studio
- [x] Tavily web search integration
- [x] FAISS semantic search
- [x] Query extraction for complex claims
- [x] Strict prompting for partial truth detection

### Next Phase (Kaggle — GPU Required)
- [ ] Fine-tune BERT classifier on LIAR / ClaimBuster dataset
- [ ] Integrate classifier as gatekeeper before LLM
- [ ] Classifier categories: Not a claim / Harmful / Misleading / Needs verification

### Final Phase
- [ ] Connect all components into single pipeline
- [ ] Simple web UI (Streamlit or Gradio)
- [ ] Evaluation metrics (accuracy, F1 score on test set)
- [ ] Project report and documentation

---

## 📚 Datasets for Classifier (Step 4)

| Dataset | Size | Use |
|---------|------|-----|
| [LIAR](https://huggingface.co/datasets/liar) | 12.8k claims | Multi-class claim labeling |
| [ClaimBuster](https://idir.uta.edu/claimbuster/) | ~23k sentences | Detects if something is even a claim |
| [FakeNewsNet](https://github.com/KaiDMML/FakeNewsNet) | Large | Social media specific fake news |
| [FEVER](https://fever.ai/) | 185k claims | Fact verification focused |

**Recommended starting point:** LIAR dataset + ClaimBuster combined for the gatekeeper classifier.

---

## 📖 Key Concepts

**RAG (Retrieval-Augmented Generation):** Instead of relying on the LLM's training memory, RAG fetches real external evidence first and forces the model to reason over that evidence. This dramatically reduces hallucination.

**Semantic Search:** Text is converted to numerical vectors (embeddings) that capture meaning. FAISS finds vectors most similar to the query vector — meaning-based search, not keyword matching.

**Embedding Model:** `all-MiniLM-L6-v2` is a small (~90MB) pre-trained model that converts text to 384-dimensional vectors. No training needed — just use it as a tool.

**Fine-tuning:** Taking a pre-trained model (BERT) and training it further on a specific task/dataset. The classifier will be fine-tuned on fact-checking datasets so it specialises in claim classification.

---

## 🖥️ Hardware Notes

- **Development machine:** Windows laptop, 8GB RAM, no GPU
- **LM Studio + Gemma 2B:** ~3-4GB RAM
- **sentence-transformers:** ~500MB RAM
- **FAISS:** Negligible
- **Fine-tuning (Step 4):** Requires GPU → use Kaggle (30 hrs free GPU/week)

---

## 📄 Project Proposal Reference

**Title:** Fact Checking on Social Media Claims
**Faculty:** Dr. Anup Kumar Kolya, Dept. of CSE, RCCIIT
**Proposed Area:** End-to-end automated fact-checking framework using deep learning and RAG frameworks for social media texts.
**Prerequisites:** Basic concepts of LLMs, prompting techniques, deep learning.

---

## 🔗 References & Tools

- [LM Studio](https://lmstudio.ai/) — Local LLM server
- [Tavily](https://tavily.com) — AI-native search API
- [sentence-transformers](https://www.sbert.net/) — Embedding models
- [FAISS](https://github.com/facebookresearch/faiss) — Vector similarity search
- [Hugging Face](https://huggingface.co/) — BERT models and datasets
- [Kaggle](https://www.kaggle.com/) — Free GPU for fine-tuning

---

*Last updated: April 2026 | Steps 1-3 complete*
