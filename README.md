# 🔮 Astro Oracle Bot

Production-ready Telegram bot и канал в тематике **астрологии, нумерологии,
эзотерики, таро и мистических прогнозов**, построенный на `aiogram 3.x`,
`PostgreSQL`, `Redis` и `OpenAI`.

> Атмосферный AI-ассистент: загадочный стиль ответов, персональные мистические
> прогнозы, нумерологический разбор, расчёт совместимости, расклады Таро и
> автоматические посты в Telegram-канал.

---

## ✨ Возможности

| Раздел | Описание |
| --- | --- |
| **Профиль** | Имя, дата рождения, пол — используются всеми AI-сервисами для персонализации |
| **Прогноз дня** | Атмосферный мистический прогноз на сегодня, сгенерированный GPT-моделью |
| **Нумерология** | Число судьбы, число личности, краткая интерпретация |
| **Совместимость** | Анализ двух дат рождения: эмоции, конфликты, романтика, карма |
| **Таро** | Расклад на 3 карты (прошлое / настоящее / будущее) с AI-интерпретацией |
| **Авто-постинг** | APScheduler публикует в Telegram-канал прогнозы, число дня, энергию дня, мистические предупреждения и вирусные эзотерические посты |
| **Админка** | Команды для статистики, ручной публикации, управления планировщиком, аналитики пользователей |
| **Антиспам / rate-limit** | Middleware на Redis ограничивает частоту сообщений |

---

## 🏗 Архитектура

Проект построен по **Clean Architecture**:

```
app/
├── config/         # Settings (pydantic-settings), конфигурация окружения
├── database/       # Async SQLAlchemy engine/session + Alembic migrations
├── models/         # SQLAlchemy ORM модели (users, subscriptions, ...)
├── repositories/   # Repository pattern — единственная точка доступа к БД
├── services/       # Бизнес-логика: AI, numerology, compatibility, tarot
│   └── ai/         # OpenAI client, prompt templates, retry, генераторы
├── handlers/       # aiogram routers (по доменам: profile, oracle, admin)
├── middlewares/    # DB session, throttling, logging, error wrapping
├── keyboards/      # Reply / inline клавиатуры
├── scheduler/      # APScheduler jobs (авто-постинг)
└── utils/          # Логирование, общие хелперы
```

**Принципы:**

- `async/await` везде (aiogram, SQLAlchemy 2.x async, OpenAI Async client).
- **Dependency Injection** через `aiogram` middlewares (БД-сессии и сервисы
  пробрасываются в хендлеры).
- **Repository pattern** — хендлеры/сервисы не знают про SQL.
- **Service layer** — отдельный слой между хендлерами и репозиториями.
- Строгая **типизация**, проверяется `mypy`.

---

## 🧰 Стек

- **Python 3.12**
- **aiogram 3.13** — Telegram Bot API
- **SQLAlchemy 2.0 (async)** + **asyncpg** — БД
- **Alembic** — миграции
- **Redis 7** — FSM storage, throttling, кеш OpenAI ответов
- **OpenAI Python SDK v1** (Async)
- **APScheduler 3** — авто-постинг
- **pydantic / pydantic-settings** — конфиг и валидация
- **Docker + docker-compose** — деплой

---

## 🚀 Быстрый старт

### 1. Клонировать репозиторий и подготовить `.env`

```bash
git clone <repo-url> astro-bot
cd astro-bot
cp .env.example .env
# отредактируй .env: BOT_TOKEN, OPENAI_API_KEY, CHANNEL_ID, ADMIN_IDS
```

### 2. Запуск через Docker Compose (рекомендуется)

```bash
docker compose up -d --build
docker compose logs -f bot
```

Контейнер `bot` автоматически применяет миграции (`alembic upgrade head`)
и запускает поллинг.

### 3. Локальная разработка без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Postgres и Redis удобно поднять только через compose:
docker compose up -d postgres redis

# Прогон миграций
alembic upgrade head

# Запуск бота
python -m app
```

---

## 🔑 Как получить ключи

### Telegram Bot Token
1. Открыть [@BotFather](https://t.me/BotFather), команда `/newbot`.
2. Скопировать токен в `BOT_TOKEN`.
3. Создать канал, добавить бота **админом** с правом `Post messages`.
4. В `CHANNEL_ID` указать `@channel_username` или числовой `-100…` id.

### OpenAI API Key
1. [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → *Create new secret key*.
2. Скопировать в `OPENAI_API_KEY`.
3. Модель по умолчанию — `gpt-4o-mini` (дёшево + достаточно для мистического стиля).

---

## 🧪 Команды разработки

```bash
ruff check .          # линтер
ruff format .         # автоформат
mypy app              # type-check
pytest                # тесты
alembic revision --autogenerate -m "msg"   # новая миграция
alembic upgrade head  # применить миграции
```

---

## 📋 План разработки

Проект собирается **поэтапно**. Текущий статус:

- [x] **ЭТАП 1** — Архитектура проекта (структура, Docker, конфиг)
- [ ] **ЭТАП 2** — Database layer
- [ ] **ЭТАП 3** — Telegram bot core
- [ ] **ЭТАП 4** — User profile system
- [ ] **ЭТАП 5** — OpenAI integration
- [ ] **ЭТАП 6** — Numerology system
- [ ] **ЭТАП 7** — Compatibility system
- [ ] **ЭТАП 8** — Tarot system
- [ ] **ЭТАП 9** — Scheduler + auto posting
- [ ] **ЭТАП 10** — Admin system
- [ ] **ЭТАП 11** — Finalization

---

## 📜 Лицензия

Проприетарный MVP. Все права защищены.
