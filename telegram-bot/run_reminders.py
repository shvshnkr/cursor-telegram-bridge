#!/usr/bin/env python3
"""
Check reminders.json for due reminders and send them via Telegram.
If a reminder has "prompt", run the Cursor agent with that prompt and send its
reply; otherwise send "text" as a fixed message. Uses the same config and
chat_id as agent_bot.py (chat_id is written by the bot when you message it).
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config")
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")
REMINDERS_FILE = os.path.join(SCRIPT_DIR, "reminders.json")
BASE = "https://api.telegram.org/bot"
DEFAULT_AGENT_TIMEOUT = 0  # 0 = unlimited


def load_config():
    """Return (token, chat_id) or (None, None) if missing."""
    token = None
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "TELEGRAM_BOT_TOKEN" and v:
                        token = v
                        break
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None, None
    if not os.path.isfile(CHAT_ID_FILE):
        return token, None
    try:
        with open(CHAT_ID_FILE) as f:
            chat_id = int(f.read().strip())
    except (ValueError, OSError):
        return token, None
    return token, chat_id


def load_reminders():
    if not os.path.isfile(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE) as f:
            data = json.load(f)
        return data.get("reminders", data) if isinstance(data, dict) else data
    except (json.JSONDecodeError, OSError):
        return []


def save_reminders(reminders):
    with open(REMINDERS_FILE, "w") as f:
        json.dump({"reminders": reminders}, f, indent=2)


def send_message(token, chat_id, text):
    url = f"{BASE}{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def get_agent_timeout():
    """Agent subprocess timeout in seconds. Config or env CURSOR_AGENT_TIMEOUT, else default."""
    timeout = None
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "CURSOR_AGENT_TIMEOUT" and v:
                        try:
                            timeout = int(v)
                        except ValueError:
                            pass
                        break
    if timeout is None:
        try:
            timeout = int(os.environ.get("CURSOR_AGENT_TIMEOUT", str(DEFAULT_AGENT_TIMEOUT)))
        except ValueError:
            timeout = DEFAULT_AGENT_TIMEOUT
    return timeout if timeout > 0 else 0  # 0 = unlimited


REMINDER_INSTRUCTION = (
    " [Your reply will be sent to the user on Telegram. "
    "Do not run any script or command that sends a Telegram message yourself—just output the message content in your reply.]"
)


def run_agent_prompt(prompt):
    """Run Cursor agent with the given prompt (no session). Return response text or error string."""
    if not (prompt or "").strip():
        return "(empty prompt)"
    # So the agent doesn't also send a message (e.g. via send_btc_gbp.py), causing duplicate delivery
    full_prompt = (prompt.strip() + REMINDER_INSTRUCTION).strip()
    cmd = [
        "cursor", "agent", "--print", "--trust", "--force",
        "--workspace", REPO_ROOT,
        "--model", "Auto",
        "--output-format", "json",
    ]
    cmd.append(full_prompt)
    timeout_sec = get_agent_timeout()
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_sec or None,  # 0 = unlimited
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        response_text = None
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "result" in obj and isinstance(obj["result"], str):
                response_text = obj["result"].strip()
                break
            if response_text is None:
                for key in ("text", "content", "response", "message", "output"):
                    if key in obj and isinstance(obj[key], str):
                        response_text = obj[key]
                        break
        if response_text is None and out:
            try:
                obj = json.loads(out)
                response_text = obj.get("result") or obj.get("text") or obj.get("content") or out
                if isinstance(response_text, dict):
                    response_text = response_text.get("content", str(response_text))
            except json.JSONDecodeError:
                response_text = out
        if not response_text and result.returncode != 0:
            response_text = err or "Agent exited with code %s" % result.returncode
        return response_text or "(no output)"
    except subprocess.TimeoutExpired:
        return "Agent timed out after %d seconds." % timeout_sec
    except Exception as e:
        return "Error running agent: %s" % e


def main():
    token, chat_id = load_config()
    if not token:
        print("run_reminders: no token", file=sys.stderr)
        sys.exit(0)
    if chat_id is None:
        print("run_reminders: no chat_id (message the bot once)", file=sys.stderr)
        sys.exit(0)
    now = datetime.now()
    reminders = load_reminders()
    due = []
    remaining = []
    for r in reminders:
        if not isinstance(r, dict):
            remaining.append(r)
            continue
        at_str = r.get("at")
        if not at_str:
            remaining.append(r)
            continue
        try:
            at = datetime.fromisoformat(at_str.replace("Z", "+00:00"))
            if at.tzinfo:
                at = at.astimezone().replace(tzinfo=None)  # to local naive for comparison with now
        except (ValueError, TypeError):
            remaining.append(r)
            continue
        if at <= now:
            due.append(r)
        else:
            remaining.append(r)
    # Remove due reminders from file immediately so the next timer run won't process them again
    # (prompt-based reminders can take minutes; we don't want two agent runs for the same reminder)
    if due:
        save_reminders(remaining)
    for r in due:
        try:
            if r.get("prompt"):
                body = run_agent_prompt(r["prompt"])
                send_message(token, chat_id, "⏰ " + body)
                print("Sent prompt reminder (%d chars)" % len(body), file=sys.stderr)
            else:
                text = r.get("text") or "(reminder)"
                send_message(token, chat_id, "⏰ " + text)
                print("Sent text reminder: %s" % text[:50], file=sys.stderr)
        except Exception as e:
            print("Failed to send reminder: %s" % e, file=sys.stderr)


if __name__ == "__main__":
    main()
