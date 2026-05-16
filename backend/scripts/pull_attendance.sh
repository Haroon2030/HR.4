#!/usr/bin/env bash
# سحب حضور من كل أجهزة البصمة + Excel — للجدولة (cron)
set -euo pipefail
cd "$(dirname "$0")/.."
export DJANGO_ENV="${DJANGO_ENV:-production}"

EXPORT_DIR="${ATTENDANCE_EXPORT_DIR:-/app/backups/attendance}"
mkdir -p "$EXPORT_DIR"

python manage.py pull_biometric_attendance \
  --all \
  --real \
  --import-db \
  --export-dir "$EXPORT_DIR"

echo "Done: $EXPORT_DIR"
