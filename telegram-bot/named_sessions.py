"""Named Cursor agent sessions (agent create-chat + --resume)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from config_loader import get_cursor_cli, get_workspace

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_FILE = os.path.join(SCRIPT_DIR, "named_sessions.json")
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

_STATE: Dict[str, Any] = {"active": None, "sessions": {}}
_CURSOR_CLI = ["cursor", "agent"]
_WORKSPACE = SCRIPT_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def configure(cursor_cli: list, workspace: str) -> None:
    global _CURSOR_CLI, _WORKSPACE
    _CURSOR_CLI = cursor_cli
    _WORKSPACE = workspace


def _agent_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def load() -> None:
    global _STATE
    if not os.path.isfile(SESSIONS_FILE):
        _STATE = {"active": None, "sessions": {}}
        return
    try:
        with open(SESSIONS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("invalid root")
        sessions = data.get("sessions")
        if not isinstance(sessions, dict):
            sessions = {}
        active = data.get("active")
        if active is not None and not isinstance(active, str):
            active = None
        _STATE = {"active": active, "sessions": sessions}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print("Could not load named_sessions.json: %s" % e, file=sys.stderr)
        _STATE = {"active": None, "sessions": {}}


def save() -> None:
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_STATE, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print("Could not save named_sessions.json: %s" % e, file=sys.stderr)


def normalize_name(name: str) -> str:
    n = (name or "").strip()
    if not _NAME_RE.match(n):
        raise ValueError(
            "Имя сессии: 1–32 символа, буквы/цифры/`-`/`_`, с буквы или цифры."
        )
    return n


def get_active_name() -> Optional[str]:
    return _STATE.get("active")


def get_active_session_id() -> Optional[str]:
    name = get_active_name()
    if not name:
        return None
    entry = _STATE.get("sessions", {}).get(name)
    if not isinstance(entry, dict):
        return None
    sid = (entry.get("id") or "").strip()
    return sid or None


def list_sessions_text() -> str:
    active = get_active_name()
    sessions = _STATE.get("sessions") or {}
    if not sessions:
        return (
            "Именованных сессий нет.\n"
            "Создать: `/new bugfix` или `/session new triage`"
        )
    lines = ["*Именованные сессии* (активная отмечена `→`):"]
    for name in sorted(sessions.keys()):
        entry = sessions[name]
        sid = (entry.get("id") or "")[:8]
        last = entry.get("last_used") or entry.get("created") or "?"
        mark = " →" if name == active else ""
        lines.append("- `%s`%s id=%s… last=%s" % (name, mark, sid, last))
    lines.append(
        "\nКоманды: `/use имя`, `/new имя`, `/drop имя`, `/drop all`, "
        "`/reset` (сброс mode-сессий и active)"
    )
    return "\n".join(lines)


def session_help_text() -> str:
    return (
        "*Именованные сессии* (`agent create-chat` + `--resume`):\n"
        "- `/new <имя>` — новая сессия, сделать активной\n"
        "- `/use <имя>` — переключиться\n"
        "- `/sessions` — список\n"
        "- `/drop <имя>` — удалить\n"
        "- `/drop all` — удалить все именованные\n"
        "- `/reset` — сброс ask/plan/agent + снять active\n"
        "- `/reset ask|plan|agent` — сброс одного mode\n"
        "\nБез active — как раньше: отдельный контекст на `/ask`, `/plan`, `/agent`."
    )


def run_create_chat() -> str:
    cmd = list(_CURSOR_CLI) + ["create-chat"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=_WORKSPACE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_agent_env(),
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("create-chat: %s" % e) from e
    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    for line in combined.splitlines():
        candidate = line.strip()
        if _UUID_RE.match(candidate):
            return candidate
    raise RuntimeError(
        "create-chat не вернул id (exit %s): %s"
        % (proc.returncode, combined[:300])
    )


def create_named(name: str) -> Tuple[str, str]:
    name = normalize_name(name)
    sessions = _STATE.setdefault("sessions", {})
    if name in sessions:
        raise ValueError("Сессия `%s` уже есть. `/drop %s` или `/use %s`." % (name, name, name))
    sid = run_create_chat()
    stamp = _now_iso()
    sessions[name] = {"id": sid, "created": stamp, "last_used": stamp}
    _STATE["active"] = name
    save()
    return name, sid


def use_named(name: str) -> str:
    name = normalize_name(name)
    sessions = _STATE.get("sessions") or {}
    if name not in sessions:
        raise ValueError("Нет сессии `%s`. Создай: `/new %s`" % (name, name))
    _STATE["active"] = name
    sessions[name]["last_used"] = _now_iso()
    save()
    return sessions[name]["id"]


def drop_named(name: str) -> None:
    name = normalize_name(name)
    sessions = _STATE.get("sessions") or {}
    if name not in sessions:
        raise ValueError("Нет сессии `%s`." % name)
    del sessions[name]
    if _STATE.get("active") == name:
        _STATE["active"] = None
    save()


def drop_all_named() -> int:
    count = len(_STATE.get("sessions") or {})
    _STATE["sessions"] = {}
    _STATE["active"] = None
    save()
    return count


def clear_active() -> None:
    _STATE["active"] = None
    save()


def update_active_session_id(session_id: Optional[str]) -> None:
    name = get_active_name()
    if not name or not session_id:
        return
    sessions = _STATE.get("sessions") or {}
    if name not in sessions:
        return
    sessions[name]["id"] = session_id
    sessions[name]["last_used"] = _now_iso()
    save()


def handle_command(text: str) -> Tuple[bool, Optional[str]]:
    """
    Parse session control commands.
    Returns (handled, reply_text). reply_text None if not handled.
    """
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return False, None
    parts = raw.split()
    cmd = parts[0].lower()
    rest = parts[1:]

    if cmd in ("/sessions", "/session") and (not rest or rest[0].lower() in ("list", "ls")):
        return True, list_sessions_text()

    if cmd == "/session" and rest and rest[0].lower() == "new" and len(rest) >= 2:
        try:
            name, sid = create_named(rest[1])
            return True, "Сессия `%s` создана.\nactive=yes\nid=%s" % (name, sid)
        except (ValueError, RuntimeError) as e:
            return True, str(e)

    if cmd == "/session" and rest and rest[0].lower() == "use" and len(rest) >= 2:
        try:
            sid = use_named(rest[1])
            return True, "Активна `%s`\nid=%s" % (normalize_name(rest[1]), sid)
        except ValueError as e:
            return True, str(e)

    if cmd == "/session" and rest and rest[0].lower() in ("drop", "delete") and len(rest) >= 2:
        if rest[1].lower() == "all":
            n = drop_all_named()
            return True, "Удалено именованных сессий: %d." % n
        try:
            drop_named(rest[1])
            return True, "Сессия `%s` удалена." % normalize_name(rest[1])
        except ValueError as e:
            return True, str(e)

    if cmd == "/session" and (not rest or rest[0].lower() in ("help", "?")):
        return True, session_help_text()

    if cmd == "/new" and len(rest) >= 1:
        try:
            name, sid = create_named(rest[0])
            return True, "Сессия `%s` создана.\nactive=yes\nid=%s" % (name, sid)
        except (ValueError, RuntimeError) as e:
            return True, str(e)

    if cmd == "/use" and len(rest) >= 1:
        try:
            sid = use_named(rest[0])
            return True, "Активна `%s`\nid=%s" % (normalize_name(rest[0]), sid)
        except ValueError as e:
            return True, str(e)

    if cmd in ("/drop", "/delete") and len(rest) >= 1:
        if rest[0].lower() == "all":
            n = drop_all_named()
            return True, "Удалено именованных сессий: %d." % n
        try:
            drop_named(rest[0])
            return True, "Сессия `%s` удалена." % normalize_name(rest[0])
        except ValueError as e:
            return True, str(e)

    return False, None
