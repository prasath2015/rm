# Remote Desktop Command Web (Flask + HTML/CSS/JS)

This project creates a local web app that you can open on your **phone** to control your **desktop**.

## Features

- Text command bar
- Voice command input (Web Speech API in browser)
- Command queue + activity log
- Desktop automation via `pyautogui`
- File operations like create/open file
- Optional API token (`REMOTE_API_TOKEN`) for local-network protection

## Example commands

- `open browser`
- `open file manager`
- `create file notes.txt`
- `open file ~/notes.txt`
- `type hello from phone`
- `press enter`
- `hotkey ctrl+s`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

When started, terminal will show both URLs:

- Desktop: `http://127.0.0.1:5000`
- Phone (same Wi-Fi): `http://<your-local-ip>:5000`

## Optional security token

```bash
export REMOTE_API_TOKEN="change-me"
python app.py
```

If enabled, enter the same token in the web page before sending commands.

## Important notes

- Run this app on the desktop machine that should receive commands.
- Keep that machine unlocked and focused where needed.
- For voice input, use a browser that supports Web Speech API (Chrome/Edge).
- `pyautogui` requires a graphical session.
- This is a local-network tool. Do not expose it publicly.
