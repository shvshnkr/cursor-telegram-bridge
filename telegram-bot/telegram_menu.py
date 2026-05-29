"""Telegram bot command menu and reply keyboard."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

BOT_COMMANDS: List[Dict[str, str]] = [
    {"command": "start", "description": "Старт и клавиатура"},
    {"command": "help", "description": "Справка по командам"},
    {"command": "stop", "description": "Остановить агента"},
    {"command": "mode", "description": "Статус сессий"},
    {"command": "sessions", "description": "Список именованных сессий"},
    {"command": "reset", "description": "Сброс контекста"},
    {"command": "ask", "description": "Режим вопросов"},
    {"command": "plan", "description": "Режим плана"},
    {"command": "agent", "description": "Режим правок"},
    {"command": "newchat", "description": "Подсказка по новому чату"},
]


def reply_keyboard_markup() -> Dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "/sessions"}, {"text": "/mode"}, {"text": "/stop"}],
            [{"text": "/ask"}, {"text": "/plan"}, {"text": "/agent"}],
            [{"text": "/reset"}, {"text": "/help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def reply_keyboard_remove() -> Dict[str, Any]:
    return {"remove_keyboard": True}


def register_bot_commands(api_fn: Callable[..., Any]) -> None:
    try:
        api_fn("setMyCommands", commands=BOT_COMMANDS)
    except Exception as e:
        print("setMyCommands failed: %s" % e, file=__import__("sys").stderr)


def start_message(
    workspace: str,
    default_mode: str,
    active_named: Optional[str],
) -> str:
    active = active_named or "(нет)"
    return (
        "*cursor-telegram-bridge*\n\n"
        "Workspace: `%s`\n"
        "Режим по умолчанию: `%s`\n"
        "Active сессия: `%s`\n\n"
        "Кнопки внизу — быстрые команды. Полный список: /help\n"
        "Именованные сессии: /session help"
    ) % (workspace, default_mode, active)


def help_message(default_mode: str) -> str:
    return (
        "*Команды*\n\n"
        "*Режимы* (префикс к тексту):\n"
        "- `/ask` — вопросы, triage\n"
        "- `/plan` — план без правок\n"
        "- `/agent` — правки кода\n"
        "- без префикса — режим `%s`\n\n"
        "*Сессии:* `/new имя`, `/use имя`, `/sessions`, `/drop имя`\n"
        "*Сброс:* `/reset`, `/mode`\n"
        "*Агент:* `/stop` — прервать текущий запуск\n\n"
        "Во время работы агента команды и `/stop` доступны сразу.\n"
        "Скрыть кнопки: /keyboard_hide"
    ) % default_mode
