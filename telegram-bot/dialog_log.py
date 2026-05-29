"""Optional Telegram dialog log for local debugging (off by default)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCK = threading.Lock()
_ENABLED = False
_JSONL_PATH: Optional[str] = None
_TXT_PATH: Optional[str] = None
_MAX_TEXT = 8000


def configure(enabled: bool, log_dir: Optional[str] = None) -> None:
    global _ENABLED, _JSONL_PATH, _TXT_PATH
    _ENABLED = bool(enabled)
    if not _ENABLED:
        _JSONL_PATH = None
        _TXT_PATH = None
        return
    base = log_dir or os.path.join(SCRIPT_DIR, "logs")
    os.makedirs(base, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    _JSONL_PATH = os.path.join(base, "dialog-%s.jsonl" % day)
    _TXT_PATH = os.path.join(base, "dialog-latest.txt")
    try:
        with open(_TXT_PATH, "w", encoding="utf-8") as f:
            f.write("=== dialog session %s ===\n" % datetime.now().isoformat(timespec="seconds"))
    except OSError:
        pass


def is_enabled() -> bool:
    return _ENABLED


def jsonl_path() -> Optional[str]:
    return _JSONL_PATH


def txt_path() -> Optional[str]:
    return _TXT_PATH


def _truncate(text: str, limit: int = _MAX_TEXT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def log_event(kind: str, chat_id: Optional[int] = None, **fields: Any) -> None:
    if not _ENABLED or not _JSONL_PATH:
        return
    entry: Dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
    }
    if chat_id is not None:
        entry["chat_id"] = chat_id
    for key, value in fields.items():
        if isinstance(value, str):
            entry[key] = _truncate(value)
        else:
            entry[key] = value
    line = json.dumps(entry, ensure_ascii=False)
    txt_line = _format_txt_line(entry)
    with _LOCK:
        try:
            with open(_JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if _TXT_PATH:
                with open(_TXT_PATH, "a", encoding="utf-8") as f:
                    f.write(txt_line + "\n")
        except OSError as e:
            print("dialog_log write failed: %s" % e, file=__import__("sys").stderr)


def _format_txt_line(entry: Dict[str, Any]) -> str:
    ts = entry.get("ts", "")
    kind = entry.get("kind", "?")
    chat = entry.get("chat_id")
    prefix = "[%s] [%s]" % (ts, kind)
    if chat is not None:
        prefix += " chat=%s" % chat
    parts = [prefix]
    for key in (
        "text",
        "prompt",
        "mode",
        "active",
        "files",
        "error",
        "ok",
        "detail",
        "command",
    ):
        if key in entry and entry[key] not in (None, ""):
            val = entry[key]
            if isinstance(val, list):
                val = ", ".join(str(x) for x in val)
            parts.append("%s=%s" % (key, val))
    return " ".join(parts)


def log_user(chat_id: int, text: str, **extra: Any) -> None:
    log_event("user_in", chat_id, text=text, **extra)


def log_bot(chat_id: int, text: str, ok: bool = True, **extra: Any) -> None:
    log_event("bot_out", chat_id, text=text, ok=ok, **extra)


def log_agent_start(chat_id: int, mode: str, prompt: str, resume: Optional[str], active: Optional[str]) -> None:
    log_event(
        "agent_start",
        chat_id,
        mode=mode,
        active=active or "-",
        resume=resume or "-",
        prompt=prompt,
    )


def log_agent_chunk(chat_id: int, text: str) -> None:
    log_event("agent_chunk", chat_id, text=text)


def log_attach(chat_id: Optional[int], files: list, source: str = "queue", error: Optional[str] = None) -> None:
    fields: Dict[str, Any] = {"files": files, "source": source}
    if error:
        fields["error"] = error
        fields["ok"] = False
    else:
        fields["ok"] = True
    log_event("attach", chat_id, **fields)


def log_system(message: str, **extra: Any) -> None:
    log_event("system", detail=message, **extra)
