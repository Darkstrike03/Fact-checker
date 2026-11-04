"""Gradio interface for the COVID-Fact evidence checker."""

from __future__ import annotations

import html
import socket
from pathlib import Path

import gradio as gr

import config
import llm_client
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


def _status_html(label: str | None, reason: str) -> str:
    if label == "SUPPORTED":
        background, color = "#e7f6ea", "#116329"
        heading = "SUPPORTED"
    elif label == "REFUTED":
        background, color = "#fde8e7", "#a61b1b"
        heading = "REFUTED"
    else:
        background, color = "#f2f2f2", "#444444"
        heading = "No verdict"

    reason_text = html.escape(reason or "No reason was returned.")
    return (
        f'<div style="padding:14px 18px;border-radius:10px;'
        f'background:{background};color:{color};border:1px solid {color}33;">'
        f'<div style="font-size:24px;font-weight:700;letter-spacing:0.04em;">'
        f"{heading}</div>"
        f'<div style="margin-top:8px;font-size:14px;color:#333;">{reason_text}</div>'
        f"</div>"
    )


def _bert_markdown(bert: dict | None) -> str:
    if not bert:
        return "BERT pre-screen disabled."
    if "error" in bert:
        return f"BERT pre-screen unavailable: `{html.escape(str(bert['error']))}`"
    return (
        f"**BERT pre-screen:** {bert['label']} "
        f"({bert['confidence']:.1%} confidence). "
        "This is a hint only; the LLM verdict uses retrieved evidence."
    )


