# Agent rules (cursor-telegram-bridge)

> Подход к работе с Cursor адаптирован из [Dahusim](https://github.com/shvshnkr/dahusim): оптимальный расход контекста, не «экономия ради экономии».

## Dev rules

- Маленькие focused diff; не трогать unrelated код.
- Root cause first — без speculative guards и log-only fixes.
- Коммиты — только по явной просьбе пользователя.
- Не коммитить `telegram-bot/config`, токены, session files.

## Task router

| Задача | Читать |
|--------|--------|
| Telegram / proxy / bot loop | `telegram-bot/agent_bot.py`, `telegram-bot/proxy.py` |
| Конфиг / workspace / CLI | `telegram-bot/config.example`, `telegram-bot/config_loader.py` |
| Dahusim log triage | `telegram-bot/prompts/log-triage.md`, workspace `AI/symptoms-index.toml` |
| Windows autostart | `scripts/install-task.ps1`, `scripts/smoke-test.ps1` |
| Как просить агента (токены, чаты) | `docs/CURSOR-HOWTO-RU.md` |

## Контекст и токены (Cursor 2.5 Auto)

**Цель — качество и скорость, не минимизация токенов любой ценой.**

- **Новый чат** — на каждую крупную задачу (новый патч, рефакторинг, другой баг). Длинная `--resume` сессия в Telegram = один непрерывный контекст; при смене темы — `/reset` в боте или новый чат в Cursor Desktop.
- **Режимы:** `/ask` для triage и вопросов; `/plan` перед большим diff; `/agent` для правок. Default в config — `CURSOR_AGENT_MODE`.
- **Модель:** `Auto` (Composer 2.5 routing) — рекомендуется; не переключать на «дешёвую» модель ради лимитов, если страдает результат.
- **@‑файлы / Read:** 3–8 ключевых файлов по задаче; не repo-wide explore, если путь уже в router.
- **Фоновый explore** — отдельный subagent; основной чат — для правок.
- **Dahusim workspace:** не перечитывать whole `AI/project-map.toml`; точечный Read/Grep по `symptoms-index.toml` → файл из entry.

## Telegram bot

- SOCKS5 (`PROXY_SOCKS5_URLS`) — **только** для Telegram HTTP; не проксировать `cursor agent`.
- `husi_simple_log_*.txt` → force `--mode ask`, копия в `{CURSOR_WORKSPACE}/AI/incoming-logs/`.
- Session files: `.cursor_agent_session.ask|plan|agent` — отдельно per mode.

## Finally

Read `README.md` and `docs/CURSOR-HOWTO-RU.md`.
