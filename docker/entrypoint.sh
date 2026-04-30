#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# One-time data import: set LOAD_INITIAL_DATA=1 in env, then unset after first run.
if [ "${LOAD_INITIAL_DATA:-0}" = "1" ] && [ -f /app/data_dump.json ] && [ ! -f /app/.data_loaded ]; then
    echo "==> Loading initial data from /app/data_dump.json..."
    python manage.py loaddata /app/data_dump.json && touch /app/.data_loaded
    echo "==> Data load complete. Set LOAD_INITIAL_DATA=0 to skip on next deploy."
fi

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
