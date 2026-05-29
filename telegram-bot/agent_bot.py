#!/usr/bin/env python3
"""
Telegram bot: forwards messages from the allowed user to Cursor CLI agent.
Fork of jes/cursor-claw with SOCKS5 failover, ask/plan/agent modes, and
configurable workspace (cursor-telegram-bridge).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config_loader import (
    REPO_ROOT,
    get_agent_language,
    get_agent_timeout,
    get_cursor_cli,
    get_default_mode,
    get_proxy_urls,
    get_workspace,
    load_config,
    require_telegram,
    session_file_for_mode,
)
import proxy
import named_sessions

TYPING_INTERVAL = 4
BASE = "https://api.telegram.org/bot"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAT_ID_FILE = os.path.join(SCRIPT_DIR, "chat_id")
OFFSET_FILE = os.path.join(SCRIPT_DIR, ".telegram_offset")
RECEIVED_IMAGES_DIR = os.path.join(SCRIPT_DIR, "received_images")
RECEIVED_DOCUMENTS_DIR = os.path.join(SCRIPT_DIR, "received_documents")
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
PENDING_IMAGES_DIR = os.path.join(SCRIPT_DIR, "pending_images")
PENDING_ATTACHMENTS_DIR = os.path.join(SCRIPT_DIR, "pending_attachments")
LOG_TRIAGE_PROMPT = os.path.join(SCRIPT_DIR, "prompts", "log-triage.md")
TELEGRAM_SESSION_PROMPT = os.path.join(SCRIPT_DIR, "prompts", "telegram-session.md")
HUSI_LOG_GLOB = "husi_simple_log_*.txt"

_CFG: Dict[str, str] = {}
_TOKEN = ""
_ALLOWED_USER_ID = 0
_WORKSPACE = REPO_ROOT
_CURSOR_CLI: List[str] = ["cursor", "agent"]
_DEFAULT_MODE = "agent"
_MODE_SESSIONS: Dict[str, Optional[str]] = {"ask": None, "plan": None, "agent": None}

_RU_LANG_CODES = frozenset({"ru", "rus", "russian", "рус", "русский"})


def _agent_subprocess_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _wrap_telegram_prompt(prompt: str, resume_session: Optional[str]) -> str:
    """Wrap user prompt without hijacking the task (language rule only as brief suffix on resume)."""
    lang = get_agent_language(_CFG)
    if lang not in _RU_LANG_CODES:
        return prompt

    brief_suffix = "\n\n(Ответь по существу на русском. Не повторяй инструкции — только результат.)"

    if resume_session:
        return prompt + brief_suffix

    header = ""
    if os.path.isfile(TELEGRAM_SESSION_PROMPT):
        with open(TELEGRAM_SESSION_PROMPT, encoding="utf-8") as f:
            header = f.read().format(workspace=_WORKSPACE)
    else:
        header = (
            "Telegram-бот. Workspace: %s. Отвечай на русском по существу. "
            "Не подтверждай инструкции.\n\nЗапрос пользователя:\n"
        ) % _WORKSPACE
    return header + prompt


def _init_runtime() -> None:
    global _CFG, _TOKEN, _ALLOWED_USER_ID, _WORKSPACE, _CURSOR_CLI, _DEFAULT_MODE
    _CFG = load_config()
    _TOKEN, _ALLOWED_USER_ID = require_telegram(_CFG)
    _WORKSPACE = get_workspace(_CFG)
    _CURSOR_CLI = get_cursor_cli(_CFG)
    _DEFAULT_MODE = get_default_mode(_CFG)
    proxy.configure(get_proxy_urls(_CFG))
    named_sessions.configure(_CURSOR_CLI, _WORKSPACE)
    named_sessions.load()
    for mode in ("ask", "plan", "agent"):
        _MODE_SESSIONS[mode] = _load_session(mode)


def api(method, **params):
    url = "%s%s/%s" % (BASE, _TOKEN, method)
    data = json.dumps(params).encode() if params else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    with proxy.open_url(req, timeout=60) as r:
        return json.loads(r.read().decode())


def send_chat_action(chat_id, action="typing"):
    try:
        api("sendChatAction", chat_id=chat_id, action=action)
    except Exception:
        pass


def collapse_blank_lines(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    result = []
    in_blank_run = False
    for line in lines:
        if not line.strip():
            if not in_blank_run:
                result.append("")
                in_blank_run = True
        else:
            result.append(line)
            in_blank_run = False
    return "\n".join(result)


def send_message(chat_id, text, parse_mode="Markdown"):
    chunk = 4096
    for i in range(0, len(text), chunk):
        part = text[i : i + chunk]
        try:
            api("sendMessage", chat_id=chat_id, text=part, parse_mode=parse_mode)
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                api("sendMessage", chat_id=chat_id, text=part)
            else:
                raise


def _multipart_post(url: str, body: bytes, boundary: str, timeout: float = 30):
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    with proxy.open_url(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def send_photo(chat_id, photo_path: str, caption: Optional[str] = None) -> None:
    if not os.path.isfile(photo_path):
        return
    url = "%s%s/sendPhoto" % (BASE, _TOKEN)
    with open(photo_path, "rb") as f:
        photo_data = f.read()
    boundary = "----FormBoundary" + os.urandom(16).hex()
    head = (
        "--%s\r\n"
        'Content-Disposition: form-data; name="chat_id"\r\n\r\n%s\r\n'
        "--%s\r\n"
        'Content-Disposition: form-data; name="photo"; filename="image.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ) % (boundary, chat_id, boundary)
    tail = "\r\n--%s--\r\n" % boundary
    body = head.encode() + photo_data + tail.encode()
    try:
        _multipart_post(url, body, boundary)
    except Exception:
        pass


def send_document(chat_id, file_path: str) -> None:
    if not os.path.isfile(file_path):
        return
    url = "%s%s/sendDocument" % (BASE, _TOKEN)
    with open(file_path, "rb") as f:
        file_data = f.read()
    name = os.path.basename(file_path)
    boundary = "----FormBoundary" + os.urandom(16).hex()
    head = (
        "--%s\r\n"
        'Content-Disposition: form-data; name="chat_id"\r\n\r\n%s\r\n'
        "--%s\r\n"
        'Content-Disposition: form-data; name="document"; filename="%s"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ) % (boundary, chat_id, boundary, name)
    tail = "\r\n--%s--\r\n" % boundary
    body = head.encode() + file_data + tail.encode()
    try:
        _multipart_post(url, body, boundary)
    except Exception:
        pass


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def send_pending_images(chat_id) -> None:
    if not os.path.isdir(PENDING_IMAGES_DIR):
        return
    try:
        for name in sorted(os.listdir(PENDING_IMAGES_DIR)):
            path = os.path.join(PENDING_IMAGES_DIR, name)
            if not os.path.isfile(path):
                continue
            lower = name.lower()
            if not any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS):
                continue
            try:
                send_photo(chat_id, path)
            except Exception:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass
    except OSError:
        pass


def send_pending_attachments(chat_id) -> None:
    if not os.path.isdir(PENDING_ATTACHMENTS_DIR):
        return
    try:
        for name in sorted(os.listdir(PENDING_ATTACHMENTS_DIR)):
            path = os.path.join(PENDING_ATTACHMENTS_DIR, name)
            if not os.path.isfile(path):
                continue
            lower = name.lower()
            try:
                if any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS):
                    send_photo(chat_id, path)
                else:
                    send_document(chat_id, path)
            except Exception:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass
    except OSError:
        pass


def _load_session(mode: str) -> Optional[str]:
    path = session_file_for_mode(mode)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            pass
    return None


def _save_session(mode: str, session_id: Optional[str]) -> None:
    path = session_file_for_mode(mode)
    if session_id:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(session_id)
        except OSError as e:
            print("Could not save session: %s" % e, file=sys.stderr)
    elif os.path.isfile(path):
        try:
            os.unlink(path)
        except OSError:
            pass
    _MODE_SESSIONS[mode] = session_id


def save_chat_id(chat_id: int) -> None:
    try:
        with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(chat_id))
    except OSError as e:
        print("Could not save chat_id: %s" % e, file=sys.stderr)


def _safe_document_filename(name: str) -> str:
    base = os.path.basename((name or "").strip()) or "file"
    if base in (".", ".."):
        base = "file"
    if len(base) > 180:
        root, ext = os.path.splitext(base)
        base = (root[:160] + ext) if ext else root[:180]
    return base


def download_telegram_file(file_id: str, dest_path: str) -> bool:
    try:
        out = api("getFile", file_id=file_id)
        if not out.get("ok"):
            return False
        file_path = (out.get("result") or {}).get("file_path")
        if not file_path:
            return False
        url = "https://api.telegram.org/file/bot%s/%s" % (_TOKEN, file_path)
        req = urllib.request.Request(url)
        with proxy.open_url(req, timeout=120) as r:
            data = r.read()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print("Download file failed: %s" % e, file=sys.stderr)
        return False


def load_offset() -> int:
    if os.path.isfile(OFFSET_FILE):
        try:
            with open(OFFSET_FILE, encoding="utf-8") as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    return 0


def save_offset(offset: int) -> None:
    try:
        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(offset))
    except OSError as e:
        print("Could not save offset: %s" % e, file=sys.stderr)


def _parse_session_and_final_output(full_stdout: str, full_stderr: str, returncode: int):
    session_id = None
    response_text = None
    for line in full_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = obj.get("session_id") or obj.get("sessionId") or obj.get("chatId")
        if sid:
            session_id = str(sid)
        if "result" in obj and isinstance(obj["result"], str):
            response_text = obj["result"].strip()
        elif response_text is None:
            for key in ("text", "content", "response", "message", "output"):
                if key in obj and isinstance(obj[key], str):
                    response_text = obj[key]
                    break
    if response_text is None and full_stdout:
        try:
            obj = json.loads(full_stdout.strip().split("\n")[-1] or "{}")
            session_id = session_id or obj.get("session_id") or obj.get("sessionId")
            response_text = obj.get("result") or obj.get("text") or obj.get("content") or full_stdout
            if isinstance(response_text, dict):
                response_text = response_text.get("content", str(response_text))
        except (json.JSONDecodeError, IndexError):
            response_text = full_stdout
    if returncode != 0 and not response_text:
        response_text = full_stderr or "Agent exited with code %s" % returncode
    return response_text or "(no output)", session_id


_MODE_CMD_RE = re.compile(r"^/(ask|plan|agent|mode|reset|newchat)\b", re.IGNORECASE)


def parse_mode_and_text(text: str) -> Tuple[str, str, bool]:
    """
    Returns (mode, prompt_text, is_control_only).
    Control commands: /mode, /reset, /newchat without trailing prompt.
    """
    stripped = (text or "").strip()
    if not stripped:
        return _DEFAULT_MODE, "", False
    m = _MODE_CMD_RE.match(stripped)
    if not m:
        return _DEFAULT_MODE, stripped, False
    cmd = m.group(1).lower()
    rest = stripped[m.end() :].strip()
    if cmd == "mode":
        return _DEFAULT_MODE, "", True
    if cmd in ("reset", "newchat"):
        return _DEFAULT_MODE, "", cmd == "reset" or cmd == "newchat"
    if rest:
        return cmd, rest, False
    return cmd, "", False


def _is_husi_log(name: str) -> bool:
    return fnmatch.fnmatch((name or "").lower(), HUSI_LOG_GLOB.lower())


def _copy_husi_log_to_workspace(src_path: str, orig_name: str) -> str:
    incoming = os.path.join(_WORKSPACE, "AI", "incoming-logs")
    os.makedirs(incoming, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest_name = "%s_%s" % (stamp, _safe_document_filename(orig_name))
    dest_path = os.path.join(incoming, dest_name)
    shutil.copy2(src_path, dest_path)
    return dest_path


def _load_log_triage_prompt(caption: str, path_in_workspace: str) -> str:
    template = ""
    if os.path.isfile(LOG_TRIAGE_PROMPT):
        with open(LOG_TRIAGE_PROMPT, encoding="utf-8") as f:
            template = f.read()
    else:
        template = "Разбор лога Dahusim. Комментарий: {caption}. Файл: {path_in_workspace}. Код не менять."
    return template.format(
        caption=caption or "не указан",
        path_in_workspace=path_in_workspace,
    )


def run_agent_streaming(
    prompt: str,
    mode: str,
    resume_session: Optional[str],
    chat_id: int,
) -> Optional[str]:
    if not prompt.strip():
        send_message(chat_id, "(no prompt)")
        return resume_session

    cmd = list(_CURSOR_CLI) + [
        "--print",
        "--trust",
        "--force",
        "--workspace",
        _WORKSPACE,
        "--model",
        (_CFG.get("CURSOR_AGENT_MODEL") or "Auto").strip() or "Auto",
        "--output-format",
        "stream-json",
    ]
    if mode == "ask":
        cmd.extend(["--mode", "ask"])
    elif mode == "plan":
        cmd.extend(["--mode", "plan"])
    if resume_session:
        cmd.extend(["--resume", resume_session])
    cmd.append(_wrap_telegram_prompt(prompt, resume_session))

    timeout_sec = get_agent_timeout(_CFG)
    full_stdout_lines: List[str] = []
    full_stderr_lines: List[str] = []
    lock = threading.Lock()
    process_done = threading.Event()
    proc_ref: List[Optional[subprocess.Popen]] = [None]

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_name = datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + ".log"
    log_path = os.path.join(LOGS_DIR, log_name)

    def reader():
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=_WORKSPACE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=_agent_subprocess_env(),
            )
            proc_ref[0] = proc
            try:
                with open(log_path, "w", encoding="utf-8") as logf:
                    for line in iter(proc.stdout.readline, ""):
                        with lock:
                            full_stdout_lines.append(line)
                        logf.write(line)
                        logf.flush()
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        try:
                            obj = json.loads(line_stripped)
                        except json.JSONDecodeError:
                            continue
                        msg_type = (obj.get("role") or obj.get("type") or obj.get("messageType") or "").lower()
                        if msg_type in ("thinking", "result"):
                            continue
                        if msg_type != "assistant":
                            continue
                        text = None
                        msg = obj.get("message")
                        if isinstance(msg, dict):
                            content = msg.get("content")
                            if isinstance(content, list):
                                parts = []
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
                                        parts.append(item["text"])
                                if parts:
                                    text = "".join(parts)
                        if text is None:
                            text = (
                                obj.get("content")
                                or obj.get("text")
                                or obj.get("delta")
                                or obj.get("result")
                                or obj.get("output")
                            )
                        if not isinstance(text, str):
                            continue
                        to_send = text.strip()
                        if to_send:
                            send_pending_attachments(chat_id)
                            send_pending_images(chat_id)
                            send_message(chat_id, collapse_blank_lines(to_send))
            finally:
                proc.wait()
                err = proc.stderr.read() if proc.stderr else ""
                if err:
                    full_stderr_lines.append(err)
        except Exception as e:
            send_message(chat_id, "Error running agent: %s" % e)
        finally:
            process_done.set()

    t = threading.Thread(target=reader, daemon=False)
    t.start()
    last_typing = 0.0
    start_time = time.time()

    while not process_done.is_set():
        time.sleep(1)
        now = time.time()
        if timeout_sec and (now - start_time) >= timeout_sec:
            p = proc_ref[0]
            if p and p.poll() is None:
                p.kill()
            send_message(chat_id, "Agent timed out after %s seconds." % timeout_sec)
            break
        if now - last_typing >= TYPING_INTERVAL:
            send_chat_action(chat_id, "typing")
            last_typing = now

    t.join(timeout=10)
    full_stdout = "".join(full_stdout_lines)
    full_stderr = "".join(full_stderr_lines)
    _, session_id = _parse_session_and_final_output(full_stdout, full_stderr, 0)
    if not session_id:
        session_id = resume_session
    return session_id


def _handle_control(chat_id: int, text: str) -> bool:
    handled, reply = named_sessions.handle_command(text)
    if handled:
        send_message(chat_id, reply or "(ok)")
        return True

    stripped = text.strip()
    lower = stripped.lower()
    parts = stripped.split()

    if lower == "/mode":
        active = named_sessions.get_active_name()
        send_message(
            chat_id,
            "Default mode: `%s`\nActive named: `%s`\n"
            "Mode sessions: ask=%s, plan=%s, agent=%s\n\n"
            "%s"
            % (
                _DEFAULT_MODE,
                active or "(none)",
                "yes" if _MODE_SESSIONS.get("ask") else "no",
                "yes" if _MODE_SESSIONS.get("plan") else "no",
                "yes" if _MODE_SESSIONS.get("agent") else "no",
                named_sessions.session_help_text(),
            ),
        )
        return True

    if lower == "/newchat":
        send_message(
            chat_id,
            "Новый контекст:\n"
            "- `/new bugfix` — именованная сессия (create-chat)\n"
            "- `/reset` — сброс mode + снять active\n"
            "- или новый чат в Cursor Desktop",
        )
        return True

    if parts and parts[0].lower() == "/reset":
        if len(parts) == 1:
            for mode in ("ask", "plan", "agent"):
                _save_session(mode, None)
            named_sessions.clear_active()
            send_message(
                chat_id,
                "Сброшено: ask/plan/agent sessions + active именованная.\n"
                "Именованные записи в `/sessions` сохранены (id остались). "
                "Удалить: `/drop all`.",
            )
            return True
        target = parts[1].lower()
        if target in ("ask", "plan", "agent"):
            _save_session(target, None)
            send_message(chat_id, "Session `%s` cleared." % target)
            return True
        if target == "all":
            for mode in ("ask", "plan", "agent"):
                _save_session(mode, None)
            named_sessions.clear_active()
            send_message(chat_id, "Mode sessions + active cleared.")
            return True
        try:
            named_sessions.drop_named(parts[1])
            send_message(chat_id, "Именованная сессия `%s` удалена." % parts[1])
        except ValueError as e:
            send_message(chat_id, str(e))
        return True

    return False


def main():
    _init_runtime()
    offset = load_offset()
    if offset:
        print("Resuming from update offset %s." % offset, file=sys.stderr)
    print("cursor-telegram-bridge running.", file=sys.stderr)
    print("Workspace: %s" % _WORKSPACE, file=sys.stderr)
    print("CLI: %s" % " ".join(_CURSOR_CLI), file=sys.stderr)
    print("Default mode: %s" % _DEFAULT_MODE, file=sys.stderr)
    print("Only user_id=%s accepted." % _ALLOWED_USER_ID, file=sys.stderr)
    print("Ctrl+C to stop.", file=sys.stderr)

    while True:
        try:
            out = api("getUpdates", offset=offset, timeout=30)
        except urllib.error.URLError as e:
            print("API error: %s" % e, file=sys.stderr)
            time.sleep(5)
            continue
        if not out.get("ok"):
            print("API not ok: %s" % out, file=sys.stderr)
            time.sleep(5)
            continue
        updates = out.get("result", [])
        if not updates:
            continue

        batch_texts: List[str] = []
        batch_image_paths: List[str] = []
        batch_document_paths: List[Tuple[str, str]] = []
        chat_id = None
        force_ask = False
        husi_caption = ""

        for i, upd in enumerate(updates):
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            uid = (msg.get("from") or {}).get("id")
            if uid != _ALLOWED_USER_ID:
                continue
            if chat_id is None:
                chat_id = msg["chat"]["id"]
            text = (msg.get("text") or "").strip()
            if text:
                if _handle_control(chat_id, text):
                    continue
                batch_texts.append(text)

            photos = msg.get("photo") or []
            if photos:
                file_id = photos[-1].get("file_id")
                if file_id:
                    os.makedirs(RECEIVED_IMAGES_DIR, exist_ok=True)
                    local_name = "photo_%s_%s.jpg" % (upd["update_id"], i)
                    dest_path = os.path.join(RECEIVED_IMAGES_DIR, local_name)
                    if download_telegram_file(file_id, dest_path):
                        batch_image_paths.append(dest_path)
                caption = (msg.get("caption") or "").strip()
                if caption:
                    batch_texts.append(caption)

            doc = msg.get("document")
            if isinstance(doc, dict) and doc.get("file_id"):
                os.makedirs(RECEIVED_DOCUMENTS_DIR, exist_ok=True)
                orig_name = doc.get("file_name") or "file"
                safe = _safe_document_filename(orig_name)
                local_name = "doc_%s_%s_%s" % (upd["update_id"], i, safe)
                dest_path = os.path.join(RECEIVED_DOCUMENTS_DIR, local_name)
                if download_telegram_file(doc["file_id"], dest_path):
                    if _is_husi_log(orig_name):
                        ws_path = _copy_husi_log_to_workspace(dest_path, orig_name)
                        batch_document_paths.append((ws_path, orig_name))
                        force_ask = True
                        husi_caption = (msg.get("caption") or "").strip()
                    else:
                        batch_document_paths.append((dest_path, orig_name))
                cap = (msg.get("caption") or "").strip()
                if cap and not _is_husi_log(orig_name):
                    batch_texts.append(cap)

        offset = updates[-1]["update_id"] + 1
        save_offset(offset)

        if not batch_texts and not batch_image_paths and not batch_document_paths:
            continue
        if chat_id is None:
            continue
        save_chat_id(chat_id)

        mode = _DEFAULT_MODE
        prompt_parts: List[str] = []
        for t in batch_texts:
            m, body, _ = parse_mode_and_text(t)
            if body:
                mode = m
                prompt_parts.append(body)
            elif m != _DEFAULT_MODE:
                mode = m

        if force_ask:
            mode = "ask"

        text = "\n\n".join(prompt_parts) if prompt_parts else ""

        if batch_image_paths:
            text += "\n\n[User sent %d image(s) at: %s]" % (
                len(batch_image_paths),
                ", ".join(batch_image_paths),
            )
        if batch_document_paths:
            paths = [p for p, _ in batch_document_paths]
            if force_ask and batch_document_paths:
                ws_path = batch_document_paths[0][0]
                text = _load_log_triage_prompt(husi_caption, ws_path) + "\n\n" + text
            else:
                text += "\n\n[User sent %d file(s) at: %s. Read and respond.]" % (
                    len(paths),
                    ", ".join(paths),
                )

        if not text.strip():
            continue

        print("Running agent mode=%s active=%s prompt: %s..." % (
            mode,
            named_sessions.get_active_name() or "-",
            text[:60],
        ), file=sys.stderr)
        send_chat_action(chat_id, "typing")
        resume = named_sessions.get_active_session_id()
        if not resume:
            resume = _MODE_SESSIONS.get(mode)
        session_id = run_agent_streaming(text, mode, resume, chat_id)
        if named_sessions.get_active_name():
            named_sessions.update_active_session_id(session_id)
        else:
            _save_session(mode, session_id)


if __name__ == "__main__":
    main()
