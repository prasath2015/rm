import importlib
import os
import queue
import re
import socket
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@dataclass
class CommandEvent:
    text: str
    source: str
    status: str
    output: str
    created_at: str


command_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
command_log: list[CommandEvent] = []
MAX_LOG = 100
worker_started = False
worker_lock = threading.Lock()


SAFE_APP_LAUNCHERS = {
    "browser": ["xdg-open", "https://www.google.com"],
    "notepad": ["gedit"],
    "file manager": ["xdg-open", str(Path.home())],
    "terminal": ["x-terminal-emulator"],
}


def add_log(text: str, source: str, status: str, output: str) -> None:
    command_log.append(
        CommandEvent(
            text=text,
            source=source,
            status=status,
            output=output,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    if len(command_log) > MAX_LOG:
        del command_log[0]


def import_optional_module(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def ensure_desktop_modules():
    pyautogui = import_optional_module("pyautogui")
    pyperclip = import_optional_module("pyperclip")
    if pyautogui is None:
        raise RuntimeError("pyautogui is not installed. Install requirements and run on desktop GUI.")
    return pyautogui, pyperclip


def type_text(text: str) -> None:
    pyautogui, pyperclip = ensure_desktop_modules()
    if pyperclip:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.write(text, interval=0.03)


def run_desktop_command(raw_command: str) -> str:
    cmd = raw_command.strip().lower()
    pyautogui, _ = ensure_desktop_modules()

    if cmd in {"open browser", "open chrome", "launch browser"}:
        subprocess.Popen(SAFE_APP_LAUNCHERS["browser"])
        return "Opened browser."

    if cmd in {"open file manager", "open files"}:
        subprocess.Popen(SAFE_APP_LAUNCHERS["file manager"])
        return "Opened file manager."

    if cmd in {"open notepad", "open editor"}:
        subprocess.Popen(SAFE_APP_LAUNCHERS["notepad"])
        return "Opened text editor."

    if cmd.startswith("create file "):
        file_name = raw_command[len("create file "):].strip()
        if not file_name:
            raise ValueError("Missing file name. Try: create file notes.txt")
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file_name)
        file_path = Path.home() / safe_name
        file_path.touch(exist_ok=True)
        subprocess.Popen(["xdg-open", str(file_path)])
        return f"Created file: {file_path}"

    if cmd.startswith("open file "):
        file_path = Path(raw_command[len("open file "):].strip()).expanduser()
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")
        subprocess.Popen(["xdg-open", str(file_path)])
        return f"Opened file: {file_path}"

    if cmd.startswith("type "):
        text = raw_command[5:]
        type_text(text)
        return f"Typed text ({len(text)} chars)."

    if cmd in {"press enter", "enter"}:
        pyautogui.press("enter")
        return "Pressed Enter."

    if cmd in {"copy", "ctrl c"}:
        pyautogui.hotkey("ctrl", "c")
        return "Pressed Ctrl+C."

    if cmd in {"paste", "ctrl v"}:
        pyautogui.hotkey("ctrl", "v")
        return "Pressed Ctrl+V."

    if cmd in {"save", "ctrl s"}:
        pyautogui.hotkey("ctrl", "s")
        return "Pressed Ctrl+S."

    if cmd.startswith("hotkey "):
        keys = [k.strip() for k in raw_command[len("hotkey "):].split("+") if k.strip()]
        if not keys:
            raise ValueError("No keys provided. Example: hotkey ctrl+shift+n")
        pyautogui.hotkey(*keys)
        return f"Pressed hotkey: {' + '.join(keys)}"

    raise ValueError(
        "Unknown command. Examples: 'open browser', 'create file notes.txt', "
        "'type hello world', 'press enter', 'hotkey ctrl+s'"
    )


def worker_loop() -> None:
    while True:
        command_text, source = command_queue.get()
        try:
            output = run_desktop_command(command_text)
            add_log(command_text, source, "success", output)
        except Exception as exc:  # noqa: BLE001
            add_log(command_text, source, "error", str(exc))
        finally:
            command_queue.task_done()


def ensure_worker_started() -> None:
    global worker_started
    if worker_started:
        return
    with worker_lock:
        if worker_started:
            return
        threading.Thread(target=worker_loop, daemon=True).start()
        worker_started = True


def is_authorized(req: request) -> bool:
    token = os.getenv("REMOTE_API_TOKEN", "").strip()
    if not token:
        return True

    header_token = (req.headers.get("X-Remote-Token") or "").strip()
    body_token = ""
    if req.is_json:
        payload = req.get_json(silent=True) or {}
        body_token = (payload.get("token") or "").strip()

    return token in {header_token, body_token}


@app.get("/")
def home():
    ensure_worker_started()
    return render_template("index.html")


@app.post("/api/command")
def queue_command():
    ensure_worker_started()
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized request."}), 401

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    source = (payload.get("source") or "phone").strip()

    if not text:
        return jsonify({"ok": False, "error": "Command text is required."}), 400

    command_queue.put((text, source))
    add_log(text, source, "queued", "Waiting for desktop execution...")
    return jsonify({"ok": True, "message": "Command queued.", "text": text})


@app.get("/api/logs")
def get_logs():
    ensure_worker_started()
    if not is_authorized(request):
        return jsonify({"ok": False, "error": "Unauthorized request."}), 401
    return jsonify({"ok": True, "logs": [event.__dict__ for event in reversed(command_log)]})


@app.get("/api/health")
def health():
    ensure_worker_started()
    return jsonify({"ok": True, "queue_size": command_queue.qsize(), "worker_started": worker_started})


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    ensure_worker_started()
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "5000"))
    print("=" * 60)
    print("Remote Desktop Command Web Started")
    print(f"Open on desktop: http://127.0.0.1:{port}")
    print(f"Open on phone  : http://{local_ip()}:{port}")
    if os.getenv("REMOTE_API_TOKEN"):
        print("Security enabled: phone must send REMOTE_API_TOKEN.")
    print("Keep this running on your desktop; phone commands execute here.")
    print("=" * 60)
    app.run(host=host, port=port, debug=False)
