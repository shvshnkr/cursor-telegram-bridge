#!/usr/bin/env python3
"""Poll Telegram and print user IDs (uses config + SOCKS5 proxy like agent_bot)."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from config_loader import get_proxy_urls, load_config, require_telegram
import proxy

BASE = "https://api.telegram.org/bot"


def api(token, method, **params):
    url = "%s%s/%s" % (BASE, token, method)
    data = json.dumps(params).encode() if params else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    with proxy.open_url(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    cfg = load_config()
    token = cfg.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in telegram-bot/config or env.", file=sys.stderr)
        sys.exit(1)
    proxy.configure(get_proxy_urls(cfg))
    offset = 0
    print("Send a message to your bot; user_id will print here.", file=sys.stderr)
    while True:
        try:
            out = api(token, "getUpdates", offset=offset, timeout=30)
        except urllib.error.URLError as e:
            print("API error: %s" % e, file=sys.stderr)
            time.sleep(5)
            continue
        if not out.get("ok"):
            print("API not ok: %s" % out, file=sys.stderr)
            time.sleep(5)
            continue
        for upd in out.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            user = msg.get("from") or {}
            uid = user.get("id")
            username = user.get("username", "")
            text = (msg.get("text") or "").strip()
            print("user_id=%s username=%r text=%r" % (uid, username, text[:80]))


if __name__ == "__main__":
    main()
