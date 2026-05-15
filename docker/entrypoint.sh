#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

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
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '526400')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')

if User.objects.filter(username=username).exists():
    print(f"Superuser '{username}' already exists \u2014 leaving it untouched.")
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' created.")
PYEOF

echo "==> Fixing swapped code/name records (idempotent)..."
python manage.py fix_swapped_code_name || echo "!! fix_swapped_code_name failed (non-fatal)"

# ─── Setup daily automatic database backup via cron ─────────────────────────
# Backup runs every day at 03:00 UTC and uploads to Cloudflare R2.
# Disable by setting BACKUP_ENABLED=false in environment.
if [ "${BACKUP_ENABLED:-true}" = "true" ]; then
    echo "==> Setting up daily database backup cron job (03:00 UTC) ..."
    BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-0 3 * * *}"
    mkdir -p /app/backups /app/logs
    # Build a cron file that runs the Django backup command in the app environment.
    cat > /etc/cron.d/hr-backup <<CRON_EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${BACKUP_SCHEDULE} root cd /app && python manage.py backup_db --cleanup --trigger cron >> /app/logs/backup.log 2>&1
CRON_EOF
    chmod 0644 /etc/cron.d/hr-backup
    crontab /etc/cron.d/hr-backup
    service cron start || cron || echo "!! cron service start failed (non-fatal)"
    echo "==> Cron schedule: ${BACKUP_SCHEDULE}"
else
    echo "==> Auto backup disabled (BACKUP_ENABLED=false)"
fi

echo "==> Starting: $@"
exec "$@"
