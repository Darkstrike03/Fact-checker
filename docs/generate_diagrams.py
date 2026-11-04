"""Generate the architecture and pipeline diagrams with Graphviz."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIAGRAMS_DIR = BASE_DIR / "docs" / "diagrams"

DOT_CANDIDATES = [
    shutil.which("dot"),
    r"C:\Program Files\Graphviz\bin\dot.exe",
    r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
]

LIVE_PIPELINE = """digraph live_pipeline {
  graph [rankdir=LR, bgcolor="white", pad="0.3", nodesep="0.35", ranksep="0.55"];
  node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11,
        fillcolor="#eef4ff", color="#3b5bdb", margin="0.18,0.10"];
  edge [fontname="Arial", fontsize=9, color="#555555"];

  claim [label="Claim", fillcolor="#fff4e6", color="#d9480f"];
  search [label="Playwright search\\nBrave Search HTML", fillcolor="#e7f5ff"];
  providers [label="Fallbacks\\nGoogle News RSS / Wikipedia", fillcolor="#f8f9fa"];
  fetch [label="Playwright page fetch\\ntrafilatura extraction"];
  sentences [label="Sentence splitter\\ndeduplicate + filter"];
  rank [label="SBERT embeddings\\nFAISS cosine top-k"];
  prompt [label="Evidence-grounded prompt\\nLABEL + REASON format"];
  llm [label="LM Studio model\\nLFM2.5 1.2B or Qwen3 0.6B"];
  parser [label="Strict parser\\nSUPPORTED / REFUTED", fillcolor="#e6fcf5", color="#0ca678"];
  result [label="UI result + sources", fillcolor="#fff0f6", color="#c2255c"];

  claim -> search;
  search -> providers [style=dashed, label="if empty"];
  search -> fetch;
  providers -> fetch [style=dashed];
  fetch -> sentences -> rank -> prompt -> llm -> parser -> result;
  rank -> result [style=dotted, label="selected evidence"];
}
"""

EVALUATION_PIPELINE = """digraph evaluation_pipeline {
  graph [rankdir=LR, bgcolor="white", pad="0.3", nodesep="0.35", ranksep="0.55"];
  node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11,
        fillcolor="#f3f0ff", color="#6741d9", margin="0.18,0.10"];
  edge [fontname="Arial", fontsize=9, color="#555555"];

  splits [label="Official COVID-Fact splits\\ntrain / dev / test", fillcolor="#fff4e6", color="#d9480f"];
  settings [label="Evaluation grid\\nmodel x prompt x evidence mode"];
  gold [label="Gold evidence\\nsentence1"];
  retrieved [label="Retrieved evidence\\nPlaywright cache + FAISS top-5"];
  claim_only [label="Claim-only baseline\\nno evidence"];
  runner [label="Incremental JSONL runner\\nresume + strict retry"];
  metrics [label="Metrics\\naccuracy, macro F1, per-class P/R/F1,\\nbootstrap CI, McNemar", fillcolor="#e6fcf5", color="#0ca678"];
  report [label="Results tables + figures\\nvs published paper numbers", fillcolor="#fff0f6", color="#c2255c"];

  splits -> settings;
  settings -> gold;
  settings -> retrieved;
  settings -> claim_only;
  gold -> runner;
  retrieved -> runner;
  claim_only -> runner;
  runner -> metrics -> report;
}
"""

SYSTEM_ARCHITECTURE = """digraph system_architecture {
  graph [rankdir=TB, bgcolor="white", pad="0.3", nodesep="0.45", ranksep="0.45"];
  node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11,
        fillcolor="#eef4ff", color="#3b5bdb", margin="0.18,0.10"];
  edge [fontname="Arial", fontsize=9, color="#555555"];

  app [label="app.py\\nGradio UI", fillcolor="#fff4e6", color="#d9480f"];
  pipeline [label="pipeline.py\\nlive orchestration", fillcolor="#fff0f6", color="#c2255c"];
  retrieval [label="retrieval.py\\nPlaywright search + page fetch"];
  evidence [label="evidence.py\\nsentences + SBERT/FAISS"];
  prompts [label="evaluation/prompts.py\\nstrict label prompts"];
  llm [label="llm_client.py\\nLM Studio OpenAI API"];
  eval [label="evaluation/\\nCOVID-Fact harness"];
  metrics [label="evaluation/metrics.py\\nmetrics + bootstrap + McNemar"];
  config [label="config.py\\npaths, models, settings", fillcolor="#f8f9fa"];
  resources [label="resources/\\npaper + TSV splits", fillcolor="#f8f9fa"];
  cache [label="cache/\\nPlaywright cache", fillcolor="#f8f9fa"];

  app -> pipeline;
  pipeline -> retrieval;
  pipeline -> evidence;
  pipeline -> prompts;
  pipeline -> llm;
  retrieval -> cache;
  eval -> retrieval;
  eval -> evidence;
  eval -> prompts;
  eval -> llm;
  eval -> metrics;
  eval -> resources;
  config -> app [style=dotted];
  config -> pipeline [style=dotted];
  config -> eval [style=dotted];
}
"""

DIAGRAMS = {
    "live_pipeline": LIVE_PIPELINE,
    "evaluation_pipeline": EVALUATION_PIPELINE,
    "system_architecture": SYSTEM_ARCHITECTURE,
}


def find_dot() -> str | None:
    for candidate in DOT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def main() -> None:
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    dot = find_dot()
    if not dot:
        raise SystemExit("Graphviz dot was not found. Install Graphviz or add it to PATH.")

    for name, source in DIAGRAMS.items():
        dot_path = DIAGRAMS_DIR / f"{name}.dot"
        dot_path.write_text(source, encoding="utf-8")
        for suffix in ("png", "svg"):
            output_path = DIAGRAMS_DIR / f"{name}.{suffix}"
            subprocess.run(
                [dot, f"-T{suffix}", str(dot_path), "-o", str(output_path)],
                check=True,
            )
            print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
