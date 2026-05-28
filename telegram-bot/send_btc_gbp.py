#!/usr/bin/env python3
"""Fetch current Bitcoin price in GBP and send a short message to the user on Telegram."""

import os
import sys
import json
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config")
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")
BASE = "https://api.telegram.org/bot"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=gbp"


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


def fetch_btc_gbp():
    with urllib.request.urlopen(COINGECKO_URL, timeout=10) as r:
        data = json.loads(r.read().decode())
    return data.get("bitcoin", {}).get("gbp")


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
        print("send_btc_gbp: no TELEGRAM_BOT_TOKEN in config or env", file=sys.stderr)
        sys.exit(1)
    if chat_id is None:
        print("send_btc_gbp: no chat_id (message the bot once first)", file=sys.stderr)
        sys.exit(1)
    try:
        price = fetch_btc_gbp()
    except Exception as e:
        print("send_btc_gbp: failed to fetch BTC price:", e, file=sys.stderr)
        sys.exit(1)
    if price is None:
        print("send_btc_gbp: no GBP price in API response", file=sys.stderr)
        sys.exit(1)
    message = "BTC: £{:,.0f}".format(price)
    try:
        send_message(token, chat_id, message)
    except Exception as e:
        print("send_btc_gbp: failed to send Telegram message:", e, file=sys.stderr)
        sys.exit(1)
    print("Sent:", message, file=sys.stderr)


if __name__ == "__main__":
    main()
