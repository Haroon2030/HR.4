#!/bin/sh
set -e

# ─── Django migrations (كل نشر / كل إعادة تشغيل للحاوية) ─────────────────────
# يُنفَّذ هنا قبل Gunicorn — لا حاجة لتشغيل migrate يدوياً بعد الرفع إن وُجد ENTRYPOINT.
# إعادة المحاولة تساعد عند اتصال قاعدة سحابية بطيئة الاستيقاظ (مثل Neon).
MIGRATE_MAX_RETRIES="${MIGRATE_MAX_RETRIES:-5}"
MIGRATE_RETRY_SECS="${MIGRATE_RETRY_SECS:-5}"
# النسخ إلى R2 قبل migrate (إن وُجدت migrations معلّقة) يتم داخل أمر migrate في apps.core

n=1
while [ "$n" -le "$MIGRATE_MAX_RETRIES" ]; do
    echo "==> Database migrations (deploy start, attempt $n/$MIGRATE_MAX_RETRIES)..."
    if python manage.py migrate --noinput; then
        echo "==> Migrations applied successfully."
        break
    fi
    if [ "$n" -eq "$MIGRATE_MAX_RETRIES" ]; then
        echo "!! migrate failed after $MIGRATE_MAX_RETRIES attempts — aborting."
        exit 1
    fi
    echo "!! migrate failed; retrying in ${MIGRATE_RETRY_SECS}s..."
    sleep "$MIGRATE_RETRY_SECS"
    n=$((n + 1))
done

# ─── مزامنة سجل الصلاحيات من الـ decorators (مهم عند نشر migrations غير core فقط) ─
echo "==> Syncing permission registry (post-migrate deploy)..."
python manage.py shell <<'PY_SYNC'
import apps.core.web_views  # noqa: F401 - load views so decorators register perms
from apps.core.permissions_registry import sync_to_db
try:
    m, p, n = sync_to_db(verbose=False)
    print(f"[permissions] deploy sync: {m} modules, {p} perms ({n} new)")
except Exception as exc:
    print(f"[permissions] deploy sync failed (non-fatal): {exc}")
PY_SYNC

echo "==> Collecting static files (إنتاج — يضمن وجود ملفات مثل css/login.css)..."
python manage.py collectstatic --noinput

# ─── Redis (موصى به مع عدة workers — لا يوقف الإقلاع) ───────────────────────
echo "==> Cache backend check..."
python manage.py shell <<'PY_REDIS'
import os
from django.conf import settings

redis_url = (os.environ.get('REDIS_URL') or '').strip()
prod = os.environ.get('DJANGO_ENV', '').lower() == 'production' or not settings.DEBUG
backend = settings.CACHES.get('default', {}).get('BACKEND', '')
if prod and not redis_url and 'locmem' in backend.lower():
    print(
        '!! WARNING: REDIS_URL غير مضبوط — LocMemCache مع عدة workers Gunicorn '
        'قد يسبب جلسات/حدود API غير متسقة. أضف REDIS_URL عند توفر Redis.'
    )
elif redis_url:
    print('==> REDIS_URL مضبوط — Cache: Redis.')
PY_REDIS

# ─── فحص قاعدة البيانات والبصمة (بعد migrate + collectstatic) ───────────────
echo "==> Attendance / database deploy check..."
if ! python manage.py check_attendance_production --deploy; then
    echo "!! check_attendance_production --deploy failed — aborting container start."
    exit 1
fi

