# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Moscow

WORKDIR /app

# System dependencies: build tools for asyncpg / cryptography, libpq for runtime, tzdata for scheduler.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        tzdata \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first to maximise layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source.
COPY alembic.ini ./alembic.ini
COPY app ./app
COPY assets ./assets

# Non-root user.
RUN groupadd -r app && useradd -r -g app -m app \
    && chown -R app:app /app
USER app

# Default command: run DB migrations then start the bot.
CMD ["sh", "-c", "alembic upgrade head && python -m app"]
