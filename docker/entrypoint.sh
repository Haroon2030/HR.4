#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# ─── Auto-load initial data on first deploy (idempotent via marker file) ──────
# Uses the custom `import_initial_data` command which:
#   - disconnects UserProfile auto-create signals during loaddata (avoids PK conflicts)
#   - flushes the DB first (clears any partial state from previous failed deploys)
#   - writes a marker file ONLY on full success → safe automatic retry on failure
if [ -f /app/data_dump.json ]; then
    python manage.py import_initial_data /app/data_dump.json \
        --flush \
        --marker /app/.data_loaded \
        || echo "!! import_initial_data failed — will retry on next deploy"
fi

# ─── Ensure superuser exists (created ONCE on first deploy, never overwritten) ─
# If 'admin' already exists, we leave it untouched. Password changes, role edits,
# and email updates done via the UI are PRESERVED across redeploys.
# To force a reset: delete the row in auth_user via Adminer, then redeploy.
# ─── One-time wipe of legacy local file paths after switching to R2 ───────────
# Runs ONCE per container volume (marker file). Safe to keep in entrypoint:
# subsequent deploys see the marker and skip.
if [ ! -f /app/.file_paths_cleared ]; then
    echo "==> Clearing legacy file paths in DB (one-time, after R2 switch)..."
    if python manage.py clear_file_paths --apply; then
        touch /app/.file_paths_cleared
        echo "==> Done. Marker /app/.file_paths_cleared written."
    else
        echo "!! clear_file_paths failed — will retry on next deploy"
    fi
fi

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

echo "==> Starting: $@"
exec "$@"
