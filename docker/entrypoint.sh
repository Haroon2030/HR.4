#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

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
