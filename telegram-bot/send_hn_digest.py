#!/usr/bin/env python3
"""Send a short HN digest to the user on Telegram. Uses same config and chat_id as agent_bot."""

import os
import sys
import json
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config")
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")
BASE = "https://api.telegram.org/bot"


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


def send_message(token, chat_id, text):
    url = f"{BASE}{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    token, chat_id = load_config()
    if not token:
        print("send_hn_digest: no TELEGRAM_BOT_TOKEN in config or env", file=sys.stderr)
        sys.exit(1)
    if chat_id is None:
        print("send_hn_digest: no chat_id (message the bot once first)", file=sys.stderr)
        sys.exit(1)
    # Message is passed as single argument (multiline ok) or we could build default
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.argv[1]
    else:
        text = (
            "HN picks for you:\n\n"
            "• AI uBlock Blacklist – blocklist for AI-generated/spam sites\n"
            "https://github.com/alvi-se/ai-ublock-blacklist\n\n"
            "• Andrej Karpathy on “Claws” – where AI is going\n"
            "https://simonwillison.net/2026/Feb/21/claws/\n\n"
            "• OpenScan – open-source 3D scan gallery (making/scanning)\n"
            "https://openscan.eu/pages/scan-gallery\n\n"
            "• Every AI assistant company is now an ad company\n"
            "https://juno-labs.com/blogs/every-company-building-your-ai-assistant-is-an-ad-company\n\n"
            "• I verified my LinkedIn identity – what they get\n"
            "https://thelocalstack.eu/posts/linkedin-identity-verification-privacy/"
        )
    try:
        send_message(token, chat_id, text)
    except Exception as e:
        print("send_hn_digest: failed to send Telegram message:", e, file=sys.stderr)
        sys.exit(1)
    print("Sent HN digest to Telegram.", file=sys.stderr)


if __name__ == "__main__":
    main()
