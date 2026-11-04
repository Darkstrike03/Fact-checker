from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _ensure_venv() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit(
            "Virtual environment not found. Run:\n"
            "  python -m venv .venv\n"
            "  .\\.venv\\Scripts\\Activate.ps1\n"
            "  pip install -r requirements.txt"
        )
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(
            str(VENV_PYTHON),
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        )


def _cli_value(flag: str) -> str | None:
    args = sys.argv[1:]
    for index, value in enumerate(args):
        if value == flag and index + 1 < len(args):
            return args[index + 1]
        if value.startswith(f"{flag}="):
            return value.split("=", 1)[1]
    return None


_ensure_venv()
os.environ["LOCAL_DEMO"] = "true"
os.environ.setdefault("API_REQUEST_TIMEOUT", "150")
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
_requested_model = _cli_value("--model")
if _requested_model:
    os.environ["DEFAULT_MODEL"] = _requested_model

import config  # noqa: E402
import model_manager  # noqa: E402
import uvicorn  # noqa: E402

HOST = "127.0.0.1"
PORT = 8000
API_URL = f"http://{HOST}:{PORT}"
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/models"
WARMUP_CLAIM = "Apple released the iPhone 15 in September 2023."
MODEL = config.DEFAULT_MODEL


def _run(command: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _tail(result: subprocess.CompletedProcess[str], limit: int = 1200) -> str:
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return text[-limit:]


def _request_json(url: str, data: dict | None = None, timeout: int = 30):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload) if payload else {}


def _wait_for(url: str, timeout: int = 45) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _request_json(url, timeout=3)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, port)) == 0


def _find_lms() -> str | None:
    found = shutil.which("lms")
    if found:
        return found
    candidate = Path.home() / ".lmstudio" / "bin" / "lms.exe"
    return str(candidate) if candidate.exists() else None


def _stop_stale_api() -> None:
    if not _port_open(PORT):
        return
    try:
        info = _request_json(f"{API_URL}/", timeout=3)
    except Exception as exc:
        raise SystemExit(
            f"Port {PORT} is already in use by another program. "
            "Close it and run the demo again."
        ) from exc
    if info.get("name") != "Factly API":
        raise SystemExit(
            f"Port {PORT} is already in use by another program. "
            "Close it and run the demo again."
        )
    print("Stopping a previous Factly API instance...")
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'uvicorn\\s+api:app' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    _run(["powershell", "-NoProfile", "-Command", script], timeout=30)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _port_open(PORT):
        time.sleep(0.5)


def _ensure_lm_studio(lms: str | None) -> None:
    if _wait_for(LM_STUDIO_URL, timeout=2):
        print("LM Studio server is already running.")
    else:
        if not lms:
            raise SystemExit(
                "LM Studio is not running and the `lms` command was not found. "
                "Open LM Studio once, then run the demo again."
            )
        print("Starting the LM Studio server...")
        result = _run([lms, "server", "start"], timeout=90)
        if result.returncode != 0 or not _wait_for(LM_STUDIO_URL, timeout=45):
            raise SystemExit(
                "Could not start the LM Studio server.\n" + _tail(result)
            )

    if not lms:
        print("Warning: `lms` was not found; relying on LM Studio to load models on demand.")
        return

    print(f"Preparing one local model: {MODEL}")
    try:
        state = model_manager.ensure_only_model(MODEL)
        loaded = state.get("loaded") or []
        if loaded:
            print(f"Loaded model(s): {', '.join(loaded)}")
        else:
            print("Warning: LM Studio did not report a loaded model yet.")
    except Exception as exc:  # noqa: BLE001 - demo should still try to start
        print(f"Warning: could not preload {MODEL}: {exc}")
        print("The model may load on first use.")


def _stop_lm_studio(lms: str | None) -> None:
    if not lms:
        return
    print("Stopping the LM Studio server...")
    _run([lms, "server", "stop"], timeout=45)


def _warmup(open_browser: bool) -> bool:
    if not _wait_for(f"{API_URL}/", timeout=45):
        print("Warning: the API did not become ready in time.")
        return False
    print("Warming up retrieval and the local model (about 30-60 seconds)...")
    started = time.perf_counter()
    payload = {"claim": WARMUP_CLAIM, "model": MODEL}
    try:
        result = _request_json(f"{API_URL}/check", data=payload, timeout=180)
        output = (result.get("models") or [{}])[0]
        elapsed = time.perf_counter() - started
        label = output.get("label") or "No verdict"
        answer = output.get("answer") or output.get("reason") or ""
        print(f"Warm-up complete in {elapsed:.1f}s: {label}")
        if answer:
            print(f"Answer: {answer}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Warm-up warning: HTTP {exc.code} {detail}")
    except Exception as exc:
        print(f"Warm-up warning: {exc}")
    finally:
        if open_browser:
            print(f"Opening {API_URL}/ui/")
            webbrowser.open(f"{API_URL}/ui/")
    return True


def _run_smoke() -> None:
    server = uvicorn.Server(
        uvicorn.Config("api:app", host=HOST, port=PORT, log_level="warning")
    )

    def warm_and_stop() -> None:
        try:
            _warmup(open_browser=False)
        finally:
            server.should_exit = True

    worker = threading.Thread(target=warm_and_stop, daemon=True)
    worker.start()
    server.run()
    worker.join(timeout=5)


def main() -> None:
    smoke = "--smoke" in sys.argv
    no_warmup = "--no-warmup" in sys.argv
    open_browser = not smoke and "--no-browser" not in sys.argv
    lms = _find_lms()
    _stop_stale_api()
    print("=" * 64)
    print("Factly local demo")
    print(f"Model: {MODEL}")
    print("Keep this window open. Press Ctrl+C to stop the API and LM Studio.")
    print("=" * 64)
    try:
        _ensure_lm_studio(lms)
        if smoke:
            _run_smoke()
        else:
            if not no_warmup:
                threading.Thread(
                    target=_warmup, args=(open_browser,), daemon=True
                ).start()
            uvicorn.run(
                "api:app",
                host=HOST,
                port=PORT,
                log_level="warning",
            )
    except KeyboardInterrupt:
        pass
    finally:
        _stop_lm_studio(lms)
        print("Factly demo stopped.")


if __name__ == "__main__":
    main()
