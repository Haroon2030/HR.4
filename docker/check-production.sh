#!/bin/sh
# فحص شامل لبيانات الإنتاج — من طرفية Docker
set -e
cd /app
exec python manage.py check_production_data "$@"
