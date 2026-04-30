#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# ─── Auto-load initial data on first deploy (idempotent) ───────────────────────
# Loads /app/data_dump.json only if the database is "empty" (no employees yet).
# Subsequent deploys skip automatically — no env var needed.
if [ -f /app/data_dump.json ]; then
    echo "==> Checking if initial data needs to be loaded..."
    NEEDS_LOAD=$(python manage.py shell -c "
from django.apps import apps
from django.db.utils import OperationalError
try:
    Employee = apps.get_model('employees', 'Employee')
    print('1' if Employee.objects.count() == 0 else '0')
except Exception:
    print('1')
" 2>/dev/null | tail -1)

    if [ "$NEEDS_LOAD" = "1" ]; then
        echo "==> Database has no employees. Resetting and loading data from /app/data_dump.json ..."
        # Flush wipes all rows but keeps schema (fixes partial imports from previous failed runs).
        python manage.py flush --noinput
        python manage.py loaddata /app/data_dump.json || echo "!! loaddata failed (check above for details)"
    else
        echo "==> Database already has data — skipping loaddata."
    fi
fi

# ─── Ensure superuser exists (admin / 526400) ──────────────────────────────────
echo "==> Ensuring superuser '${DJANGO_SUPERUSER_USERNAME:-admin}' exists..."
python manage.py shell <<PYEOF
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '526400')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')

user, created = User.objects.get_or_create(
    username=username,
    defaults={'email': email, 'is_staff': True, 'is_superuser': True},
)
user.is_staff = True
user.is_superuser = True
if not user.email:
    user.email = email
user.set_password(password)
user.save()
print(f"Superuser '{username}' {'created' if created else 'updated'}.")
PYEOF

echo "==> Starting: $@"
exec "$@"
