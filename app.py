"""Gradio interface for the Factly evidence-first claim checker."""

from __future__ import annotations

import html
import socket

import gradio as gr

import config
import llm_client
import model_manager
import pipeline


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def available_models() -> list[str]:
    models = llm_client.list_chat_models()
    for fallback in (config.DEFAULT_MODEL, config.SECOND_MODEL):
        if fallback not in models:
            models.append(fallback)
    return models


def _status_html(result: dict | None, error: str = "") -> str:
    if not result or error:
        reason = html.escape(error or "No result was returned.")
        return (
            '<div style="padding:16px 18px;border-radius:12px;'
            'background:#fef3f2;color:#a61b1b;border:1px solid #fecdca;">'
            '<div style="font-size:15px;font-weight:600;">Check failed</div>'
            f'<div style="margin-top:8px;font-size:14px;color:#444;">{reason}</div>'
            "</div>"
        )

    label = str(result.get("label") or "UNVERIFIED").upper()
    if label == "SUPPORTED":
        background, color = "#e7f6ea", "#116329"
    elif label == "REFUTED":
        background, color = "#fde8e7", "#a61b1b"
    else:
        background, color = "#f2f2f2", "#444444"

    answer = html.escape(
        result.get("answer") or result.get("reason") or "No answer was returned."
    )
    reason = html.escape(result.get("reason") or "")
    confidence = html.escape(str(result.get("confidence") or "LOW").upper())
    citations = result.get("citations") or []
    citation_text = " ".join(f"[{int(number)}]" for number in citations)
    citation_html = (
        f'<div style="margin-top:10px;font-size:12px;color:#666;">'
        f"Citations used: {html.escape(citation_text)}</div>"
        if citations
        else ""
    )
    return (
        f'<div style="padding:16px 18px;border-radius:12px;'
        f'background:{background};color:{color};border:1px solid {color}33;">'
        f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">'
        f'<span style="font-size:13px;font-weight:700;letter-spacing:0.08em;">'
        f"{label}</span>"
        f'<span style="font-size:12px;padding:2px 8px;border-radius:999px;'
        f'background:{color}18;">{confidence} confidence</span>'
        f"</div>"
        f'<div style="margin-top:10px;font-size:20px;line-height:1.35;'
        f'font-weight:600;color:#1f1f1f;">{answer}</div>'
        f'<div style="margin-top:8px;font-size:13px;color:#555;">{reason}</div>'
        f"{citation_html}"
        f"</div>"
    )


def _sources_markdown(result: dict) -> str:
    selected = result.get("selected_evidence") or []
    retrieval = result.get("retrieval") or {}
    provider = retrieval.get("provider") or "none"
    lines = [
        f"**Evidence provider:** {provider} | "
        f"**Pages fetched:** {len(retrieval.get('results', []))} | "
        f"**Selected passages:** {len(selected)}"
    ]
    if not selected:
        error = retrieval.get("error")
        lines.append("")
        lines.append(
            "No usable evidence sentences were retrieved."
            + (f" Retrieval error: `{html.escape(str(error))}`" if error else "")
        )
        return "\n".join(lines)

    lines.append("")
    for number, sentence in enumerate(selected, start=1):
        title = html.escape(sentence.get("title") or "Untitled source")
        url = sentence.get("url") or ""
        text = html.escape((sentence.get("text") or "")[:700])
        published = sentence.get("published_at")
        score = sentence.get("score")
        meta = []
        if published:
            meta.append(str(published)[:10])
        if score is not None:
            meta.append(f"similarity {score:.3f}")
        meta_text = f" ({', '.join(meta)})" if meta else ""
        if url:
            lines.append(f"{number}. [{title}]({url}){meta_text}")
        else:
            lines.append(f"{number}. **{title}**{meta_text}")
        lines.append(f"   > {text}")
        lines.append("")
    return "\n".join(lines)


def _meta_markdown(result: dict) -> str:
    retrieval = result.get("retrieval") or {}
    checks = result.get("checks") or {}
    lines = [
        f"- Model: `{html.escape(str(result.get('model', '')))}`",
        f"- Confidence: `{html.escape(str(result.get('confidence', '')))}`",
        f"- Evidence mode: live Playwright retrieval",
        f"- Search provider: `{retrieval.get('provider') or 'none'}`",
        f"- Cached retrieval: `{bool(retrieval.get('cached'))}`",
        f"- Retried for a strict answer: `{bool(result.get('retried'))}`",
        f"- Latency: `{result.get('latency_seconds', 0.0):.2f}s`",
        f"- Retrieval quality: `{checks.get('relevance_label', 'unknown')}`",
    ]
    return "\n".join(lines)


def _raw_markdown(result: dict) -> str:
    raw = (result.get("raw_response") or "").strip()
    if not raw:
        return "No raw model output."
    return "```text\n" + raw[:5000] + "\n```"


def check_claim_ui(claim: str, model: str) -> tuple[str, str, str, str]:
    claim = (claim or "").strip()
    if not claim:
        return (
            _status_html(None, "Please enter a claim."),
            "No evidence retrieved.",
            "",
            "",
        )

    try:
        model_manager.ensure_only_model(model)
        result = pipeline.check_claim(claim, model=model, use_bert=False)
    except Exception as exc:  # noqa: BLE001 - shown in the UI
        return (
            _status_html(None, f"Pipeline error: {exc}"),
            "",
            "",
            str(exc),
        )

    return (
        _status_html(result),
        _sources_markdown(result),
        _meta_markdown(result),
        _raw_markdown(result),
    )