# ─── Auto-load initial data on first deploy (idempotent via marker file) ──────
# DOUBLE-SAFE: never flushes if the DB already contains user data, even if the
# marker file is missing (e.g. container recreated without a persistent volume).
#
# Marker file logic alone:
#   - First deploy: marker absent → flush + load → write marker.
#   - Subsequent: marker present → skip entirely → DB preserved.
#
# Extra safety check below: if Branch / Employee / Role rows exist, we ALWAYS
# skip the import — even when the marker is missing. This prevents accidental
# data loss when the marker volume is lost.
if [ -f /app/data_dump.json ] && [ ! -f /app/.data_loaded ]; then
    HAS_DATA=$(python manage.py shell -c "
from django.db import connection
try:
    with connection.cursor() as c:
        for table in ['core_branch', 'employees_employee', 'core_role']:
            c.execute(f'SELECT COUNT(*) FROM {table}')
            if c.fetchone()[0] > 0:
                print('YES'); break
        else:
            print('NO')
except Exception:
    print('NO')
" 2>/dev/null | tail -n 1)

    if [ "$HAS_DATA" = "YES" ]; then
        echo "==> Database already contains data — creating marker WITHOUT import (safety)."
        touch /app/.data_loaded
    else
        echo "==> Empty database detected — loading initial data from data_dump.json ..."
        python manage.py import_initial_data /app/data_dump.json \
            --flush \
            --marker /app/.data_loaded \
            || echo "!! import_initial_data failed — will retry on next deploy"
    fi
fi

# ─── Ensure superuser exists (created ONCE on first deploy, never overwritten) ─
# If 'admin' already exists, we leave it untouched. Password changes, role edits,
# and email updates done via the UI are PRESERVED across redeploys.
# To force a reset: delete the row in auth_user via Adminer, then redeploy.
echo "==> Checking superuser '${DJANGO_SUPERUSER_USERNAME:-admin}'..."
python manage.py shell <<PYEOF
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = (os.environ.get('DJANGO_SUPERUSER_PASSWORD') or '').strip()
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')

if User.objects.filter(username=username).exists():
    print(f"Superuser '{username}' already exists \u2014 leaving it untouched.")
elif not password:
    print(
        "!! DJANGO_SUPERUSER_PASSWORD is not set \u2014 "
        "skipping superuser creation. Set it in .env before first deploy."
    )
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' created.")
PYEOF

echo "==> Fixing swapped code/name records (idempotent)..."
python manage.py fix_swapped_code_name || echo "!! fix_swapped_code_name failed (non-fatal)"

# ─── وكيل البصمة (API ingest على السحابة — لا يسحب من LAN داخل الحاوية) ─────
echo "==> Attendance agent API (production check)..."
python manage.py shell <<'PY_AGENT'
import os
from django.conf import settings

key = (getattr(settings, 'ATTENDANCE_AGENT_API_KEY', None) or '').strip()
prod = os.environ.get('DJANGO_ENV', '').lower() == 'production' or not settings.DEBUG
if prod and not key:
    print(
        '!! WARNING: ATTENDANCE_AGENT_API_KEY غير مضبوط في .env — '
        'فعّل المفتاح ثم شغّل وكيل الفرع (backend/scripts/biometric_bridge).'
    )
elif prod:
    print('==> ATTENDANCE_AGENT_API_KEY مضبوط — جاهز لاستقبال الوكيل من الفرع.')
else:
    print('==> Attendance agent: فحص الإنتاج متخطى (بيئة تطوير).')
PY_AGENT

# ─── Cron: نسخ احتياطي يومي + تنبيهات وثائق (اختياري لكل منهما) ───────────────
CRON_NEEDED=false
if [ "${BACKUP_ENABLED:-true}" = "true" ]; then CRON_NEEDED=true; fi
if [ "${DOCUMENT_EXPIRY_CRON:-true}" = "true" ]; then CRON_NEEDED=true; fi
if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then CRON_NEEDED=true; fi

if [ "$CRON_NEEDED" = "true" ]; then
    mkdir -p /app/backups /app/logs
    {
        echo "SHELL=/bin/sh"
        echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        if [ "${BACKUP_ENABLED:-true}" = "true" ]; then
            BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-0 3 * * *}"
            echo "${BACKUP_SCHEDULE} root cd /app && python manage.py backup_db --cleanup --trigger cron >> /app/logs/backup.log 2>&1"
        fi
        if [ "${DOCUMENT_EXPIRY_CRON:-true}" = "true" ]; then
            DOC_SCHED="${DOCUMENT_EXPIRY_CRON_SCHEDULE:-30 6 * * *}"
            DOC_DAYS="${DOCUMENT_EXPIRY_CRON_DAYS:-30}"
            DOC_EXTRA=""
            if [ "${DOCUMENT_EXPIRY_CRON_SEND_EMAIL:-false}" = "true" ]; then
                DOC_EXTRA=" --send-email"
            fi
            echo "${DOC_SCHED} root cd /app && python manage.py notify_document_expiry --days ${DOC_DAYS}${DOC_EXTRA} >> /app/logs/document_expiry.log 2>&1"
        fi
        if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then
            OPS_SCHED="${OPERATIONS_REPORT_CRON_SCHEDULE:-* * * * *}"
            echo "${OPS_SCHED} root cd /app && python manage.py send_operations_report --send-email >> /app/logs/operations_report.log 2>&1"
        fi
    } > /etc/cron.d/hr-backup
    chmod 0644 /etc/cron.d/hr-backup
    crontab /etc/cron.d/hr-backup
    service cron start || cron || echo "!! cron service start failed (non-fatal)"
    if [ "${BACKUP_ENABLED:-true}" = "true" ]; then
        echo "==> Backup cron: ${BACKUP_SCHEDULE:-0 3 * * *}"
    fi
    if [ "${DOCUMENT_EXPIRY_CRON:-true}" = "true" ]; then
        echo "==> Document expiry cron: ${DOCUMENT_EXPIRY_CRON_SCHEDULE:-30 6 * * *} (--days ${DOCUMENT_EXPIRY_CRON_DAYS:-30})"
    fi
    if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then
        echo "==> Operations report cron: ${OPERATIONS_REPORT_CRON_SCHEDULE:-* * * * *} (time from DB settings)"
    fi
else
    echo "==> Cron disabled (BACKUP_ENABLED=false and DOCUMENT_EXPIRY_CRON=false and OPERATIONS_REPORT_CRON=false)"
fi

echo "==> Starting: $@"
exec "$@"
