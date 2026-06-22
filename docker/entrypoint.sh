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

# ─── إعدادات تقرير العمليات (جدول + سجل افتراضي) ─────────────────────────────
echo "==> Ensuring operations report settings table..."
python manage.py ensure_operations_report_settings || {
    echo "!! ensure_operations_report_settings failed — aborting."
    exit 1
}

echo "==> Ensuring workflow WhatsApp settings table..."
python manage.py ensure_workflow_whatsapp_settings || {
    echo "!! ensure_workflow_whatsapp_settings failed — aborting."
    exit 1
}

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

# ─── SMTP (البريد — لا يوقف الإقلاع) ─────────────────────────────────────────
echo "==> Email / SMTP check..."
if python manage.py check_email_delivery --verify-connection; then
    echo "==> SMTP connection OK."
else
    echo "!! WARNING: SMTP غير جاهز أو فشل الاتصال — جدول الدوام وتقرير العمليات لن يُرسلا فعلياً."
fi

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
# If username already exists in PostgreSQL, password and profile are left untouched.
# Set in Dokploy Environment — example: DJANGO_SUPERUSER_USERNAME=1
echo "==> Bootstrap superuser (once) '${DJANGO_SUPERUSER_USERNAME:-admin}'..."
python manage.py ensure_bootstrap_superuser || echo "!! ensure_bootstrap_superuser failed (non-fatal)"

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

# ─── Cron: نسخ احتياطي يومي + تقرير العمليات (اختياري لكل منهما) ─────────────
CRON_NEEDED=false
if [ "${BACKUP_ENABLED:-true}" = "true" ]; then CRON_NEEDED=true; fi
if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then CRON_NEEDED=true; fi

if [ "$CRON_NEEDED" = "true" ]; then
    mkdir -p /app/backups /app/logs
    # cron لا يرث متغيرات Docker — نحفظها بقيم مُهرَّبة باستخدام Python
    python - <<'PY_ENV'
import os, sys
keys = (
    'DJANGO_ENV','DJANGO_SETTINGS_MODULE','DATABASE_URL','DB_SSLMODE',
    'SECRET_KEY','ALLOWED_HOSTS','CSRF_TRUSTED_ORIGINS',
    'EMAIL_HOST','EMAIL_HOST_USER','EMAIL_HOST_PASSWORD','EMAIL_PORT',
    'EMAIL_USE_TLS','EMAIL_USE_SSL','DEFAULT_FROM_EMAIL',
    'REDIS_URL','TZ','TIME_ZONE','USE_HTTPS',
    'ATTENDANCE_AGENT_API_KEY',
)
lines = []
for k in keys:
    v = os.environ.get(k)
    if v and '\n' not in v:
        escaped = v.replace("'", "'\\''")
        lines.append(f"export {k}='{escaped}'")
with open('/app/logs/cron-runtime.env', 'w') as f:
    f.write('\n'.join(lines) + '\n')
os.chmod('/app/logs/cron-runtime.env', 0o600)
print(f'==> cron env: {len(lines)} vars saved to /app/logs/cron-runtime.env')
PY_ENV

    {
        echo "SHELL=/bin/sh"
        echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        if [ "${BACKUP_ENABLED:-true}" = "true" ]; then
            BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-0 3 * * *}"
            echo "${BACKUP_SCHEDULE} root run-cron-cmd python manage.py backup_db --cleanup --trigger cron >> /app/logs/backup.log 2>&1"
        fi
        if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then
            OPS_SCHED="${OPERATIONS_REPORT_CRON_SCHEDULE:-* * * * *}"
            echo "${OPS_SCHED} root run-cron-cmd python manage.py send_operations_report --send-email --verbose-skip >> /app/logs/operations_report.log 2>&1"
        fi
        echo ""
    } > /etc/cron.d/hr-backup
    chmod 0644 /etc/cron.d/hr-backup
    # /etc/cron.d/ يُقرأ مباشرة — لا تستخدم crontab (تفسد صيغة root)
    service cron start || cron || echo "!! cron service start failed (non-fatal)"
    if [ "${BACKUP_ENABLED:-true}" = "true" ]; then
        echo "==> Backup cron: ${BACKUP_SCHEDULE:-0 3 * * *}"
    fi
    if [ "${OPERATIONS_REPORT_CRON:-true}" = "true" ]; then
        echo "==> Operations report cron: ${OPERATIONS_REPORT_CRON_SCHEDULE:-* * * * *} (time from DB settings)"
    fi
else
    echo "==> Cron disabled (BACKUP_ENABLED=false and OPERATIONS_REPORT_CRON=false)"
fi

echo "==> Starting: $@"
exec "$@"
