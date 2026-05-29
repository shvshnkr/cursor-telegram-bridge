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
    "CURSOR_AGENT_IDLE_TIMEOUT": "1200",
    "CURSOR_AGENT_MODE": "agent",
    "CURSOR_AGENT_MODEL": "Auto",
    "CURSOR_AGENT_LANGUAGE": "ru",
    "CURSOR_WORKSPACE": "",
    "CURSOR_CLI": "",
    "PROXY_SOCKS5_URLS": "",
    "TELEGRAM_DIALOG_LOG": "0",
    "TELEGRAM_DIALOG_LOG_DIR": "",
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


def _parse_timeout_seconds(cfg: Dict[str, str], key: str, default: str = "0") -> int:
    raw = (cfg.get(key) or default).strip() or default
    try:
        timeout = int(raw)
    except ValueError:
        timeout = 0
    return timeout if timeout > 0 else 0


def get_agent_timeout(cfg: Dict[str, str]) -> int:
    """Wall-clock limit for one agent subprocess; 0 = unlimited."""
    return _parse_timeout_seconds(cfg, "CURSOR_AGENT_TIMEOUT", "0")


def get_agent_idle_timeout(cfg: Dict[str, str]) -> int:
    """
    Stop agent if no stdout from CLI for this many seconds (thinking/stream-json counts).
    0 = disabled. Default 1200 — long log runs can take many minutes if CLI keeps streaming.
    """
    return _parse_timeout_seconds(cfg, "CURSOR_AGENT_IDLE_TIMEOUT", "1200")


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


def get_dialog_log_enabled(cfg: Dict[str, str]) -> bool:
    raw = (cfg.get("TELEGRAM_DIALOG_LOG") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_dialog_log_dir(cfg: Dict[str, str]) -> str:
    custom = (cfg.get("TELEGRAM_DIALOG_LOG_DIR") or "").strip()
    if custom:
        return os.path.abspath(os.path.expanduser(custom))
    return os.path.join(SCRIPT_DIR, "logs")


def session_file_for_mode(mode: str) -> str:
    safe = mode if mode in ("ask", "plan", "agent") else "agent"
    return os.path.join(SCRIPT_DIR, ".cursor_agent_session.%s" % safe)


def _cursor_agent_cmd_candidates() -> List[str]:
    """Well-known install locations when agent is not on PATH (common for background tasks)."""
    out: List[str] = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        out.append(os.path.join(local, "cursor-agent", "agent.cmd"))
    roaming = os.environ.get("APPDATA", "")
    if roaming:
        out.append(os.path.join(roaming, "cursor-agent", "agent.cmd"))
    home = os.path.expanduser("~")
    if home:
        out.append(os.path.join(home, ".cursor", "bin", "agent.cmd"))
    return out


def _windows_system32(exe_name: str) -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", exe_name)


def _resolve_cursor_agent_ps1(cmd_path: str) -> Optional[str]:
    """cursor-agent installs agent.cmd next to cursor-agent.ps1 — prefer direct PS1 launch."""
    if not cmd_path.lower().endswith((".cmd", ".bat")):
        return None
    script_dir = os.path.dirname(os.path.abspath(cmd_path))
    ps1 = os.path.join(script_dir, "cursor-agent.ps1")
    return ps1 if os.path.isfile(ps1) else None


def resolve_cli_argv(argv: List[str]) -> List[str]:
    """
    Resolve CLI executable to a path subprocess can spawn on Windows.
    Background tasks often lack PATH — use full paths to cmd/powershell, or PS1 directly.
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
    rest = argv[1:]
    if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
        ps1 = _resolve_cursor_agent_ps1(resolved)
        if ps1:
            pwsh = _windows_system32(
                os.path.join("WindowsPowerShell", "v1.0", "powershell.exe")
            )
            if os.path.isfile(pwsh):
                return [
                    pwsh,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    ps1,
                ] + rest
        cmd_exe = _windows_system32("cmd.exe")
        if os.path.isfile(cmd_exe):
            return [cmd_exe, "/c", os.path.abspath(resolved)] + rest
        return ["cmd.exe", "/c", resolved] + rest
    if resolved != exe and os.path.isfile(resolved):
        return [resolved] + rest
    return argv


def _probe_cli_argv(argv: List[str]) -> bool:
    try:
        subprocess.run(
            argv + ["--version"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_cursor_cli(preferred: str = "") -> List[str]:
    """Return argv prefix for Cursor CLI, e.g. cmd.exe /c agent.cmd or ['cursor', 'agent']."""
    pref = (preferred or "").strip()
    # Bare "agent" in config should not skip full-path discovery (background tasks often lack PATH).
    if pref.lower() in ("agent", "agent.cmd", "cursor agent"):
        pref = ""
    if pref:
        argv = resolve_cli_argv(pref.split())
        if _probe_cli_argv(argv):
            return argv
        # Config path invalid — fall back to discovery below.

    for candidate in _cursor_agent_cmd_candidates():
        if os.path.isfile(candidate):
            argv = resolve_cli_argv([candidate])
            if _probe_cli_argv(argv):
                return argv

    agent_path = shutil.which("agent") or shutil.which("agent.cmd")
    if agent_path:
        argv = resolve_cli_argv(["agent"])
        if _probe_cli_argv(argv):
            return argv

    if shutil.which("cursor"):
        argv = ["cursor", "agent"]
        if _probe_cli_argv(argv):
            return argv

    for candidate in _cursor_agent_cmd_candidates():
        if os.path.isfile(candidate):
            return resolve_cli_argv([candidate])
    return resolve_cli_argv(["agent"])


def get_cursor_cli(cfg: Dict[str, str]) -> List[str]:
    return detect_cursor_cli(cfg.get("CURSOR_CLI", ""))
