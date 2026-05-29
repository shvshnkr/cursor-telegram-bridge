#!/usr/bin/env python3
"""
Send file(s) to the Telegram user via cursor-telegram-bridge.

Default: queue for the next bot message chunk (use while agent is running).
--now: send immediately (needs chat_id from a prior bot message).
"""

from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import dialog_log  # noqa: E402
import outbound  # noqa: E402
from config_loader import (  # noqa: E402
    get_dialog_log_dir,
    get_dialog_log_enabled,
    get_proxy_urls,
    load_config,
    require_telegram,
)
import proxy  # noqa: E402


def _load_chat_id() -> int:
    if os.path.isfile(CHAT_ID_FILE):
        try:
            with open(CHAT_ID_FILE, encoding="utf-8") as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    raise SystemExit("attach_file: no chat_id — message the bot once from Telegram")


def _ensure_pysocks() -> None:
    try:
        import socks  # noqa: F401
    except ImportError:
        raise SystemExit(
            "attach_file --now needs PySocks in this Python.\n"
            "  Install: \"%s\" -m pip install PySocks\n"
            "  Or use queue mode (no --now) — files go with the next bot reply.\n"
            "  Bot venv: %s"
            % (sys.executable, os.path.join(os.path.dirname(SCRIPT_DIR), ".venv", "Scripts", "python.exe"))
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send file(s) to Telegram user")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Send immediately instead of queuing with the next reply",
    )
    parser.add_argument("files", nargs="+", help="Path(s) to local file(s)")
    args = parser.parse_args()

    cfg = load_config()
    dialog_log.configure(get_dialog_log_enabled(cfg), get_dialog_log_dir(cfg))

    if args.now:
        _ensure_pysocks()
        token, _ = require_telegram(cfg)
        proxy.configure(get_proxy_urls(cfg))
        chat_id = _load_chat_id()
        for src in args.files:
            path = os.path.abspath(src)
            try:
                outbound.send_immediate(proxy.open_url, token, chat_id, path)
                print("Sent:", path)
                dialog_log.log_attach(chat_id, [os.path.basename(path)], source="attach--now", error=None)
            except ImportError as e:
                dialog_log.log_attach(chat_id, [os.path.basename(path)], source="attach--now", error=str(e))
                print("attach_file:", e, file=sys.stderr)
                _ensure_pysocks()
            except (OSError, ValueError, RuntimeError) as e:
                dialog_log.log_attach(chat_id, [os.path.basename(path)], source="attach--now", error=str(e))
                print("attach_file:", e, file=sys.stderr)
                sys.exit(1)
        return

    for src in args.files:
        path = os.path.abspath(src)
        try:
            dest = outbound.queue_file(path)
            print("Queued:", dest)
            dialog_log.log_attach(None, [os.path.basename(path)], source="attach-queue")
        except (OSError, ValueError) as e:
            dialog_log.log_attach(None, [os.path.basename(path)], source="attach-queue", error=str(e))
            print("attach_file:", e, file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
