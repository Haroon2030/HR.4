"""المسار الآمن لملفات النسخ الاحتياطي المحلي."""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

ALLOWED_BACKUP_FILENAME = re.compile(
    r'^hr_backup_\d{8}_\d{6}(?:_[a-zA-Z0-9-]+)?\.(?:sql|sqlite3)\.gz$'
)


def safe_local_backup_path(filename: str) -> Path | None:
    """يُرجع مسار الملف إذا وُجد ضمن BACKUP_STORAGE_DIR واسمه مسموح."""
    raw = (filename or '').strip()
    if '/' in raw or '\\' in raw or raw.startswith('.'):
        return None
    if not ALLOWED_BACKUP_FILENAME.match(raw):
        return None
    root = Path(getattr(settings, 'BACKUP_STORAGE_DIR', '/app/backups')).resolve()
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None