def _sources_markdown(result: dict) -> str:
    selected = result.get("selected_evidence") or []
    retrieval = result.get("retrieval") or {}
    provider = retrieval.get("provider") or "none"
    lines = [
        f"**Evidence provider:** {provider} | "
        f"**Pages fetched:** {len(retrieval.get('results', []))}"
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
        score = sentence.get("score")
        score_text = f" (similarity {score:.3f})" if score is not None else ""
        if url:
            lines.append(f"{number}. [{title}]({url}){score_text}")
        else:
            lines.append(f"{number}. **{title}**{score_text}")
        lines.append(f"   > {text}")
        lines.append("")
    return "\n".join(lines)


def _meta_markdown(result: dict) -> str:
    retrieval = result.get("retrieval") or {}
    lines = [
        f"- Model: `{html.escape(str(result.get('model', '')))}`",
        f"- Evidence mode: live Playwright retrieval",
        f"- Search provider: `{retrieval.get('provider') or 'none'}`",
        f"- Cached retrieval: `{bool(retrieval.get('cached'))}`",
        f"- Retried for a strict label: `{bool(result.get('retried'))}`",
        f"- Latency: `{result.get('latency_seconds', 0.0):.2f}s`",
    ]
    return "\n".join(lines)


def _raw_markdown(result: dict) -> str:
    raw = (result.get("raw_response") or "").strip()
    if not raw:
        return "No raw model output."
    return "```text\n" + raw[:5000] + "\n```"


def check_claim_ui(
    claim: str,
    primary_model: str,
    secondary_model: str,
    use_bert: bool,
) -> tuple[str, str, str, str, str, str, str]:
    claim = (claim or "").strip()
    if not claim:
        empty = _status_html(None, "Please enter a claim.")
        return empty, empty, "No evidence retrieved.", "BERT pre-screen disabled.", "", "", ""

    try:
        comparison = pipeline.compare_models(
            claim,
            models=[primary_model, secondary_model],
            use_bert=use_bert,
        )
    except Exception as exc:  # noqa: BLE001 - shown in the UI
        error = _status_html(None, f"Pipeline error: {exc}")
        return error, error, "", "", "", "", str(exc)

    primary, secondary = comparison["models"]
    evidence_markdown = _sources_markdown(
        {
            "selected_evidence": comparison["evidence_bundle"]["selected"],
            "retrieval": comparison["evidence_bundle"]["retrieval"],
        }
    )
    primary_status = _status_html(primary.get("label"), primary.get("reason", ""))
    secondary_status = _status_html(
        secondary.get("label"), secondary.get("reason", "")
    )
    return (
        primary_status,
        secondary_status,
        evidence_markdown,
        _bert_markdown(comparison.get("bert")),
        _meta_markdown(primary),
        _raw_markdown(primary),
        _raw_markdown(secondary),
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

with gr.Blocks(title="COVID-Fact Evidence Checker") as app:
    gr.Markdown(
        "# COVID-Fact Evidence Checker\n"
        "Retrieval-grounded fact checking with two small local models. "
        "The primary labels follow the COVID-Fact dataset: **SUPPORTED** or **REFUTED**.\n\n"
        f"{health_text}"
    )

    with gr.Tabs():
        with gr.Tab("Live fact check"):
            with gr.Row():
                with gr.Column(scale=2):
                    claim_input = gr.Textbox(
                        label="Claim",
                        placeholder=(
                            "e.g. COVID-19 vaccines reduce hospitalisation."
                        ),
                        lines=3,
                    )
                    with gr.Row():
                        primary_model = gr.Dropdown(
                            choices=chat_models,
                            value=config.DEFAULT_MODEL,
                            label="Primary model",
                        )
                        secondary_model = gr.Dropdown(
                            choices=chat_models,
                            value=config.SECOND_MODEL,
                            label="Comparison model",
                        )
                    use_bert = gr.Checkbox(
                        label="Run optional BERT pre-screen (not used for the final label)",
                        value=False,
                    )
                    submit = gr.Button("Check claim", variant="primary")
                    gr.Examples(
                        examples=[
                            ["COVID-19 vaccines reduce hospitalisation."],
                            ["Ivermectin is a proven cure for COVID-19."],
                            ["SARS-CoV-2 can spread through aerosols."],
                            ["The COVID-19 vaccine changes your DNA."],
                        ],
                        inputs=claim_input,
                    )

                with gr.Column(scale=3):
                    gr.Markdown("### Primary model")
                    primary_output = gr.HTML()
                    gr.Markdown("### Comparison model")
                    secondary_output = gr.HTML()

            with gr.Row():
                evidence_output = gr.Markdown(label="Evidence used")
                with gr.Column():
                    bert_output = gr.Markdown(label="BERT pre-screen")
                    meta_output = gr.Markdown(label="Run details")

            with gr.Accordion("Raw model outputs", open=False):
                primary_raw = gr.Markdown()
                secondary_raw = gr.Markdown()

            submit.click(
                fn=check_claim_ui,
                inputs=[claim_input, primary_model, secondary_model, use_bert],
                outputs=[
                    primary_output,
                    secondary_output,
                    evidence_output,
                    bert_output,
                    meta_output,
                    primary_raw,
                    secondary_raw,
                ],
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
                "SBERT + FAISS, and asks each LM Studio model for a strict "
                "SUPPORTED/REFUTED label using only the selected evidence."
            )

        with gr.Tab("COVID-Fact evaluation"):
            gr.Markdown(_evaluation_markdown())

        with gr.Tab("Labels and method"):
            gr.Markdown(
                "## Dataset-aligned labels\n"
                "The official COVID-Fact RTE data uses `entailment` and "
                "`not_entailment`. This project maps them to **SUPPORTED** and "
                "**REFUTED** only.\n\n"
                "The live UI does not invent `True`, `False`, `Misleading`, or "
                "`Unverifiable` verdicts. If retrieval finds no usable evidence, "
                "the UI says **No verdict** instead of guessing.\n\n"
                "## Evidence policy\n"
                "The model sees only the selected retrieved sentences. The optional "
                "BERT screen is shown as a hint, not as the final verdict.\n\n"
                "## Reproducibility\n"
                "Evaluation scripts use the official train/dev/test TSV files and "
                "the same strict label parser. The test split is never used for "
                "prompt tuning."
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
