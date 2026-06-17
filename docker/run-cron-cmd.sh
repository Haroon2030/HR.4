#!/bin/sh
# يُحمّل متغيرات حاوية Dokploy — cron لا يرثها افتراضياً.
set -a
if [ -f /app/logs/cron-runtime.env ]; then
    # shellcheck disable=SC1091
    . /app/logs/cron-runtime.env
fi
set +a
cd /app || exit 1
exec "$@"
