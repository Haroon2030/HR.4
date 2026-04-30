#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# ─── Auto-load initial data on first deploy (idempotent via marker file) ──────
# Marker is written to a persistent location only after a FULL successful load.
# If marker is missing (first deploy or previous attempt failed), we flush and reload.
MARKER_FILE="/app/.data_loaded"
if [ -f /app/data_dump.json ]; then
    if [ ! -f "$MARKER_FILE" ]; then
        echo "==> No data marker found — performing full data load ..."
        # Flush wipes all rows but keeps schema (fixes partial imports from previous failed runs).
        python manage.py flush --noinput

        echo "==> Loading main data from /app/data_dump.json ..."
        if python manage.py loaddata /app/data_dump.json; then
            MAIN_OK=1
        else
            MAIN_OK=0
            echo "!! main loaddata failed"
        fi

        PROFILES_OK=1
        # UserProfile is auto-created by post_save signal on User → wipe & reload to restore real data.
        if [ -f /app/data_profiles.json ]; then
            echo "==> Restoring user profiles ..."
            python manage.py shell -c "from apps.core.models import UserProfile; UserProfile.objects.all().delete()" || true
            if ! python manage.py loaddata /app/data_profiles.json; then
                PROFILES_OK=0
                echo "!! profiles loaddata failed"
            fi
        fi

        if [ "$MAIN_OK" = "1" ] && [ "$PROFILES_OK" = "1" ]; then
            touch "$MARKER_FILE"
            echo "==> Data load complete. Marker written to $MARKER_FILE."
        else
            echo "!! Data load incomplete — marker NOT written. Will retry on next deploy."
        fi
    else
        echo "==> Data marker present — skipping loaddata."
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
