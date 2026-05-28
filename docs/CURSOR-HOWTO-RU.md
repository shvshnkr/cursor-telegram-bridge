# Cursor: how-to для cursor-telegram-bridge

Подход адаптирован из [Dahusim docs/CURSOR-HOWTO-RU](https://github.com/shvshnkr/dahusim).  
**Цель — оптимальный расход контекста и лимитов Cursor 2.5 Auto, не «экономия любой ценой».**

## Контекст и окна агента

- **Новый чат Agent/Composer** — на каждую крупную задачу (новый патч, другой баг, смена архитектуры). Длинная переписка съедает контекст; модель путает ветки и ранние решения.
- **Telegram `--resume`** — один непрерывный поток в боте. Сменили тему → `/reset` в Telegram или новый чат в Cursor Desktop.
- **Plan mode** (`/plan`) — перед большим diff: согласовать scope, не править код до подтверждения.
- **@‑файлы** — 3–8 ключевых файлов, не весь репозиторий.
- **Фоновый explore** — отдельный subagent; основной чат — для правок.

## Модель: Auto (Composer 2.5)

- В config: `CURSOR_AGENT_MODEL=Auto` — рекомендуется.
- Auto маршрутизирует между моделями; не переключайтесь на «дешёвую» модель ради лимитов, если страдает качество triage или diff.
- При **usage limit** в Cursor: подождать reset, уменьшить scope задачи, `/ask` вместо `/agent` для анализа — но не отказываться от Auto без причины.

## Режимы через Telegram

| Ситуация | Режим |
|----------|-------|
| Вопрос, triage лога, code review | `/ask` |
| План большого рефакторинга | `/plan` |
| Правки кода, коммиты, CI | `/agent` |
| `husi_simple_log_*.txt` | автоматически **ask** (код не менять) |

## Этот репозиторий (бот)

- Правила агента: [`AGENTS.md`](../AGENTS.md)
- Конфиг: `telegram-bot/config.example`
- Коммиты — только по явной просьбе
- Proxy только для Telegram; `cursor agent` — локально, без SOCKS

## Dahusim workspace

Если `CURSOR_WORKSPACE` указывает на Dahusim:

1. Не делать repo-wide explore — см. `AI/symptoms-index.toml` → нужный `.kt`
2. Лог simple-mode: grep H24, H37, H4, H1 (см. Dahusim CURSOR-HOWTO)
3. Файлы из Telegram: `AI/incoming-logs/` (gitignored в Dahusim)

## Когда сменить чат (чеклист)

- [ ] Другая фича / другой репозиторий
- [ ] Агент повторяет отвергнутые идеи
- [ ] Контекст > ~30–50 сообщений без `/reset`
- [ ] После merge/релиза — новая сессия для следующего тикета
- [ ] Usage limit — новый чат не поможет; нужен reset лимита или меньший scope

## Запрос к агенту (шаблон)

```
Симптом: …
Режим: /ask или /agent
Workspace: DaiHusim / cursor-telegram-bridge
Ограничение: не трогать X, только Y
Лог/файл: @path или приложить husi_simple_log_*.txt
```
