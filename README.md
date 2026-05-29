# cursor-telegram-bridge

**Telegram-бот → локальный Cursor Agent CLI.** Пишете с телефона — на ПК выполняется `agent`, ответ приходит в Telegram.

> **Про проект:** форк [jes/cursor-claw](https://github.com/jes/cursor-claw), доработанный в [Cursor](https://cursor.com) (Agent / Composer 2.5 Auto): Windows, SOCKS5 для Telegram, режимы ask/plan/agent, именованные сессии, triage логов.

---

## Кратко (30 секунд)

1. На ПК: [Cursor CLI](https://cursor.com/docs/cli/installation) (`agent login`), Python 3.10+.
2. Telegram: бот от [@BotFather](https://t.me/BotFather), ваш `user_id`.
3. `copy telegram-bot\config.example telegram-bot\config` → заполнить токен, user_id, путь к проекту.
4. `pip install -r requirements.txt` → `python telegram-bot\agent_bot.py`.
5. В Telegram: `/session help`, `/new mytask`, `/ask …` или `/agent …`.

**Не cloud-агенты** (не cursor-tg): один локальный `agent` на вашей машине. Контекст копится в сессии — для новой задачи `/new имя` или `/reset`.

---

## Возможности

| Функция | Описание |
|---------|----------|
| Telegram ↔ CLI | Polling → `agent --print --trust --force --workspace …` |
| SOCKS5 failover | Только для `api.telegram.org`; CLI и workspace **без** прокси |
| Режимы | `/ask` (read-only), `/plan`, `/agent` |
| Именованные сессии | `/new`, `/use`, `/sessions` — `agent create-chat` + `--resume` |
| Mode-сессии | Отдельный контекст ask / plan / agent, если нет active |
| Логи `husi_simple_log_*.txt` | force ask, копия в `{workspace}/AI/incoming-logs/` |
| Windows autostart | `scripts/install-task.ps1`, smoke-test |
| Язык ответов | `CURSOR_AGENT_LANGUAGE=ru` в config |

---

## Требования

- **Python** 3.10+
- **Cursor Agent CLI** на Windows:
  ```powershell
  irm 'https://cursor.com/install?win32=true' | iex
  agent login
  agent --version
  ```
  На Windows subprocess вызывает `cmd.exe /c agent.CMD` (см. `config_loader.py`).
- **Telegram:** bot token, ваш numeric `user_id`
- **Опционально:** SOCKS5, если `api.telegram.org` недоступен напрямую

---

## Установка

```powershell
git clone https://github.com/shvshnkr/cursor-telegram-bridge.git
cd cursor-telegram-bridge

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy telegram-bot\config.example telegram-bot\config
notepad telegram-bot\config   # токен, user_id, CURSOR_WORKSPACE
```

Узнать `user_id`:

```powershell
cd telegram-bot
python echo_user_ids.py
# напишите боту в Telegram — в консоли появится user_id
```

Запуск:

```powershell
python telegram-bot\agent_bot.py
```

Проверка:

```powershell
.\scripts\smoke-test.ps1
```

Autostart (Task Scheduler):

```powershell
.\scripts\install-task.ps1
Start-ScheduledTask -TaskName cursor-telegram-bridge
```

---

## Конфигурация (`telegram-bot/config`)

Файл **не коммитится**. Шаблон: `telegram-bot/config.example`.

| Ключ | Описание |
|------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен от BotFather |
| `TELEGRAM_ALLOWED_USER_ID` | Только этот user_id может писать боту |
| `CURSOR_WORKSPACE` | Абсолютный путь к проекту для `--workspace` |
| `CURSOR_CLI` | Пусто = auto-detect (`agent` / `cursor agent`) |
| `CURSOR_AGENT_MODE` | Default без префикса: `ask` \| `plan` \| `agent` |
| `CURSOR_AGENT_MODEL` | Рекомендуется `Auto` |
| `CURSOR_AGENT_LANGUAGE` | `ru` — ответы на русском |
| `CURSOR_AGENT_TIMEOUT` | Секунды; `0` = без лимита |
| `PROXY_SOCKS5_URLS` | Через запятую; `socks5h://host:port` (DNS через прокси) |

Пример proxy (замените на свои):

```ini
PROXY_SOCKS5_URLS=socks5h://127.0.0.1:1080,socks5h://127.0.0.1:2080
```

---

## Команды в Telegram

### Режимы (флаг `--mode` для CLI)

| Команда | Режим | Когда |
|---------|-------|-------|
| `/ask …` | ask | Вопросы, triage, review без правок |
| `/plan …` | plan | План перед большим diff |
| `/agent …` | agent | Правки кода, shell |
| *(текст без префикса)* | из `CURSOR_AGENT_MODE` | По умолчанию |

### Именованные сессии (контекст)

| Команда | Действие |
|---------|----------|
| `/new bugfix` | `agent create-chat` → новая сессия, active |
| `/use triage` | Переключить active |
| `/sessions` | Список (`→` = active) |
| `/drop bugfix` | Удалить |
| `/drop all` | Удалить все |
| `/session help` | Справка |

**Active именованная** — все сообщения идут в один `--resume` id.  
**Без active** — три отдельных потока: ask / plan / agent (файлы `.cursor_agent_session.*`).

### Сброс контекста

| Команда | Действие |
|---------|----------|
| `/reset` | Сброс mode-сессий + снять active |
| `/reset ask` | Сброс только ask |
| `/reset all` | Mode + active (именованные записи остаются) |
| `/reset имя` | Удалить именованную сессию |
| `/mode` | Статус: default mode, active, sessions |

### Файлы

- Отправьте **документ** или **фото** (подпись = часть промпта).
- `husi_simple_log_*.txt` → режим **ask**, triage-промпт, копия в `AI/incoming-logs/`.

---

## Сессии и контекст (как не упереться в лимит)

```
Telegram → бот → agent --resume <id> → один непрерывный чат
```

| Ситуация | Действие |
|----------|----------|
| Новая задача | `/new feature-x` или `/reset` |
| Другая задача параллельно | `/new bugfix` + `/use bugfix` |
| Вопрос vs правки | `/ask` vs `/agent` (разные mode-id без active) |
| Длинная переписка | `/reset` или новая именованная сессия |
| Desktop vs Telegram | Разные сессии; не синхронизируются |

Подробнее: [`docs/CURSOR-HOWTO-RU.md`](docs/CURSOR-HOWTO-RU.md).

---

## Архитектура

```
[Telegram] --HTTPS--> [SOCKS5?] --> api.telegram.org
                          |
                     agent_bot.py (polling)
                          |
                     subprocess: agent --print --resume …
                          |
                     CURSOR_WORKSPACE (локально, без proxy)
```

**Структура репозитория:**

```
cursor-telegram-bridge/
  telegram-bot/
    agent_bot.py          # основной цикл
    named_sessions.py     # /new, /use, create-chat
    proxy.py              # SOCKS5 failover
    config_loader.py
    prompts/
      telegram-session.md # шапка новой сессии
      log-triage.md       # шаблон для husi_simple_log_*.txt
  scripts/
    install-task.ps1
    smoke-test.ps1
  docs/
    CURSOR-HOWTO-RU.md
```

**Runtime (gitignore):** `config`, `named_sessions.json`, `.cursor_agent_session.*`, `logs/`, `received_documents/`.

---

## Отличия от upstream [cursor-claw](https://github.com/jes/cursor-claw)

| Патч | Зачем |
|------|-------|
| `proxy.py` | SOCKS5 для Telegram в restricted networks |
| `CURSOR_WORKSPACE` | Workspace не = корень бота |
| ask / plan / agent | CLI `--mode` + Telegram-префиксы |
| Именованные сессии | `create-chat`, `/new`, `/use` |
| UTF-8 subprocess | Fix `charmap` на Windows |
| `agent.CMD` wrapper | `cmd.exe /c` для subprocess |
| log triage | `husi_simple_log_*.txt` → ask + incoming-logs |
| Windows Task Scheduler | `install-task.ps1` |

Merge upstream: `git fetch upstream && git merge upstream/master`

---

## Безопасность

- **Не коммить:** `telegram-bot/config`, токены, session files, логи с перепиской.
- Бот принимает только `TELEGRAM_ALLOWED_USER_ID`.
- Agent: `--trust --force` — только для **личного** бота.
- Прокси только для Telegram; не проксируйте CLI через untrusted SOCKS.

---

## Troubleshooting

| Симптом | Решение |
|---------|---------|
| `WinError 2` при agent | Установите CLI: `irm … \| iex`; в config `CURSOR_CLI=agent` |
| `charmap` codec error | Обновите до последней версии (UTF-8 в subprocess) |
| `Authentication required` | `agent login` |
| Бот молчит | Проверьте proxy, токен, `echo_user_ids.py` |
| Ответы на английском / «принято» | `/reset`; `CURSOR_AGENT_LANGUAGE=ru` |
| Файл не разобран | Отправьте файл **снова** с caption; проверьте `received_documents/` |
| `bot-stderr.log` locked | Один экземпляр бота; убейте лишние `python agent_bot.py` |

---

## Лицензия

Use and modify as you like. Upstream [cursor-claw](https://github.com/jes/cursor-claw) — without warranty.
