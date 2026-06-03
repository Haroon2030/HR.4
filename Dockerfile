# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=config.settings \
    PORT=8082

# System deps for psycopg2 + Pillow + build + pg_dump/psql for backups
# Install postgresql-client-18 from PostgreSQL APT repository to match server version 18.x
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
        curl \
        ca-certificates \
        gnupg \
        cron \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy project
COPY backend/ /app/

# Optional: data dump for one-time auto-import on first deploy
COPY data_dump.json* /app/

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/check-hr.sh /usr/local/bin/check-hr
COPY docker/check-production.sh /usr/local/bin/check-production
RUN chmod +x /entrypoint.sh /usr/local/bin/check-hr /usr/local/bin/check-production

# Create runtime dirs (including backups)
RUN mkdir -p /app/staticfiles /app/media /app/logs /app/backups

# تجميع الملفات الثابتة عند البناء — يُسرّع إعادة تشغيل الحاوية (لا يغيّر DJANGO_ENV للتشغيل)
RUN DJANGO_ENV=development SECRET_KEY=build-collectstatic-dummy-key-not-for-production-use \
    python manage.py collectstatic --noinput

EXPOSE 8082

# Migrations run in entrypoint.sh on every container start (before CMD / Gunicorn).
ENTRYPOINT ["/entrypoint.sh"]
# gthread workers — better for I/O-bound apps (DB-heavy). 3 workers × 4 threads = 12 concurrent.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8082} --workers ${GUNICORN_WORKERS:-3} --threads ${GUNICORN_THREADS:-4} --worker-class ${GUNICORN_WORKER_CLASS:-gthread} --timeout ${GUNICORN_TIMEOUT:-120} --keep-alive ${GUNICORN_KEEP_ALIVE:-30} --access-logfile - --error-logfile -"]
