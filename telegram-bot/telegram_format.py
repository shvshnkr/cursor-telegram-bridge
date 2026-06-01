"""Prepare long markdown (plans) for Telegram HTML messages."""

from __future__ import annotations

import html
import os
import re
from typing import List, Optional

TELEGRAM_TEXT_LIMIT = 4096
MAX_PLAN_FILE_BYTES = 200_000

_CODE_FENCE_LINE_RE = re.compile(r"^```")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\d+\.\s+(.*)$")


def split_telegram_messages(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Split text into chunks under Telegram's message size limit."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1
        if line_len > limit:
            flush()
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        if current_len + line_len > limit and current:
            flush()
        current.append(line)
        current_len += line_len
    flush()
    return chunks


def split_html_messages(html: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Split HTML for sendMessage; tries to break on paragraph boundaries."""
    html = (html or "").strip()
    if not html:
        return []
    if len(html) <= limit:
        return [html]

    parts = split_telegram_messages(html, limit)
    if len(parts) <= 1:
        return parts

    # Prefer splitting before <pre> blocks when a chunk is still too large
    merged: List[str] = []
    for part in parts:
        if len(part) <= limit:
            merged.append(part)
            continue
        merged.extend(_split_preserving_pre(part, limit))
    return merged


def _split_preserving_pre(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]
    out: List[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            out.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return out


def markdown_plan_to_html(md: str) -> str:
    """Best-effort Markdown → Telegram HTML (parse_mode=HTML)."""
    md = (md or "").replace("\r\n", "\n").strip()
    if not md:
        return ""

    out: List[str] = []
    in_pre = False
    pre_lines: List[str] = []

    for line in md.split("\n"):
        if _CODE_FENCE_LINE_RE.match(line.strip()):
            if in_pre:
                out.append("<pre>" + html.escape("\n".join(pre_lines)) + "</pre>")
                pre_lines = []
                in_pre = False
            else:
                in_pre = True
            continue
        if in_pre:
            pre_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            out.append("")
            continue

        hm = _HEADER_RE.match(stripped)
        if hm:
            out.append("<b>" + html.escape(hm.group(2)) + "</b>")
            continue

        ul = _UL_RE.match(stripped)
        if ul:
            out.append("• " + html.escape(ul.group(1)))
            continue

        ol = _OL_RE.match(stripped)
        if ol:
            out.append(html.escape(ol.group(1)))
            continue

        out.append(html.escape(line))

    if in_pre and pre_lines:
        out.append("<pre>" + html.escape("\n".join(pre_lines)) + "</pre>")

    return "\n".join(out)


def read_plan_file(path: str) -> Optional[str]:
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size > MAX_PLAN_FILE_BYTES:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip() or None
    except OSError:
        return None


def pick_plan_file(paths: List[str]) -> Optional[str]:
    if not paths:
        return None
    scored: List[tuple] = []
    for path in paths:
        base = os.path.basename(path).lower()
        score = 10 if "plan" in base else 0
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > MAX_PLAN_FILE_BYTES:
            continue
        scored.append((score, size, path))
    if not scored:
        return paths[0]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def strip_plan_path_mentions(text: str, paths: List[str]) -> str:
    """Remove file paths and attach notes from intro text."""
    cleaned = text or ""
    for path in paths:
        variants = {
            path,
            os.path.basename(path),
            path.replace("\\", "/"),
            path.replace("/", "\\"),
        }
        for variant in variants:
            if variant:
                cleaned = cleaned.replace(variant, "")
    cleaned = re.sub(r"\[TG_FILE:[^\]]+\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"📎\s*[^\n]*\.md\b[^\n]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def dedupe_intro_from_plan(intro: str, plan_text: str) -> str:
    """If the agent pasted the full plan in the intro, keep only the preamble."""
    intro = (intro or "").strip()
    plan_text = (plan_text or "").strip()
    if not intro or not plan_text:
        return intro
    if len(plan_text) < 80:
        return intro
    head = plan_text[: min(400, len(plan_text))]
    idx = intro.find(head)
    if idx > 0:
        return intro[:idx].strip()
    if intro.strip() == plan_text.strip():
        return ""
    return intro
