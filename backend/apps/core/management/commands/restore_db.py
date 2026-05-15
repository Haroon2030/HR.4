"""
أمر استرجاع قاعدة البيانات من نسخة احتياطية
================================================
يدعم:
  - PostgreSQL (psql)
  - SQLite (نسخ ملف)

مصادر النسخة:
  - ملف محلي: /app/backups/<filename>
  - من R2: HR/backups/<year>/<month>/<filename>

الاستخدام:
  python manage.py restore_db --list                       # عرض النسخ المتاحة
  python manage.py restore_db --file backup.sql.gz         # استرجاع من ملف محلي
  python manage.py restore_db --r2-key HR/backups/...      # استرجاع من R2
  python manage.py restore_db --latest                     # استرجاع آخر نسخة من R2
  python manage.py restore_db --latest --confirm           # تخطي تأكيد المستخدم

⚠️ تحذير: الاسترجاع يستبدل قاعدة البيانات الحالية بالكامل!
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


DEFAULT_BACKUP_DIR = Path('/app/backups')
R2_BACKUP_PREFIX = 'HR/backups'


class Command(BaseCommand):
    help = 'استرجاع قاعدة البيانات من نسخة احتياطية (محلية أو من R2)'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='ملف نسخة احتياطية محلي')
        parser.add_argument('--r2-key', type=str, help='مفتاح النسخة على R2')
        parser.add_argument('--latest', action='store_true', help='استرجاع أحدث نسخة من R2')
        parser.add_argument('--list', action='store_true', help='عرض النسخ المتاحة')
        parser.add_argument('--confirm', action='store_true', help='تخطي تأكيد المستخدم')
        parser.add_argument(
            '--backup-dir',
            type=str,
            default=str(DEFAULT_BACKUP_DIR),
            help=f'مجلد النسخ الاحتياطية المحلية (افتراضي: {DEFAULT_BACKUP_DIR})',
        )

    def handle(self, *args, **opts):
        backup_dir = Path(opts['backup_dir'])
        backup_dir.mkdir(parents=True, exist_ok=True)

        if opts['list']:
            self._list_backups(backup_dir)
            return

        # تحديد مصدر النسخة
        local_file = None
        if opts['file']:
            local_file = Path(opts['file'])
            if not local_file.is_absolute():
                local_file = backup_dir / local_file.name
            if not local_file.exists():
                raise CommandError(f'الملف غير موجود: {local_file}')
        elif opts['r2_key']:
            local_file = self._download_from_r2(opts['r2_key'], backup_dir)
        elif opts['latest']:
            r2_key = self._find_latest_r2()
            if not r2_key:
                raise CommandError('لا توجد نسخ احتياطية على R2.')
            local_file = self._download_from_r2(r2_key, backup_dir)
        else:
            raise CommandError(
                'حدد مصدر النسخة: --file أو --r2-key أو --latest\n'
                'أو استخدم --list لعرض المتاح.'
            )

        # تأكيد المستخدم
        if not opts['confirm']:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  تحذير: الاسترجاع سيستبدل جميع البيانات الحالية!'
            ))
            self.stdout.write(f'  الملف: {local_file}')
            self.stdout.write(f'  الحجم: {local_file.stat().st_size / 1024:.2f} KB')
            try:
                answer = input('\nهل أنت متأكد؟ اكتب "نعم" أو "yes" للمتابعة: ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write(self.style.ERROR('\nأُلغي.'))
                return
            if answer not in ('نعم', 'yes', 'y'):
                self.stdout.write(self.style.ERROR('أُلغي.'))
                return

        # أغلق الاتصالات قبل الاسترجاع
        for conn in connections.all():
            conn.close()

        # تنفيذ الاسترجاع
        db_engine = settings.DATABASES['default']['ENGINE']
        if 'postgresql' in db_engine:
            self._restore_postgres(local_file)
        elif 'sqlite' in db_engine:
            self._restore_sqlite(local_file)
        else:
            raise CommandError(f'محرك قاعدة البيانات غير مدعوم: {db_engine}')

        self.stdout.write(self.style.SUCCESS('━' * 60))
        self.stdout.write(self.style.SUCCESS('✓ تم الاسترجاع بنجاح!'))
        self.stdout.write(self.style.WARNING(
            '  أعد تشغيل التطبيق إذا لم تظهر البيانات فوراً.'
        ))

    # ──────────────────────────────────────────────────────────────────
    # PostgreSQL restore
    # ──────────────────────────────────────────────────────────────────
    def _restore_postgres(self, gz_file: Path):
        from urllib.parse import unquote
        db = settings.DATABASES['default']
        url = os.environ.get('DATABASE_URL', '')
        if url:
            parsed = urlparse(url)
            user = unquote(parsed.username or '') or db.get('USER', 'postgres')
            password = unquote(parsed.password or '') or db.get('PASSWORD', '')
            env = {**os.environ, 'PGPASSWORD': password}
            cmd = [
                'psql',
                '-h', parsed.hostname or db.get('HOST', 'localhost'),
                '-p', str(parsed.port or db.get('PORT') or 5432),
                '-U', user,
                '-d', (parsed.path.lstrip('/') if parsed.path else db.get('NAME', '')),
                '-v', 'ON_ERROR_STOP=1',
                '--single-transaction',
            ]
        else:
            env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD', '')}
            cmd = [
                'psql',
                '-h', db.get('HOST', 'localhost'),
                '-p', str(db.get('PORT') or 5432),
                '-U', db.get('USER', 'postgres'),
                '-d', db.get('NAME', ''),
                '-v', 'ON_ERROR_STOP=1',
                '--single-transaction',
            ]

        self.stdout.write('استرجاع PostgreSQL ...')
        try:
            with gzip.open(gz_file, 'rb') as gz:
                proc = subprocess.run(
                    cmd, env=env, input=gz.read(),
                    check=True, capture_output=True
                )
            if proc.stderr:
                msg = proc.stderr.decode('utf-8', errors='ignore')
                if msg.strip():
                    self.stdout.write(msg)
        except FileNotFoundError:
            raise CommandError('psql غير مثبت في الحاوية.')
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise CommandError(f'فشل psql:\n{err}')

    # ──────────────────────────────────────────────────────────────────
    # SQLite restore
    # ──────────────────────────────────────────────────────────────────
    def _restore_sqlite(self, gz_file: Path):
        db_file = Path(settings.DATABASES['default']['NAME'])
        backup_of_current = db_file.with_suffix(
            f'.before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.bak'
        )

        if db_file.exists():
            shutil.copy2(db_file, backup_of_current)
            self.stdout.write(f'حُفظت نسخة من الحالية: {backup_of_current.name}')

        with gzip.open(gz_file, 'rb') as gz, open(db_file, 'wb') as out:
            shutil.copyfileobj(gz, out)

    # ──────────────────────────────────────────────────────────────────
    # R2 utilities
    # ──────────────────────────────────────────────────────────────────
    def _download_from_r2(self, r2_key: str, target_dir: Path) -> Path:
        from apps.core.storages import HRMediaStorage
        storage = HRMediaStorage()
        if not storage.exists(r2_key):
            # storage.exists يرجع False دائماً، نحاول الفتح مباشرة
            pass
        try:
            f = storage._open(r2_key, 'rb')
        except Exception as e:
            raise CommandError(f'تعذّر فتح الملف على R2 ({r2_key}): {e}')
        local_path = target_dir / Path(r2_key).name
        with open(local_path, 'wb') as out:
            shutil.copyfileobj(f, out)
        f.close()
        self.stdout.write(self.style.SUCCESS(
            f'✓ نُزّلت النسخة من R2: {local_path}'
        ))
        return local_path

    def _find_latest_r2(self) -> str | None:
        from apps.core.storages import HRMediaStorage
        storage = HRMediaStorage()
        # نمشي على بضعة شهور أخيرة
        now = datetime.now()
        candidates = []
        for year_offset, month_offset in [(0, 0), (0, -1), (-1, 0)]:
            y = now.year + year_offset
            m = now.month + month_offset
            if m <= 0:
                m += 12
                y -= 1
            prefix = f'{R2_BACKUP_PREFIX}/{y}/{m:02d}/'
            try:
                dirs, files = storage.listdir(prefix)
            except Exception:
                continue
            for fn in files:
                candidates.append(f'{prefix}{fn}')
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0]

    def _list_backups(self, backup_dir: Path):
        # محلي
        self.stdout.write(self.style.SUCCESS('━' * 60))
        self.stdout.write(self.style.SUCCESS('📁 النسخ المحلية:'))
        self.stdout.write(self.style.SUCCESS('━' * 60))
        local_files = sorted(backup_dir.glob('hr_backup_*'), reverse=True)
        if not local_files:
            self.stdout.write('  (لا توجد نسخ محلية)')
        for f in local_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            self.stdout.write(f'  {f.name}  ({size_mb:.2f} MB, {mtime})')

        # R2
        self.stdout.write(self.style.SUCCESS('\n━' * 60))
        self.stdout.write(self.style.SUCCESS('☁️  النسخ على Cloudflare R2:'))
        self.stdout.write(self.style.SUCCESS('━' * 60))
        if not getattr(settings, 'USE_R2', False):
            self.stdout.write('  (R2 غير مفعّل)')
            return
        try:
            from apps.core.storages import HRMediaStorage
            storage = HRMediaStorage()
            now = datetime.now()
            found = []
            for offset in range(6):  # آخر 6 شهور
                m = now.month - offset
                y = now.year
                while m <= 0:
                    m += 12
                    y -= 1
                prefix = f'{R2_BACKUP_PREFIX}/{y}/{m:02d}/'
                try:
                    _, files = storage.listdir(prefix)
                except Exception:
                    continue
                for fn in files:
                    found.append(f'{prefix}{fn}')
            if not found:
                self.stdout.write('  (لا توجد نسخ على R2)')
            for key in sorted(found, reverse=True):
                self.stdout.write(f'  {key}')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  تعذّر الاتصال بـ R2: {e}'))
