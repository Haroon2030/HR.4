"""
أمر النسخ الاحتياطي لقاعدة البيانات
========================================
يدعم:
  - PostgreSQL (pg_dump)
  - SQLite (نسخ ملف)

يحفظ النسخة الاحتياطية في:
  - محلياً: /app/backups/ (أو BACKUP_STORAGE_DIR)
  - Cloudflare R2: HR/backups/<year>/<month>/

يكتب سجلًا في DatabaseBackupLog ويمكن إرسال بريد عند النجاح/الفشل.

الاستخدام:
  python manage.py backup_db                  # نسخ احتياطي عادي
  python manage.py backup_db --label "before-migration"  # مع تسمية
  python manage.py backup_db --local-only     # محلي فقط (بدون R2)
  python manage.py backup_db --cleanup        # حذف النسخ القديمة محلياً (7 أيام)
  python manage.py backup_db --trigger cron   # تمييز السجل كجدولة (cron)
  python manage.py backup_db --no-notify      # عدم إرسال بريد لهذه المحاولة
"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import DatabaseBackupLog

DEFAULT_BACKUP_DIR = Path(getattr(settings, 'BACKUP_STORAGE_DIR', None) or '/app/backups')
LOCAL_RETENTION_DAYS = 7
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
        parser.add_argument(
            '--trigger',
            type=str,
            choices=['manual', 'cron'],
            default='manual',
            help='مصدر التشغيل (للسجل والتقارير)',
        )
        parser.add_argument(
            '--no-notify',
            action='store_true',
            help='عدم إرسال بريد إشعار لهذه المحاولة',
        )

    def handle(self, *args, **opts):
        backup_dir = Path(opts['output_dir'])
        backup_dir.mkdir(parents=True, exist_ok=True)

        label = self._sanitize_label(opts['label'])
        local_only = opts['local_only']
        do_cleanup = opts['cleanup']
        trigger_opt = opts['trigger']
        do_notify = not opts['no_notify']

        trigger = (
            DatabaseBackupLog.Trigger.CRON
            if trigger_opt == 'cron'
            else DatabaseBackupLog.Trigger.MANUAL
        )

        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        suffix = f'_{label}' if label else ''
        db_engine = settings.DATABASES['default']['ENGINE']
        filename = (
            f'hr_backup_{ts}{suffix}.sql.gz'
            if 'postgresql' in db_engine
            else f'hr_backup_{ts}{suffix}.sqlite3.gz'
        )
        local_path = backup_dir / filename

        r2_key_out = ''
        r2_error_out = ''

        try:
            if 'postgresql' in db_engine:
                self._dump_postgres(local_path)
            elif 'sqlite' in db_engine:
                self._dump_sqlite(local_path)
            else:
                raise CommandError(f'محرك قاعدة البيانات غير مدعوم: {db_engine}')

            size_bytes = local_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f'✓ تم إنشاء النسخة الاحتياطية محلياً: {local_path} ({size_mb:.2f} MB)'
            ))

            if not local_only and getattr(settings, 'USE_R2', False):
                try:
                    r2_key_out = self._upload_to_r2(local_path, filename)
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ تم رفع النسخة إلى Cloudflare R2: {r2_key_out}'
                    ))
                except Exception as e:
                    r2_error_out = str(e)
                    self.stdout.write(self.style.WARNING(
                        f'⚠ فشل رفع النسخة إلى R2: {e}\n'
                        f'  النسخة المحلية موجودة في: {local_path}'
                    ))
            elif not local_only:
                self.stdout.write(self.style.WARNING(
                    '⚠ USE_R2 غير مفعّل — تم الحفظ محلياً فقط'
                ))

            if do_cleanup:
                self._cleanup_local(backup_dir)

            status = (
                DatabaseBackupLog.Status.PARTIAL
                if r2_error_out and not local_only and getattr(settings, 'USE_R2', False)
                else DatabaseBackupLog.Status.SUCCESS
            )
            DatabaseBackupLog.objects.create(
                trigger=trigger,
                status=status,
                filename=filename,
                size_bytes=size_bytes,
                r2_key=r2_key_out,
                dump_error='',
                r2_error=r2_error_out,
            )

            if do_notify:
                self._maybe_send_mail_ok(
                    filename=filename,
                    size_mb=size_mb,
                    r2_key=r2_key_out,
                    r2_error=r2_error_out,
                    trigger_opt=trigger_opt,
                    local_only=local_only,
                )

            self.stdout.write(self.style.SUCCESS('━' * 60))
            self.stdout.write(self.style.SUCCESS(
                f'✓ اكتملت النسخة الاحتياطية: {filename}'
            ))

        except Exception as exc:
            err_text = str(exc)
            if isinstance(exc, CommandError):
                err_text = err_text.strip() or repr(exc)

            DatabaseBackupLog.objects.create(
                trigger=trigger,
                status=DatabaseBackupLog.Status.FAILED,
                filename=filename,
                size_bytes=0,
                r2_key='',
                dump_error=err_text,
                r2_error='',
            )

            if do_notify:
                from apps.core.services.backup_notify import send_backup_notification

                send_backup_notification(
                    success=False,
                    subject_hint=f'[HR] فشل النسخ الاحتياطي — {filename}',
                    body_lines=[
                        'فشلت عملية النسخ الاحتياطي لقاعدة البيانات.',
                        f'الملف المخطط: {filename}',
                        f'المصدر: {"مجدول (cron)" if trigger_opt == "cron" else "يدوي"}',
                        '',
                        'تفاصيل الخطأ:',
                        err_text,
                    ],
                )

            if isinstance(exc, CommandError):
                raise
            raise CommandError(err_text) from exc

    def _maybe_send_mail_ok(
        self,
        *,
        filename: str,
        size_mb: float,
        r2_key: str,
        r2_error: str,
        trigger_opt: str,
        local_only: bool,
    ):
        from apps.core.services.backup_notify import send_backup_notification

        lines = [
            'اكتملت عملية النسخ الاحتياطي لقاعدة البيانات.',
            f'الملف: {filename}',
            f'الحجم التقريبي: {size_mb:.2f} MB',
            f'المصدر: {"مجدول (cron)" if trigger_opt == "cron" else "يدوي"}',
        ]
        if local_only or not getattr(settings, 'USE_R2', False):
            lines.append('التخزين: محلي فقط.')
        elif r2_key:
            lines.append(f'تم الرفع إلى R2: {r2_key}')
        if r2_error:
            lines.extend(['', 'تحذير: فشل رفع النسخة إلى Cloudflare R2:', r2_error])

        partial = bool(r2_error)
        subject = (
            f'[HR] تنبيه النسخ الاحتياطي — تحذير R2 ({filename})'
            if partial
            else f'[HR] النسخ الاحتياطي نجح — {filename}'
        )

        send_backup_notification(
            success=True,
            subject_hint=subject,
            body_lines=lines,
        )

    def _dump_postgres(self, output_path: Path):
        """ينفذ pg_dump ويضغط الناتج بـ gzip."""
        from urllib.parse import unquote

        db = settings.DATABASES['default']
        url = os.environ.get('DATABASE_URL', '')
        if url:
            parsed = urlparse(url)
            user = unquote(parsed.username or '') or db.get('USER', 'postgres')
            password = unquote(parsed.password or '') or db.get('PASSWORD', '')
            env = {**os.environ, 'PGPASSWORD': password}
            cmd = [
                'pg_dump',
                '-h', parsed.hostname or db.get('HOST', 'localhost'),
                '-p', str(parsed.port or db.get('PORT') or 5432),
                '-U', user,
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

    def _dump_sqlite(self, output_path: Path):
        """ينسخ ملف SQLite ويضغطه."""
        db = settings.DATABASES['default']
        db_file = Path(db['NAME'])
        if not db_file.exists():
            raise CommandError(f'ملف قاعدة البيانات غير موجود: {db_file}')
        with open(db_file, 'rb') as src, gzip.open(output_path, 'wb') as gz:
            shutil.copyfileobj(src, gz)

    def _upload_to_r2(self, local_path: Path, filename: str) -> str:
        """يرفع النسخة الاحتياطية إلى R2 ويرجع الـ key."""
        from apps.core.storages import HRMediaStorage

        now = timezone.now()
        key = f'{R2_BACKUP_PREFIX}/{now.year}/{now.month:02d}/{filename}'
        storage = HRMediaStorage()
        with open(local_path, 'rb') as f:
            content_file = ContentFile(f.read())
            saved_name = storage._save(key, content_file)
        return saved_name

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

    @staticmethod
    def _sanitize_label(label: str) -> str:
        """تنظيف التسمية: حروف وأرقام و - و _ فقط."""
        if not label:
            return ''
        return re.sub(r'[^a-zA-Z0-9_-]+', '-', label).strip('-')[:40]
