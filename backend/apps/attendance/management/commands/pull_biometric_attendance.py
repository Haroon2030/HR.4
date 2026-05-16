"""
سحب كل سجلات الحضور من جهاز/أجهزة البصمة ZKTeco.

أمثلة:
  # جهاز مسجّل في النظام (بالمعرّف)
  python manage.py pull_biometric_attendance --device 1

  # بالـ IP مباشرة (uFace 800)
  python manage.py pull_biometric_attendance --ip 192.168.51.3 --port 4370

  # كل الأجهزة النشطة + تصدير Excel
  python manage.py pull_biometric_attendance --all --export-dir ./exports

  # نطاق تاريخ + استيراد لقاعدة البيانات
  python manage.py pull_biometric_attendance --device 1 --from 2026-01-01 --to 2026-05-16 --import-db

  # معاينة بدون حفظ
  python manage.py pull_biometric_attendance --device 1 --dry-run

  # إجبار الاتصال الحقيقي (تجاهل BIOMETRIC_MOCK_MODE)
  python manage.py pull_biometric_attendance --device 1 --real

  # جدولة cron يومية
  python manage.py pull_biometric_attendance --all --import-db --export-dir /app/backups/attendance
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.attendance.models import BiometricDevice
from apps.attendance.services.attendance_pull import DevicePullResult, pull_device_attendance
from apps.attendance.services.zk_client import is_mock_mode


class Command(BaseCommand):
    help = 'سحب احترافي لكل سجلات الحضور من أجهزة ZKTeco (استيراد + Excel)'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument('--device', type=int, help='معرّف الجهاز في النظام')
        target.add_argument('--all', action='store_true', help='كل الأجهزة النشطة')
        target.add_argument(
            '--ip', type=str,
            help='عنوان IP (جهاز مؤقت غير مسجّل — يتطلب --name)',
        )

        parser.add_argument('--port', type=int, default=4370, help='منفذ TCP (افتراضي 4370)')
        parser.add_argument('--comm-key', type=int, default=0, help='Comm Key')
        parser.add_argument('--name', type=str, default='', help='اسم مؤقت عند استخدام --ip')

        parser.add_argument('--from', dest='date_from', type=str, help='من تاريخ YYYY-MM-DD')
        parser.add_argument('--to', dest='date_to', type=str, help='إلى تاريخ YYYY-MM-DD')

        parser.add_argument(
            '--import-db', dest='import_db', action='store_true', default=True,
            help='استيراد إلى قاعدة البيانات (افتراضي)',
        )
        parser.add_argument(
            '--no-import-db', dest='import_db', action='store_false',
            help='تصدير/عرض فقط بدون حفظ في DB',
        )
        parser.add_argument('--dry-run', action='store_true', help='معاينة: لا يكتب في DB')
        parser.add_argument(
            '--full', action='store_true',
            help='سحب كامل (بدون فلتر زمني) — الافتراضي تزايدي: الجديد فقط',
        )
        parser.add_argument(
            '--clear-device', action='store_true',
            help='حذف السجلات من الجهاز بعد السحب (احذر!)',
        )
        parser.add_argument('--real', action='store_true', help='اتصال حقيقي حتى في وضع التجريبي')
        parser.add_argument('--mock', action='store_true', help='إجبار الوضع التجريبي')

        parser.add_argument(
            '--export', type=str, default='',
            help='مسار ملف Excel (.xlsx)',
        )
        parser.add_argument(
            '--export-dir', type=str, default='',
            help='مجلد تصدير (يُنشأ ملف باسم تلقائي لكل جهاز)',
        )

    def handle(self, *args, **options):
        date_from = self._parse_date(options.get('date_from'))
        date_to = self._parse_date(options.get('date_to'))
        if date_from and date_to and date_from > date_to:
            raise CommandError('تاريخ --from يجب أن يكون قبل --to')

        force_mock = None
        if options['mock']:
            force_mock = True
        elif options['real']:
            force_mock = False

        if is_mock_mode(force=force_mock) and not options['real']:
            self.stdout.write(self.style.WARNING(
                '⚠ وضع تجريبي (BIOMETRIC_MOCK_MODE) — استخدم --real للجهاز الفعلي'
            ))

        devices = self._resolve_devices(options)
        export_dir = Path(options['export_dir']) if options.get('export_dir') else None
        single_export = Path(options['export']) if options.get('export') else None

        results: list[DevicePullResult] = []
        for device in devices:
            export_path = None
            if single_export and len(devices) == 1:
                export_path = single_export
            elif export_dir:
                stamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
                safe_name = ''.join(c if c.isalnum() else '_' for c in device.name)[:30]
                export_path = export_dir / f'attendance_{safe_name}_{device.id}_{stamp}.xlsx'

            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n═══ {device.name} ({device.address_label}) ═══'
            ))

            incremental = not options['full'] and not (date_from or date_to)
            result = pull_device_attendance(
                device,
                date_from=date_from,
                date_to=date_to,
                import_db=options['import_db'],
                dry_run=options['dry_run'],
                clear_device=options['clear_device'],
                incremental=incremental,
                force_mock=force_mock,
                export_path=export_path,
            )
            results.append(result)
            self._print_result(result)

        self._print_totals(results)
        if any(not r.ok for r in results):
            raise CommandError('فشل سحب جهاز واحد أو أكثر')

    def _resolve_devices(self, options) -> list[BiometricDevice]:
        if options.get('ip'):
            name = options.get('name') or f"ZK-{options['ip']}"
            device, _ = BiometricDevice.objects.get_or_create(
                ip_address=options['ip'],
                port=options['port'],
                defaults={
                    'name': name,
                    'comm_key': options['comm_key'],
                    'is_active': True,
                },
            )
            if device.comm_key != options['comm_key']:
                device.comm_key = options['comm_key']
                device.save(update_fields=['comm_key', 'updated_at'])
            return [device]

        if options.get('all'):
            qs = BiometricDevice.objects.filter(is_deleted=False, is_active=True).order_by('name')
            if not qs.exists():
                raise CommandError('لا توجد أجهزة نشطة مسجّلة')
            return list(qs)

        device_id = options['device']
        try:
            return [BiometricDevice.objects.get(pk=device_id, is_deleted=False)]
        except BiometricDevice.DoesNotExist as exc:
            raise CommandError(f'الجهاز {device_id} غير موجود') from exc

    def _parse_date(self, value: str | None):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError('صيغة التاريخ: YYYY-MM-DD') from exc

    def _print_result(self, r: DevicePullResult) -> None:
        if not r.ok:
            self.stdout.write(self.style.ERROR(f'  ✗ {r.error}'))
            return

        self.stdout.write(self.style.SUCCESS('  ✓ تم الاتصال والسحب'))
        if r.serial_number:
            self.stdout.write(f'  الرقم التسلسلي: {r.serial_number}')
        if r.firmware:
            self.stdout.write(f'  الإصدار: {r.firmware}')
        self.stdout.write(f'  مستخدمون على الجهاز: {r.users_on_device}')
        self.stdout.write(f'  سجلات على الجهاز: {r.punches_fetched}')
        self.stdout.write(f'  بعد التصفية: {r.punches_after_filter}')
        if r.punches_new:
            self.stdout.write(f'  جديد للاستيراد: {r.punches_new}')
        if r.imported:
            self.stdout.write(self.style.SUCCESS(f'  مستوردة للنظام: {r.imported}'))
        if r.skipped_duplicate:
            self.stdout.write(f'  مكررة (تخطي): {r.skipped_duplicate}')
        if r.skipped_time_filter:
            self.stdout.write(f'  قديمة (تخطي زمني): {r.skipped_time_filter}')
        if r.unmapped_users:
            self.stdout.write(self.style.WARNING(
                f'  مستخدمون بلا ربط HR: {r.unmapped_users} — ربطهم من صفحة أجهزة البصمة'
            ))
        if r.export_path:
            self.stdout.write(self.style.SUCCESS(f'  Excel: {r.export_path}'))

        if r.punches:
            self.stdout.write('\n  آخر 5 سجلات:')
            self.stdout.write(
                f"  {'التاريخ':<12} {'الوقت':<10} {'رقم':<6} {'الاسم':<18} {'الحركة':<10} {'HR':<16}"
            )
            for p in r.punches[-5:]:
                local = timezone.localtime(p.punched_at)
                self.stdout.write(
                    f"  {local.strftime('%Y-%m-%d'):<12} "
                    f"{local.strftime('%H:%M:%S'):<10} "
                    f"{p.device_user_id:<6} "
                    f"{(p.device_user_name or '—')[:18]:<18} "
                    f"{p.punch_type_label[:10]:<10} "
                    f"{(p.employee_name or 'غير مربوط')[:16]:<16}"
                )

    def _print_totals(self, results: list[DevicePullResult]) -> None:
        ok = [r for r in results if r.ok]
        if len(results) <= 1:
            return
        self.stdout.write(self.style.MIGRATE_HEADING('\n═══ الإجمالي ═══'))
        self.stdout.write(f'  أجهزة: {len(results)} | ناجحة: {len(ok)}')
        self.stdout.write(
            f'  سجلات: {sum(r.punches_after_filter for r in ok)} | '
            f'مستوردة: {sum(r.imported for r in ok)}'
        )
