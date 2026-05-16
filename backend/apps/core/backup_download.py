"""المسار الآمن لملفات النسخ الاحتياطي المحلي وتحميلها."""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse

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


def stream_database_backup_file(*, filename: str, r2_key: str = '') -> FileResponse | None:
    """
    يُرجع FileResponse للملف المحلي أو من R2، أو None إن لم يتوفر الملف.
    """
    local_path = safe_local_backup_path(filename)
    if local_path is not None:
        fh = local_path.open('rb')
        resp = FileResponse(fh, as_attachment=True, filename=filename)
        resp['Content-Type'] = 'application/gzip'
        return resp

    key = (r2_key or '').strip()
    if not key.startswith('HR/backups/'):
        return None

    from apps.core.storages import HRMediaStorage

    storage = HRMediaStorage()
    with storage.open(key, 'rb') as remote:
        payload = remote.read()
    blob = BytesIO(payload)
    resp = FileResponse(blob, as_attachment=True, filename=filename)
    resp['Content-Type'] = 'application/gzip'
    return resp


def backup_download_error_response(message: str, *, status: int = 400) -> HttpResponse:
    return HttpResponse(message, status=status, content_type='text/plain; charset=utf-8')
