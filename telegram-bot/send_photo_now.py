#!/usr/bin/env python3
"""Send a local image to Telegram immediately (Bot API sendPhoto)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config")
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")
BASE = "https://api.telegram.org/bot"


def load_token_and_chat():
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
    chat_id = None
    if os.path.isfile(CHAT_ID_FILE):
        try:
            with open(CHAT_ID_FILE) as f:
                chat_id = int(f.read().strip())
        except (ValueError, OSError):
            pass
    return token, chat_id


def send_photo(token: str, chat_id: int, photo_path: str, caption: str | None = None) -> None:
    if not os.path.isfile(photo_path):
        raise FileNotFoundError(photo_path)
    url = "%s%s/sendPhoto" % (BASE, token)
    with open(photo_path, "rb") as f:
        photo_data = f.read()
    boundary = "----FormBoundary" + os.urandom(16).hex()
    parts = [
        (
            '--%s\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n%d\r\n'
            % (boundary, chat_id)
        ).encode(),
        (
            '--%s\r\nContent-Disposition: form-data; name="photo"; filename="chart.png"\r\n'
            "Content-Type: image/png\r\n\r\n" % boundary
        ).encode(),
        photo_data,
    ]
    if caption:
        parts.append(
            (
                '\r\n--%s\r\nContent-Disposition: form-data; name="caption"\r\n\r\n%s\r\n'
                % (boundary, caption[:1024])
            ).encode()
        )
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read().decode())
    if not out.get("ok"):
        raise RuntimeError("Telegram API: %s" % out)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: send_photo_now.py <image.png> [caption]", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    caption = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
    token, chat_id = load_token_and_chat()
    if not token:
        print("send_photo_now: missing TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(1)
    if chat_id is None:
        print("send_photo_now: missing chat_id (message the bot once)", file=sys.stderr)
        sys.exit(1)
    send_photo(token, chat_id, path, caption)
    print("Sent", path)


if __name__ == "__main__":
    main()
