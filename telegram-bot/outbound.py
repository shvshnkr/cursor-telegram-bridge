"""Queue and send files from the agent to Telegram."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime
from typing import Callable, List, Optional, Set

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_IMAGES_DIR = os.path.join(SCRIPT_DIR, "pending_images")
PENDING_ATTACHMENTS_DIR = os.path.join(SCRIPT_DIR, "pending_attachments")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
# Deliverables the bot may auto-attach when the agent only mentions a path in text.
SENDABLE_EXTENSIONS = IMAGE_EXTENSIONS + (
    ".pdf",
    ".md",
    ".html",
    ".htm",
    ".zip",
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".svg",
    ".docx",
    ".xlsx",
    ".pptx",
)
_EXT_GROUP = "|".join(ext.lstrip(".") for ext in SENDABLE_EXTENSIONS)
# Backticks, Windows/UNC paths, or workspace-relative paths ending in a sendable extension.
_PATH_IN_TEXT_RE = re.compile(
    r"(?:`([^`]+\.(?:%s))`)"
    r"|(?:\b([A-Za-z]:[\\/][^\s`<>|\[\]*?]+\.(?:%s))\b)"
    r"|(?:\b([~/][^\s`<>|\[\]*?]+\.(?:%s))\b)"
    r"|(?:\b([\w\-.\\/]+\.(?:%s))\b)"
    % (_EXT_GROUP, _EXT_GROUP, _EXT_GROUP, _EXT_GROUP),
    re.IGNORECASE,
)
# Telegram Bot API document limit
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_AUTO_ATTACH_PER_MESSAGE = 5


def is_image_path(path: str) -> bool:
    return path.lower().endswith(IMAGE_EXTENSIONS)


def _check_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise ValueError(
            "File too large for Telegram (%d bytes, max %d): %s"
            % (size, MAX_FILE_BYTES, path)
        )


def queue_file(src_path: str) -> str:
    """Copy a file into the pending queue; bot sends it with the next reply chunk."""
    src = os.path.abspath(src_path)
    _check_file(src)
    dest_dir = PENDING_IMAGES_DIR if is_image_path(src) else PENDING_ATTACHMENTS_DIR
    os.makedirs(dest_dir, mode=0o700, exist_ok=True)
    base = os.path.basename(src)
    name, ext = os.path.splitext(base)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    dest_name = "%s_%s%s" % (name, stamp, ext)
    dest = os.path.join(dest_dir, dest_name)
    shutil.copy2(src, dest)
    return dest


def flush_pending(
    chat_id: int,
    send_photo: Callable[[int, str], None],
    send_document: Callable[[int, str], None],
) -> int:
    """Send all queued files; return count sent."""
    sent = 0
    for directory, use_photo in (
        (PENDING_IMAGES_DIR, True),
        (PENDING_ATTACHMENTS_DIR, False),
    ):
        if not os.path.isdir(directory):
            continue
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            try:
                if use_photo or is_image_path(path):
                    send_photo(chat_id, path)
                else:
                    send_document(chat_id, path)
                sent += 1
            except Exception as e:
                print("flush_pending send failed %s: %s" % (path, e), file=sys.stderr)
            try:
                os.unlink(path)
            except OSError:
                pass
    return sent


def extract_sendable_paths(text: str, workspace: str) -> List[str]:
    """Find paths in assistant text that point to existing deliverable files."""
    if not text:
        return []
    seen: Set[str] = set()
    found: List[str] = []
    for match in _PATH_IN_TEXT_RE.finditer(text):
        for group in match.groups():
            if not group:
                continue
            raw = group.strip().strip('"').strip("'")
            resolved = resolve_workspace_path(raw, workspace)
            if not resolved or resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
            if len(found) >= MAX_AUTO_ATTACH_PER_MESSAGE:
                return found
    return found


def queue_paths(paths: List[str]) -> List[str]:
    """Queue existing files; return basenames successfully queued."""
    queued: List[str] = []
    for path in paths:
        try:
            queue_file(path)
            queued.append(os.path.basename(path))
        except (OSError, ValueError) as e:
            print("auto-attach queue failed %s: %s" % (path, e), file=sys.stderr)
    return queued


def resolve_workspace_path(raw: str, workspace: str) -> Optional[str]:
    """Resolve user/agent path against workspace; return abspath if file exists."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return None
    if os.path.isabs(raw):
        candidate = os.path.normpath(raw)
    else:
        candidate = os.path.normpath(os.path.join(workspace, raw))
    return candidate if os.path.isfile(candidate) else None


def _multipart_post(open_url, url: str, body: bytes, boundary: str, timeout: float = 120):
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    with open_url(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def send_photo_immediate(open_url, token: str, chat_id: int, photo_path: str) -> None:
    _check_file(photo_path)
    url = "https://api.telegram.org/bot%s/sendPhoto" % token
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
    out = _multipart_post(open_url, url, body, boundary)
    if not out.get("ok"):
        raise RuntimeError("sendPhoto: %s" % out)


def send_document_immediate(open_url, token: str, chat_id: int, file_path: str) -> None:
    _check_file(file_path)
    url = "https://api.telegram.org/bot%s/sendDocument" % token
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
    out = _multipart_post(open_url, url, body, boundary)
    if not out.get("ok"):
        raise RuntimeError("sendDocument: %s" % out)


def send_immediate(open_url, token: str, chat_id: int, file_path: str) -> None:
    if is_image_path(file_path):
        send_photo_immediate(open_url, token, chat_id, file_path)
    else:
        send_document_immediate(open_url, token, chat_id, file_path)
