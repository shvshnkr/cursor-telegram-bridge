# cursor-telegram-bridge

Telegram ↔ локальный **Cursor CLI** (`cursor agent` / `agent`). Форк [jes/cursor-claw](https://github.com/jes/cursor-claw) с патчами под Windows, SOCKS5 для `api.telegram.org`, режимами ask/plan/agent и triage логов Dahusim.

> **Примечание:** этот репозиторий и большая часть кода написаны с помощью [Cursor](https://cursor.com) (Agent / Composer 2.5 Auto). Upstream — community-проект [cursor-claw](https://github.com/jes/cursor-claw).

## Возможности

- Polling Telegram-бота → subprocess `cursor agent --print --trust --force`
- **SOCKS5 failover** для Telegram API (`PROXY_SOCKS5_URLS`); CLI и workspace **без** прокси
- Режимы: `/ask`, `/plan`, `/agent` (+ default в config)
- Отдельные session files per mode (`.cursor_agent_session.ask|plan|agent`)
- Файлы `husi_simple_log_*.txt` → force ask, копия в `{CURSOR_WORKSPACE}/AI/incoming-logs/`
- Настраиваемый `CURSOR_WORKSPACE` (например `C:\Users\user\DaiHusim`)
- Windows: Task Scheduler (`scripts/install-task.ps1`), smoke-test

## Требования

- Python 3.10+
- [Cursor CLI](https://cursor.com/docs/cli/overview): `agent` или `cursor agent` на PATH, `agent login`
- Telegram bot token ([@BotFather](https://t.me/BotFather))

## Быстрый старт (Windows)

```powershell
cd C:\Users\user\cursor-telegram-bridge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy telegram-bot\config.example telegram-bot\config
# заполнить TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID, CURSOR_WORKSPACE, PROXY_SOCKS5_URLS

python telegram-bot\echo_user_ids.py   # узнать user_id (через proxy)
python telegram-bot\agent_bot.py       # запуск бота
```

Autostart:

```powershell
.\scripts\install-task.ps1
Start-ScheduledTask -TaskName cursor-telegram-bridge
```

Smoke:

```powershell
.\scripts\smoke-test.ps1
```

## Конфиг (`telegram-bot/config`)

| Ключ | Назначение |
|------|------------|
| `TELEGRAM_BOT_TOKEN` | токен бота |
| `TELEGRAM_ALLOWED_USER_ID` | только этот user_id |
| `CURSOR_WORKSPACE` | `--workspace` для agent |
| `CURSOR_CLI` | пусто = auto (`agent` vs `cursor agent`) |
| `CURSOR_AGENT_MODE` | default: `ask` \| `plan` \| `agent` |
| `CURSOR_AGENT_MODEL` | рекомендуется `Auto` |
| `PROXY_SOCKS5_URLS` | через запятую, `socks5h://...` |

Пример proxy chain:

```
socks5h://127.0.0.1:2181,socks5h://127.0.0.1:2080,socks5h://192.168.1.96:11080
```

## Команды в Telegram

| Команда | Действие |
|---------|----------|
| `/ask …` | read-only вопрос |
| `/plan …` | plan mode |
| `/agent …` | agent (правки кода) |
| `/mode` | текущий default и sessions |
| `/reset` | сброс всех session files |
| `/newchat` | подсказка про новый чат |

Текст без префикса → режим из `CURSOR_AGENT_MODE`.

## Работа с Cursor (токены, чаты)

См. [`docs/CURSOR-HOWTO-RU.md`](docs/CURSOR-HOWTO-RU.md) и [`AGENTS.md`](AGENTS.md) — подход адаптирован из [Dahusim](https://github.com/shvshnkr/dahusim): **оптимальный** расход контекста (не «экономия ради экономии»), когда менять чат, какие режимы использовать.

## Upstream

- Fork base: [jes/cursor-claw](https://github.com/jes/cursor-claw)
- Remote `upstream` в этом репо — для merge патчей из оригинала

## Безопасность

- Не коммитить `telegram-bot/config`, session files, токены
- Бот принимает только `TELEGRAM_ALLOWED_USER_ID`
- Agent запускается с `--trust --force` — только для личного бота

## Лицензия

Use and modify as you like. Upstream cursor-claw — без warranty.
