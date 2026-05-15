"""
أمر النسخ الاحتياطي لقاعدة البيانات
========================================
يدعم:
  - PostgreSQL (pg_dump)
  - SQLite (نسخ ملف)

يحفظ النسخة الاحتياطية في:
  - محلياً: /app/backups/
  - Cloudflare R2: HR/backups/<year>/<month>/

الاستخدام:
  python manage.py backup_db                  # نسخ احتياطي عادي
  python manage.py backup_db --label "before-migration"  # مع تسمية
  python manage.py backup_db --local-only     # محلي فقط (بدون R2)
  python manage.py backup_db --cleanup        # حذف النسخ القديمة (الإبقاء على 30 يوم)
"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


DEFAULT_BACKUP_DIR = Path('/app/backups')
LOCAL_RETENTION_DAYS = 7      # احتفظ بآخر 7 أيام محلياً
R2_RETENTION_DAYS = 30        # احتفظ بآخر 30 يوم على R2
R2_BACKUP_PREFIX = 'HR/backups'


class Command(BaseCommand):
    help = 'إنشاء نسخة احتياطية من قاعدة البيانات (محلياً وعلى Cloudflare R2)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--label',
            type=str,
            default='',
            help='تسمية مختصرة للنسخة (مثل: before-migration)',
        )
        parser.add_argument(
            '--local-only',
            action='store_true',
            help='حفظ محلي فقط بدون رفع على R2',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='حذف النسخ القديمة بعد إنشاء النسخة الجديدة',
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=str(DEFAULT_BACKUP_DIR),
            help=f'مجلد حفظ النسخة (افتراضي: {DEFAULT_BACKUP_DIR})',
        )

    def handle(self, *args, **opts):
        backup_dir = Path(opts['output_dir'])
        backup_dir.mkdir(parents=True, exist_ok=True)

        label = self._sanitize_label(opts['label'])
        local_only = opts['local_only']
        do_cleanup = opts['cleanup']

        # توليد اسم الملف
        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        suffix = f'_{label}' if label else ''
        db_engine = settings.DATABASES['default']['ENGINE']

        if 'postgresql' in db_engine:
            filename = f'hr_backup_{ts}{suffix}.sql.gz'
            local_path = backup_dir / filename
            self._dump_postgres(local_path)
        elif 'sqlite' in db_engine:
            filename = f'hr_backup_{ts}{suffix}.sqlite3.gz'
            local_path = backup_dir / filename
            self._dump_sqlite(local_path)
        else:
            raise CommandError(f'محرك قاعدة البيانات غير مدعوم: {db_engine}')

        size_mb = local_path.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'✓ تم إنشاء النسخة الاحتياطية محلياً: {local_path} ({size_mb:.2f} MB)'
        ))

        # رفع لـ R2
        if not local_only and getattr(settings, 'USE_R2', False):
            try:
                r2_key = self._upload_to_r2(local_path, filename)
                self.stdout.write(self.style.SUCCESS(
                    f'✓ تم رفع النسخة إلى Cloudflare R2: {r2_key}'
                ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'⚠ فشل رفع النسخة إلى R2: {e}\n'
                    f'  النسخة المحلية موجودة في: {local_path}'
                ))
        elif not local_only:
            self.stdout.write(self.style.WARNING(
                '⚠ USE_R2 غير مفعّل — تم الحفظ محلياً فقط'
            ))

        # تنظيف النسخ القديمة
        if do_cleanup:
            self._cleanup_local(backup_dir)

        self.stdout.write(self.style.SUCCESS('━' * 60))
        self.stdout.write(self.style.SUCCESS(
            f'✓ اكتملت النسخة الاحتياطية: {filename}'
        ))

    # ──────────────────────────────────────────────────────────────────
    # PostgreSQL dump
    # ──────────────────────────────────────────────────────────────────
    def _dump_postgres(self, output_path: Path):
        """ينفذ pg_dump ويضغط الناتج بـ gzip."""
        db = settings.DATABASES['default']
        # دعم DATABASE_URL أو مفاتيح منفصلة
        url = os.environ.get('DATABASE_URL', '')
        if url:
            parsed = urlparse(url)
            env = {
                **os.environ,
                'PGPASSWORD': parsed.password or db.get('PASSWORD', ''),
            }
            cmd = [
                'pg_dump',
                '-h', parsed.hostname or db.get('HOST', 'localhost'),
                '-p', str(parsed.port or db.get('PORT') or 5432),
                '-U', parsed.username or db.get('USER', 'postgres'),
                '-d', (parsed.path.lstrip('/') if parsed.path else db.get('NAME', '')),
                '--no-owner',
                '--no-acl',
                '--clean',
                '--if-exists',
            ]
        else:
            env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD', '')}
            cmd = [
                'pg_dump',
                '-h', db.get('HOST', 'localhost'),
                '-p', str(db.get('PORT') or 5432),
                '-U', db.get('USER', 'postgres'),
                '-d', db.get('NAME', ''),
                '--no-owner',
                '--no-acl',
                '--clean',
                '--if-exists',
            ]

        self.stdout.write(f'تشغيل pg_dump → {output_path.name} ...')

        try:
            with gzip.open(output_path, 'wb') as gz:
                proc = subprocess.run(
                    cmd, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                gz.write(proc.stdout)
        except FileNotFoundError:
            raise CommandError(
                'pg_dump غير موجود. ثبّت postgresql-client في الحاوية.'
            )
        except subprocess.CalledProcessError as e:
            output_path.unlink(missing_ok=True)
            err = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise CommandError(f'فشل pg_dump:\n{err}')

    # ──────────────────────────────────────────────────────────────────
    # SQLite dump
    # ──────────────────────────────────────────────────────────────────
    def _dump_sqlite(self, output_path: Path):
        """ينسخ ملف SQLite ويضغطه."""
        db = settings.DATABASES['default']
        db_file = Path(db['NAME'])
        if not db_file.exists():
            raise CommandError(f'ملف قاعدة البيانات غير موجود: {db_file}')
        with open(db_file, 'rb') as src, gzip.open(output_path, 'wb') as gz:
            shutil.copyfileobj(src, gz)

    # ──────────────────────────────────────────────────────────────────
    # رفع لـ Cloudflare R2
    # ──────────────────────────────────────────────────────────────────
    def _upload_to_r2(self, local_path: Path, filename: str) -> str:
        """يرفع النسخة الاحتياطية إلى R2 ويرجع الـ key."""
        from apps.core.storages import HRMediaStorage

        now = timezone.now()
        key = f'{R2_BACKUP_PREFIX}/{now.year}/{now.month:02d}/{filename}'
        storage = HRMediaStorage()
        with open(local_path, 'rb') as f:
            # نتجاوز get_available_name لتثبيت اسم الملف بالضبط
            content_file = ContentFile(f.read())
            saved_name = storage._save(key, content_file)
        return saved_name

    # ──────────────────────────────────────────────────────────────────
    # تنظيف النسخ المحلية القديمة
    # ──────────────────────────────────────────────────────────────────
    def _cleanup_local(self, backup_dir: Path):
        """يحذف النسخ المحلية الأقدم من LOCAL_RETENTION_DAYS."""
        cutoff = timezone.now() - timedelta(days=LOCAL_RETENTION_DAYS)
        cutoff_ts = cutoff.timestamp()
        removed = 0
        for f in backup_dir.glob('hr_backup_*'):
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    removed += 1
            except OSError:
                continue
        if removed:
            self.stdout.write(self.style.SUCCESS(
                f'✓ حُذفت {removed} نسخة محلية أقدم من {LOCAL_RETENTION_DAYS} يوم'
            ))

    # ──────────────────────────────────────────────────────────────────
    # أدوات مساعدة
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _sanitize_label(label: str) -> str:
        """تنظيف التسمية: حروف وأرقام و - و _ فقط."""
        if not label:
            return ''
        return re.sub(r'[^a-zA-Z0-9_-]+', '-', label).strip('-')[:40]


# استيراد متأخر لتجنب مشاكل دائرية
from django.core.files.base import ContentFile  # noqa: E402
