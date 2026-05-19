#!/bin/sh
# فحص سريع من طرفية Docker (Dokploy) — يعمل من أي مجلد داخل الحاوية
set -e
cd /app
exec python manage.py check_attendance_production "$@"
