# 🔮 Astro Oracle Bot

Production-ready Telegram-бот и канал в тематике **астрологии, нумерологии,
эзотерики, таро и мистических прогнозов**. Построен на `aiogram 3.x`,
`PostgreSQL`, `Redis`, `APScheduler` и `OpenAI`.

> Атмосферный AI-ассистент: загадочный стиль ответов, персональные мистические
> прогнозы, нумерологический разбор, расчёт совместимости, расклады Таро,
> автоматические посты в Telegram-канал.

---

## Содержание

- [Возможности](#-возможности)
- [Команды](#-команды)
- [Архитектура](#-архитектура)
- [Стек](#-стек)
- [Быстрый старт](#-быстрый-старт)
- [Конфигурация (`.env`)](#-конфигурация-env)
- [Как получить ключи](#-как-получить-ключи)
- [Расписание авто-постинга](#-расписание-авто-постинга)
- [Разработка](#-разработка)
- [Тестирование](#-тестирование)
- [Продакшен-деплой](#-продакшен-деплой)
- [Troubleshooting](#-troubleshooting)
- [Структура проекта](#-структура-проекта)
- [Лицензия](#-лицензия)

---

## ✨ Возможности

| Раздел | Описание |
| --- | --- |
| **Профиль** | Имя, дата рождения, пол — собираются через FSM и используются всеми AI-сервисами для персонализации |
| **Прогноз дня** | Атмосферный мистический прогноз на сегодня от GPT-модели, кнопка «погадать ещё раз» |
| **Нумерология** | Число судьбы (life path) + число личности (expression) с master numbers 11/22/33 и краткой интерпретацией |
| **Совместимость** | Анализ двух дат рождения: эмоции, конфликтность, романтический потенциал, кармическая связь |
| **Таро** | Расклад на 3 карты (Прошлое / Настоящее / Будущее) с AI-интерпретацией; работает с / без вопроса пользователя |
| **Авто-постинг** | APScheduler публикует в Telegram-канал по cron: прогноз дня, число дня, энергия дня, мистические предупреждения, вирусные эзотерические посты |
| **Админка** | `/admin`, `/stats`, `/post_now <kind>`, `/scheduler`, `/scheduler_pause`, `/scheduler_resume` — только для `ADMIN_IDS` |
| **Антиспам / rate-limit** | Redis-middleware ограничивает частоту сообщений на пользователя |
| **Логи и обработка ошибок** | Глобальный error handler, типизированный logging-middleware, мистические fallback'и при сбоях OpenAI |

---

## 🤖 Команды

### Пользовательские

| Команда | Что делает |
| --- | --- |
| `/start` | Приветствие + главное меню (reply-клавиатура) |
| `/profile` | Профиль: просмотр, FSM-регистрация, точечное редактирование |
| `/edit_profile` | Открыть меню редактирования профиля |
| `/cancel` | Прервать любой FSM-флоу |
| `/forecast` | Мистический прогноз дня |
| `/numerology` | Число судьбы + число личности |
| `/compatibility` | Совместимость с партнёром (две даты рождения) |
| `/tarot` | Расклад на 3 карты Таро (по желанию — с вопросом) |
| `/help` | Список команд |

### Админ-команды (только для `ADMIN_IDS`)

| Команда | Что делает |
| --- | --- |
| `/admin` | Help по админ-командам |
| `/stats` | Срез метрик: пользователи (всего / с профилем / активные 24h / 7d / заблокированы), посты по статусам, посты по kind за 7 дней |
| `/post_now <kind>` | Сгенерировать и **сразу** опубликовать пост в канал. Алиасы: `forecast`, `number`, `energy`, `warning`, `viral` |
| `/scheduler` | Статус планировщика + список job'ов с `next_run_time` |
| `/scheduler_pause` | Поставить все job'ы на паузу |
| `/scheduler_resume` | Снять паузу (или запустить, если был остановлен) |

---

## 🏗 Архитектура

Проект построен по **Clean Architecture** со строгими слоями:

```
app/
├── config/         # Settings (pydantic-settings) — единая точка для всех env-vars
├── database/       # Async SQLAlchemy engine/session + Alembic migrations
├── models/         # ORM-модели (User, Subscription, GeneratedPost, TarotHistory, CompatibilityCheck)
├── repositories/   # Repository pattern — единственная точка доступа к БД
├── services/       # Бизнес-логика:
│   ├── ai/         # OpenAI client + prompt templates + retry
│   ├── numerology.py
│   ├── compatibility.py
│   ├── tarot.py
│   ├── profile.py
│   └── admin_stats.py
├── handlers/       # aiogram routers по доменам
├── filters/        # AdminFilter и т.п.
├── middlewares/    # DB session, throttling, logging, user upsert, AI service, admin context
├── keyboards/      # Reply / inline клавиатуры
├── states/         # FSM-состояния (хранятся отдельно от хендлеров)
├── scheduler/      # APScheduler jobs (авто-постинг)
└── utils/          # Логирование, общие хелперы
```

**Принципы:**

- `async/await` везде (aiogram, SQLAlchemy 2.x async, OpenAI Async).
- **Dependency Injection** через aiogram middlewares (БД-сессии, `ai_service`, `scheduler`, `settings` пробрасываются в handler kwargs).
- **Repository pattern** — handler'ы и сервисы не знают про SQL.
- **Service layer** — бизнес-логика отделена от транспорта (Telegram) и от инфраструктуры (БД).
- Строгая **типизация** (`from __future__ import annotations`, Mapped[..] / Protocol / dataclass).
- Нет циклических импортов — слои импортируют только «вниз».

### Layered dependency direction

```
handlers  → services → repositories → models
   ↓           ↓
keyboards   services/ai (OpenAI)
   ↓
states / filters / middlewares
```

---

## 🧰 Стек

- **Python 3.12**
- **aiogram 3.13** — Telegram Bot API
- **SQLAlchemy 2.0 (async)** + **asyncpg** — БД
- **Alembic** — миграции
- **Redis 7** — FSM storage + throttling
- **OpenAI Python SDK v1** (Async) — генерация текста
- **APScheduler 3.10** — авто-постинг по cron
- **pydantic 2 / pydantic-settings** — конфиг и валидация
- **tenacity** — ретраи OpenAI-запросов
- **Docker + docker-compose** — деплой
- **ruff** + **mypy** + **pytest** — качество кода

---

## 🚀 Быстрый старт

### Через Docker Compose (рекомендуется)

```bash
git clone https://github.com/AlexYad29/telegram-bot-astral.git astro-bot
cd astro-bot
cp .env.example .env
# Отредактируй .env: BOT_TOKEN, OPENAI_API_KEY, CHANNEL_ID, ADMIN_IDS

docker compose up -d --build
docker compose logs -f bot
```

Контейнер `bot` автоматически применяет миграции (`alembic upgrade head`) и
запускает long-polling. Postgres и Redis поднимаются с healthcheck'ами —
бот стартует только после того, как оба сервиса готовы.

### Локально без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Postgres + Redis — поднимаем только их через compose:
docker compose up -d postgres redis

# Миграции
alembic upgrade head

# Запуск бота
python -m app
```

---

## ⚙ Конфигурация (`.env`)

Полный список переменных — в [`.env.example`](.env.example). Основные:

| Переменная | Обязательная | Описание |
| --- | --- | --- |
| `BOT_TOKEN` | ✅ | Токен из [@BotFather](https://t.me/BotFather) |
| `BOT_USERNAME` | — | username без `@` (используется в логах) |
| `CHANNEL_ID` | для авто-постинга | `@channel_username` или числовой `-100...` |
| `ADMIN_IDS` | для админки | Comma-separated: `123456,7890` |
| `OPENAI_API_KEY` | ✅ | Ключ с [platform.openai.com](https://platform.openai.com/api-keys) |
| `OPENAI_MODEL` | — | По умолчанию `gpt-4o-mini` |
| `OPENAI_TEMPERATURE` | — | `0.9` — мистический «творческий» режим |
| `OPENAI_MAX_TOKENS` | — | `600` |
| `POSTGRES_*` | ✅ | Хост/порт/БД/пользователь/пароль |
| `REDIS_*` | ✅ | Хост/порт/DB |
| `TIMEZONE` | — | `Europe/Moscow` — определяет cron планировщика |
| `LOG_LEVEL` | — | `INFO`/`DEBUG`/`WARNING` |
| `RATE_LIMIT_MESSAGES_PER_MINUTE` | — | антиспам, по умолчанию 20 |
| `THROTTLE_DEFAULT_RATE` | — | минимальный интервал (секунды) между сообщениями одного пользователя |

> Все секреты внутри pydantic обёрнуты в `SecretStr` — их нельзя случайно
> вывести в лог через `repr(settings)`.

---

## 🔑 Как получить ключи

### Telegram Bot Token

1. Откройте [@BotFather](https://t.me/BotFather) → команда `/newbot`.
2. Скопируйте токен в `BOT_TOKEN`.
3. Создайте Telegram-канал, добавьте бота **админом** с правом *Post messages*.
4. В `CHANNEL_ID` укажите `@channel_username` или числовой id вида `-100…`
   (получить — переслать любое сообщение из канала в [@userinfobot](https://t.me/userinfobot)).
5. Свой Telegram user_id (для `ADMIN_IDS`) — там же, через [@userinfobot](https://t.me/userinfobot).

### OpenAI API Key

1. [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → *Create new secret key*.
2. Скопируйте в `OPENAI_API_KEY`.
3. Модель по умолчанию — `gpt-4o-mini` (дёшево + хватает для мистического стиля).
   Можно поменять на `gpt-4o` для большего качества.

---

## 📅 Расписание авто-постинга

Расписание описано в `app/scheduler/schedules.py` через `CronSpec`. По умолчанию:

| Тип поста (`PostKind`) | Когда |
| --- | --- |
| `DAY_FORECAST` | Каждый день в **09:00** |
| `DAY_NUMBER` | Каждый день в **10:00** |
| `DAY_ENERGY` | Каждый день в **12:00** |
| `MYSTICAL_WARNING` | По понедельникам / пятницам в **20:00** |
| `VIRAL` | По воскресеньям в **18:00** |

Time zone берётся из `TIMEZONE` (`Europe/Moscow` по умолчанию). Чтобы изменить
расписание — отредактируйте `DEFAULT_SCHEDULE` в
[`app/scheduler/schedules.py`](app/scheduler/schedules.py).

Каждый job:
1. Зовёт `AIService.generate_channel_post(kind, today, day_number?)`.
2. Создаёт запись в `generated_posts` со статусом `SCHEDULED`.
3. Отправляет текст в `CHANNEL_ID` через `bot.send_message`.
4. Помечает запись `SENT` (или `FAILED` с текстом ошибки).

Админ может в любой момент вызвать `/post_now <kind>` — это та же job-функция,
запущенная вручную, с записью в БД.

---

## 🧪 Разработка

```bash
# Установка окружения
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Линтер
ruff check .
ruff format .

# Type-check
mypy app

# Тесты
pytest

# Новая миграция (по diff'у моделей)
alembic revision --autogenerate -m "add new column"
alembic upgrade head
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) запускает `ruff check`
и `pytest` на каждый PR и push в `main`.

---

## ✅ Тестирование

В `tests/` лежат unit-тесты на:

- валидаторы и сервисы (`profile`, `numerology`, `compatibility`, `tarot`, `admin_stats`);
- prompt-builder'ы и AI-service (с моками `AIClient`);
- middleware'ы и фильтры (`AdminFilter`);
- handler'ы (smoke + happy/sad paths с моками);
- scheduler jobs и cron-расписание;
- репозитории (через SQLite in-memory с подменой `BigInteger → Integer`).

```bash
pytest -q              # быстро
pytest -vv             # подробно
pytest -k admin        # только админка
pytest --co -q         # collect-only — посмотреть список тестов
```

---

## 🚢 Продакшен-деплой

### Чек-лист перед запуском

- [ ] Заполнен `.env`: `BOT_TOKEN`, `OPENAI_API_KEY`, `CHANNEL_ID`, `ADMIN_IDS`, `POSTGRES_*`, `REDIS_*`.
- [ ] У бота **есть права** в канале (Post messages).
- [ ] `TIMEZONE` совпадает с тем, в котором вы хотите видеть посты.
- [ ] Резервное копирование Postgres настроено (volume `postgres_data`).
- [ ] Проброса портов наружу не настроено — в `docker-compose.yml` postgres/redis
      слушают только `127.0.0.1`.

### Запуск

```bash
docker compose up -d --build
docker compose logs -f bot          # хвост логов
docker compose ps                   # статус сервисов
docker compose exec bot alembic current   # текущий head миграций
docker compose down                 # стоп (данные остаются в volume)
```

### Обновление кода

```bash
git pull
docker compose build bot
docker compose up -d bot            # пересоздаст контейнер с новой миграцией
```

Образ собран в **2 стадии** (`builder` + `runtime`): runtime-стадия не содержит
`build-essential`/`libpq-dev`, поэтому итоговый образ компактный.

### Backups

```bash
# Дамп
docker compose exec postgres pg_dump -U astrobot astrobot > backup.sql

# Восстановление
cat backup.sql | docker compose exec -T postgres psql -U astrobot astrobot
```

---

## 🛟 Troubleshooting

| Симптом | Решение |
| --- | --- |
| `bot` сразу падает с `alembic.util.exc.CommandError` | Проверь `POSTGRES_*` в `.env`; контейнер видит postgres по hostname `postgres`. |
| Бот не отвечает на `/start` | `docker compose logs bot` — обычно неверный `BOT_TOKEN` или 401 от Telegram. |
| Авто-посты не идут в канал | `docker compose logs bot \| grep autopost`. Чаще всего: бот не админ канала, либо `CHANNEL_ID` без `@` для публичных / с неверным форматом для приватных. |
| OpenAI отвечает 401 | Истёк/неверный `OPENAI_API_KEY` — обнови, перезапусти `bot`. |
| `RateLimitError` от OpenAI | Поднял ли биллинг? Tenacity ретраит 3 раза с expo backoff — если падает снова, проверь квоту. |
| `/stats` показывает 0 пользователей | Никто ещё не вызывал `/start` — `UserUpsertMiddleware` создаёт строку при первом апдейте. |
| Не приходят админ-команды | Свой Telegram id есть в `ADMIN_IDS`? (формат: `ADMIN_IDS=123,456`, без пробелов). |
| FSM «застрял» | Пользователю — `/cancel`. Сервер: `docker compose restart bot` (Redis-state сохранится). |

Логи стандартного формата: `LEVEL logger:line — message`. Запросы к Telegram /
OpenAI / SQL приглушены до WARNING — чтобы не шуметь.

---

## 📂 Структура проекта

```
astro-bot/
├── alembic.ini
├── docker-compose.yml
├── Dockerfile                 # multi-stage (builder + runtime)
├── pyproject.toml             # ruff + mypy + pytest config
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .github/workflows/ci.yml   # GitHub Actions
├── app/
│   ├── __main__.py            # entrypoint: bot + scheduler + middlewares
│   ├── bot.py                 # фабрики Bot / Dispatcher / Redis
│   ├── config/settings.py     # pydantic Settings
│   ├── database/
│   │   ├── base.py            # DeclarativeBase + naming convention
│   │   ├── session.py         # async engine + session_scope
│   │   └── migrations/        # Alembic
│   ├── models/                # User, Subscription, GeneratedPost, TarotHistory, CompatibilityCheck
│   ├── repositories/          # CRUD + admin-queries
│   ├── services/
│   │   ├── ai/                # OpenAIClient + prompts + AIService
│   │   ├── numerology.py
│   │   ├── compatibility.py
│   │   ├── tarot.py
│   │   ├── profile.py
│   │   └── admin_stats.py
│   ├── handlers/              # common / profile / forecast / numerology
│   │                          # / compatibility / tarot / admin / errors
│   ├── filters/admin.py
│   ├── middlewares/           # db_session, throttling, logging,
│   │                          # user_upsert, ai_service, admin_context
│   ├── keyboards/             # main_menu, profile, compatibility, tarot
│   ├── states/                # profile, compatibility, tarot
│   ├── scheduler/             # scheduler, jobs, schedules
│   └── utils/logging.py
├── assets/tarot/major_arcana.json
└── tests/                     # pytest, 22+ модулей, 170+ тестов
```

---

## 📜 Лицензия

Проприетарный MVP. Все права защищены.