def _evaluation_markdown() -> str:
    summary_path = config.RESULTS_DIR / "summary.md"
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8")
    return (
        "No evaluation summary yet.\n\n"
        "Run:\n"
        "```powershell\n"
        ".venv\\Scripts\\python.exe -m evaluation.evaluate_covidfact "
        "--split test --mode gold --prompt both\n"
        "```"
    )


def _pipeline_image() -> str | None:
    path = config.DIAGRAMS_DIR / "live_pipeline.png"
    return str(path) if path.exists() else None


chat_models = available_models()
health = llm_client.health_check()
if health.get("reachable"):
    health_text = (
        f"LM Studio reachable at `{health['url']}`. "
        f"Chat models: {', '.join(health['chat_models']) or 'none reported'}."
    )
else:
    health_text = (
        f"LM Studio is not reachable at `{health['url']}`. "
        "Start the server and load a model before checking claims."
    )

with gr.Blocks(title="Factly - Social-media Claim Checker") as app:
    gr.Markdown(
        "# Factly\n"
        "Evidence-first fact checking for social-media claims. "
        "Factly searches the live web, ranks the strongest passages, and returns "
        "**SUPPORTED**, **REFUTED**, or **UNVERIFIED** with citations.\n\n"
        f"{health_text}"
    )

    with gr.Tabs():
        with gr.Tab("Check a claim"):
            with gr.Row():
                with gr.Column(scale=2):
                    claim_input = gr.Textbox(
                        label="Claim",
                        placeholder=(
                            "e.g. The Indian government banned TikTok in June 2020."
                        ),
                        lines=3,
                    )
                    model = gr.Dropdown(
                        choices=chat_models,
                        value=config.DEFAULT_MODEL,
                        label="Model (one loaded at a time)",
                    )
                    submit = gr.Button("Check claim", variant="primary")
                    gr.Examples(
                        examples=[
                            ["Narendra Modi visited Goa on 19 January 2023"],
                            ["The Indian government banned TikTok in June 2020"],
                            ["Apple released the iPhone 15 in September 2023"],
                            [
                                "NASA confirmed Earth will experience 15 days of "
                                "darkness in November 2025"
                            ],
                        ],
                        inputs=claim_input,
                    )

                with gr.Column(scale=3):
                    gr.Markdown("### Answer")
                    answer_output = gr.HTML()

            with gr.Row():
                evidence_output = gr.Markdown(label="Evidence used")
                with gr.Column():
                    meta_output = gr.Markdown(label="Run details")

            with gr.Accordion("Model draft before safety checks", open=False):
                raw_output = gr.Markdown()

            submit.click(
                fn=check_claim_ui,
                inputs=[claim_input, model],
                outputs=[answer_output, evidence_output, meta_output, raw_output],
            )
            claim_input.submit(
                fn=check_claim_ui,
                inputs=[claim_input, model],
                outputs=[answer_output, evidence_output, meta_output, raw_output],
            )

        with gr.Tab("Pipeline"):
            image_path = _pipeline_image()
            if image_path:
                gr.Image(
                    value=image_path,
                    label="Live retrieval-augmented pipeline",
                    buttons=["download", "fullscreen"],
                )
            else:
                gr.Markdown(
                    "Pipeline diagram not generated yet. Run "
                    "`python docs/generate_diagrams.py`."
                )
            gr.Markdown(
                "The live path uses Playwright to search the web and fetch pages, "
                "splits pages into sentences, ranks them against the claim with "
                "SBERT + FAISS, and asks the selected LM Studio model for an "
                "evidence-grounded answer. Deterministic date, entity, and source "
                "checks can downgrade a verdict to UNVERIFIED."
            )

        with gr.Tab("COVID-Fact reference benchmark"):
            gr.Markdown(_evaluation_markdown())

        with gr.Tab("Labels and method"):
            gr.Markdown(
                "## Live labels\n"
                "The live UI uses **SUPPORTED**, **REFUTED**, and **UNVERIFIED**. "
                "UNVERIFIED means the evidence was missing, weak, or did not confirm "
                "the claim's key details.\n\n"
                "The COVID-Fact benchmark stays binary: `entailment` maps to "
                "SUPPORTED and `not_entailment` maps to REFUTED.\n\n"
                "## Evidence policy\n"
                "The model sees only the selected retrieved passages. The evidence "
                "panel exposes the five passages used for the verdict and the wider "
                "set of retrieved candidates.\n\n"
                "## Reproducibility\n"
                "Evaluation scripts use the official train/dev/test TSV files and "
                "a strict binary parser. The test split is never used for prompt "
                "tuning."
            )

if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print(f"Binding: http://{config.GRADIO_SERVER_NAME}:{config.GRADIO_SERVER_PORT}")
    print(f"Local:   http://127.0.0.1:{config.GRADIO_SERVER_PORT}")
    print(f"LAN:     http://{lan_ip}:{config.GRADIO_SERVER_PORT}")
    if config.GRADIO_SHARE:
        print("Gradio share link enabled.")
    app.launch(
        server_name=config.GRADIO_SERVER_NAME,
        server_port=config.GRADIO_SERVER_PORT,
        share=config.GRADIO_SHARE,
        show_error=True,
    )
