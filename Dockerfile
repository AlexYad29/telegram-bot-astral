# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder ----------
# Собираем колёса в отдельный prefix, чтобы итоговый образ не тянул
# build-essential / libpq-dev и оставался максимально лёгким.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Системные зависимости только для сборки нативных колёс (asyncpg, cryptography).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Ставим в отдельный prefix — потом просто копируем `/install` в runtime-стадию.
RUN pip install --upgrade pip \
    && pip install --prefix=/install -r requirements.txt


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Moscow

WORKDIR /app

# В runtime достаточно libpq5 + tzdata; build-essential / libpq-dev НЕ берём —
# образ остаётся компактным.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        tzdata \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Кладём собранные зависимости из builder-стадии.
COPY --from=builder /install /usr/local

# Исходники приложения.
COPY alembic.ini ./alembic.ini
COPY app ./app
COPY assets ./assets

# Не-root пользователь.
RUN groupadd -r app && useradd -r -g app -m app \
    && chown -R app:app /app
USER app

# Лёгкий healthcheck: процесс жив и Python способен запуститься.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import app" || exit 1

# По умолчанию: миграции → polling.
CMD ["sh", "-c", "alembic upgrade head && python -m app"]
