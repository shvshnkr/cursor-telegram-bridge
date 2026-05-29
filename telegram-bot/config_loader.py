"""Load telegram-bot/config and env overrides."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config")

DEFAULTS: Dict[str, str] = {
    "CURSOR_AGENT_TIMEOUT": "0",
    "CURSOR_AGENT_MODE": "agent",
    "CURSOR_AGENT_MODEL": "Auto",
    "CURSOR_AGENT_LANGUAGE": "ru",
    "CURSOR_WORKSPACE": "",
    "CURSOR_CLI": "",
    "PROXY_SOCKS5_URLS": "",
}


def _parse_config_file() -> Dict[str, str]:
    values = dict(DEFAULTS)
    if not os.path.isfile(CONFIG_FILE):
        return values
    with open(CONFIG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k:
                values[k] = v
    return values


def _env_override(key: str, current: str) -> str:
    env_val = os.environ.get(key)
    if env_val is not None and env_val.strip() != "":
        return env_val.strip()
    return current


def load_config() -> Dict[str, str]:
    cfg = _parse_config_file()
    for key in list(cfg.keys()) + [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USER_ID",
    ]:
        cfg[key] = _env_override(key, cfg.get(key, ""))
    if not cfg.get("CURSOR_WORKSPACE"):
        cfg["CURSOR_WORKSPACE"] = REPO_ROOT
    return cfg


def require_telegram(cfg: Dict[str, str]) -> Tuple[str, int]:
    token = cfg.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in %s or env." % CONFIG_FILE)
    uid_raw = cfg.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    try:
        user_id = int(uid_raw)
    except (TypeError, ValueError):
        raise SystemExit("Set TELEGRAM_ALLOWED_USER_ID in %s or env." % CONFIG_FILE)
    return token, user_id


def get_agent_timeout(cfg: Dict[str, str]) -> int:
    raw = cfg.get("CURSOR_AGENT_TIMEOUT", "0").strip() or "0"
    try:
        timeout = int(raw)
    except ValueError:
        timeout = 0
    return timeout if timeout > 0 else 0


def get_workspace(cfg: Dict[str, str]) -> str:
    path = os.path.expanduser(cfg.get("CURSOR_WORKSPACE", REPO_ROOT).strip() or REPO_ROOT)
    return os.path.abspath(path)


def get_proxy_urls(cfg: Dict[str, str]) -> List[str]:
    raw = cfg.get("PROXY_SOCKS5_URLS", "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def get_default_mode(cfg: Dict[str, str]) -> str:
    mode = (cfg.get("CURSOR_AGENT_MODE") or "agent").strip().lower()
    if mode not in ("ask", "plan", "agent"):
        return "agent"
    return mode


def get_agent_language(cfg: Dict[str, str]) -> str:
    return (cfg.get("CURSOR_AGENT_LANGUAGE") or "ru").strip().lower() or "ru"


def session_file_for_mode(mode: str) -> str:
    safe = mode if mode in ("ask", "plan", "agent") else "agent"
    return os.path.join(SCRIPT_DIR, ".cursor_agent_session.%s" % safe)


def resolve_cli_argv(argv: List[str]) -> List[str]:
    """
    Resolve CLI executable to a path subprocess can spawn on Windows.
    .cmd/.bat wrappers (Cursor agent installer) need cmd.exe /c.
    """
    if not argv:
        return argv
    exe = argv[0]
    if os.path.isabs(exe) and os.path.isfile(exe):
        resolved = exe
    else:
        resolved = (
            shutil.which(exe)
            or shutil.which(exe + ".cmd")
            or shutil.which(exe + ".exe")
            or exe
        )
    if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", resolved] + argv[1:]
    if resolved != exe:
        return [resolved] + argv[1:]
    return argv


def detect_cursor_cli(preferred: str = "") -> List[str]:
    """Return argv prefix for Cursor CLI, e.g. cmd.exe /c agent.cmd or ['cursor', 'agent']."""
    pref = (preferred or "").strip()
    if pref:
        return resolve_cli_argv(pref.split())
    agent_path = shutil.which("agent") or shutil.which("agent.cmd")
    if agent_path:
        argv = resolve_cli_argv(["agent"])
        try:
            subprocess.run(
                argv + ["--version"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            return argv
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("cursor"):
        return ["cursor", "agent"]
    return resolve_cli_argv(["agent"])


def get_cursor_cli(cfg: Dict[str, str]) -> List[str]:
    return detect_cursor_cli(cfg.get("CURSOR_CLI", ""))
