"""
فحص إنتاج البصمة — اتصال قاعدة البيانات، الجداول، الربط، وحفظ السجلات.

الاستخدام على السيرفر (داخل حاوية Docker):
  python manage.py check_attendance_production
  python manage.py check_attendance_production --details
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


@dataclass
class CheckResult:
    ok: bool
    title: str
    detail: str = ''
    hint: str = ''


@dataclass
class Report:
    checks: list[CheckResult] = field(default_factory=list)
    warnings: int = 0
    failures: int = 0
    deploy_mode: bool = False

    def add(self, check: CheckResult, *, critical: bool = True) -> None:
        """في وضع --deploy: الفحوصات غير الحرجة تُحوَّل لتحذيرات ولا توقف النشر."""
        if self.deploy_mode and critical is False and not check.ok:
            title = check.title
            if title.startswith('❌ '):
                title = '⚠ ' + title[2:]
            elif not title.startswith('⚠'):
                title = f'⚠ {title}'
            check = CheckResult(True, title, check.detail, check.hint)
        self.checks.append(check)
        if check.ok:
            if '⚠' in check.title:
                self.warnings += 1
            return
        if 'تحذير' in check.title or check.title.startswith('⚠'):
            self.warnings += 1
        else:
            self.failures += 1


class Command(BaseCommand):
    help = 'فحص قاعدة البيانات والبصمة في الإنتاج (جداول، ربط، حفظ السجلات)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--details', '--detail', action='store_true',
            dest='details',
            help='عرض تفاصيل إضافية (آخر السجلات، أجهزة)',
        )
        parser.add_argument(
            '--json', action='store_true',
            help='إخراج JSON فقط (للمراقبة الآلية)',
        )
        parser.add_argument(
            '--deploy', action='store_true',
            help='وضع النشر: يفشل فقط عند DB/جداول/مفتاح الوكيل — لا يوقف النشر لجدول بصمات فارغ',
        )

    def handle(self, *args, **options):
        report = self._run_checks(
            verbose=options['details'],
            deploy=options['deploy'],
        )
        if options['json']:
            self.stdout.write(json.dumps(self._to_dict(report), ensure_ascii=False, indent=2))
        else:
            self._print_report(report, verbose=options['details'])
        if report.failures:
            self.stderr.write(self.style.ERROR('\n❌ يوجد أخطاء حرجة — راجع التفاصيل أعلاه.'))
            raise SystemExit(1)
        if report.warnings:
            self.stdout.write(self.style.WARNING('\n⚠ يوجد تحذيرات — قد لا تُحفظ البصمات أو الربط غير مكتمل.'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ فحص البصمة: كل شيء يبدو سليماً.'))

    def _run_checks(self, *, verbose: bool, deploy: bool) -> Report:
        report = Report(deploy_mode=deploy)
        report.add(self._check_database(), critical=True)
        report.add(self._check_attendance_tables(), critical=True)
        report.add(self._check_agent_api_key(), critical=True)
        report.add(self._check_devices(), critical=not deploy)
        report.add(self._check_punches_saved(), critical=not deploy)
        report.add(self._check_relationships(), critical=not deploy)
        if verbose:
            self._verbose_extra = True
        else:
            self._verbose_extra = False
        return report

    def _check_database(self) -> CheckResult:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                one = cursor.fetchone()[0]
                db_name = connection.settings_dict.get('NAME', '?')
                vendor = connection.vendor
            if one != 1:
                return CheckResult(False, '❌ قاعدة البيانات', 'استعلام SELECT 1 فشل')
            host = connection.settings_dict.get('HOST') or 'local'
            return CheckResult(
                True,
                '✅ اتصال قاعدة البيانات',
                f'{vendor} — قاعدة: {db_name} — host: {host}',
            )
        except Exception as exc:
            return CheckResult(
                False,
                '❌ اتصال قاعدة البيانات',
                str(exc),
                hint='تحقق من DATABASE_URL في .env على السيرفر',
            )

    def _check_attendance_tables(self) -> CheckResult:
        from apps.attendance.models import (
            AttendancePunch,
            BiometricDevice,
            BiometricDeviceUser,
            EmployeeBiometricEnrollment,
        )

        expected = [
            (BiometricDevice, 'أجهزة البصمة'),
            (BiometricDeviceUser, 'مستخدمو الجهاز'),
            (EmployeeBiometricEnrollment, 'ربط موظف ↔ جهاز'),
            (AttendancePunch, 'سجلات البصمة (الحضور)'),
        ]
        missing = []
        for model, label in expected:
            table = model._meta.db_table
            if table not in connection.introspection.table_names():
                missing.append(f'{table} ({label})')

        if missing:
            return CheckResult(
                False,
                '❌ جداول البصمة',
                'ناقص: ' + ', '.join(missing),
                hint='شغّل: python manage.py migrate',
            )
        tables = ', '.join(m._meta.db_table for m, _ in expected)
        return CheckResult(True, '✅ جداول البصمة موجودة', tables)

    def _check_agent_api_key(self) -> CheckResult:
        key = (getattr(settings, 'ATTENDANCE_AGENT_API_KEY', None) or '').strip()
        prod = not settings.DEBUG
        if not key:
            if prod:
                return CheckResult(
                    False,
                    '❌ مفتاح وكيل البصمة',
                    'ATTENDANCE_AGENT_API_KEY غير مضبوط في .env',
                    hint='python manage.py generate_attendance_agent_key',
                )
            return CheckResult(
                True,
                '⚠ مفتاح وكيل البصمة (تطوير)',
                'غير مضبوط — مقبول في التطوير فقط',
            )
        return CheckResult(True, '✅ مفتاح وكيل البصمة', f'مضبوط ({len(key)} حرفاً)')

    def _check_devices(self) -> CheckResult:
        from apps.attendance.models import BiometricDevice

        total = BiometricDevice.objects.filter(is_deleted=False).count()
        active = BiometricDevice.objects.filter(is_deleted=False, is_active=True).count()
        if total == 0:
            return CheckResult(
                False,
                '❌ أجهزة البصمة',
                'لا يوجد أي جهاز مسجّل في attendance_biometricdevice',
                hint='أضف جهازاً من واجهة: أجهزة البصمة',
            )

        never_synced = BiometricDevice.objects.filter(
            is_deleted=False, is_active=True, last_sync_at__isnull=True,
        ).count()
        detail = f'إجمالي: {total} | نشط: {active} | لم تُزامَن أبداً: {never_synced}'
        if active and never_synced == active:
            return CheckResult(
                False,
                '❌ مزامنة الأجهزة',
                detail,
                hint='شغّل وكيل الفرع (biometric_bridge/agent.py) وتأكد من VPN/IP',
            )
        if never_synced:
            return CheckResult(True, '⚠ أجهزة البصمة', detail)
        return CheckResult(True, '✅ أجهزة البصمة', detail)

    def _check_punches_saved(self) -> CheckResult:
        from apps.attendance.models import AttendancePunch

        total = AttendancePunch.objects.filter(is_deleted=False).count()
        if total == 0:
            return CheckResult(
                False,
                '❌ سجلات البصمة',
                'جدول attendance_attendancepunch فارغ — لا تُحفظ بصمات بعد',
                hint='تحقق من الوكيل المحلي + POST /api/v1/attendance/agent/ingest/',
            )

        since = timezone.now() - timedelta(days=7)
        recent = AttendancePunch.objects.filter(
            is_deleted=False, punched_at__gte=since,
        ).count()
        latest = (
            AttendancePunch.objects.filter(is_deleted=False)
            .order_by('-punched_at')
            .values_list('punched_at', 'device_user_id', 'device_id')
            .first()
        )
        detail = f'إجمالي السجلات: {total} | آخر 7 أيام: {recent}'
        if latest:
            detail += f' | آخر بصمة: {latest[0]} (مستخدم جهاز {latest[1]}، جهاز id={latest[2]})'
        if recent == 0:
            return CheckResult(
                True,
                '⚠ سجلات البصمة (قديمة فقط)',
                detail + ' — لا بصمات جديدة خلال 7 أيام',
                hint='تحقق من تشغيل الوكيل أو تكرار السجلات (skipped_duplicate)',
            )
        return CheckResult(True, '✅ سجلات البصمة محفوظة', detail)

    def _check_relationships(self) -> CheckResult:
        from apps.attendance.models import (
            AttendancePunch,
            BiometricDevice,
            EmployeeBiometricEnrollment,
        )
        from apps.employees.models import Employee

        issues = []

        # بصمات لجهاز محذوف/غير موجود (يجب ألا يحدث مع FK)
        bad_device = AttendancePunch.objects.filter(is_deleted=False).exclude(
            device_id__in=BiometricDevice.objects.values_list('id', flat=True),
        ).count()
        if bad_device:
            issues.append(f'بصمات بجهاز غير موجود: {bad_device}')

        unmapped = AttendancePunch.objects.filter(
            is_deleted=False, employee_id__isnull=True,
        ).count()
        total_punches = AttendancePunch.objects.filter(is_deleted=False).count()
        enrollments = EmployeeBiometricEnrollment.objects.filter(is_deleted=False).count()

        mapped_pct = 0
        if total_punches:
            mapped = total_punches - unmapped
            mapped_pct = int(100 * mapped / total_punches)

        detail_parts = [
            f'ربط موظف↔جهاز (enrollment): {enrollments}',
            f'بصمات بدون employee_id: {unmapped} من {total_punches}',
        ]
        if total_punches:
            detail_parts.append(f'نسبة الربط بالموظف: {mapped_pct}%')

        if issues:
            return CheckResult(False, '❌ سلامة الربط', '; '.join(issues + detail_parts))

        if total_punches and unmapped == total_punches and enrollments == 0:
            return CheckResult(
                True,
                '⚠ الربط بالموظفين',
                '; '.join(detail_parts),
                hint='من واجهة البصمة: اربط أرقام مستخدمي الجهاز بالموظفين (EmployeeBiometricEnrollment)',
            )
        if total_punches and mapped_pct < 50:
            return CheckResult(
                True,
                '⚠ الربط بالموظفين',
                '; '.join(detail_parts),
                hint='كثير من البصمات غير مربوطة بموظف — راجع التسجيل على الجهاز',
            )

        # موظف مُحذوف لكن ما زال مربوطاً ببصمة
        deleted_emp_punches = AttendancePunch.objects.filter(
            is_deleted=False,
            employee_id__isnull=False,
        ).exclude(
            employee_id__in=Employee.objects.filter(is_deleted=False).values_list('id', flat=True),
        ).count()
        if deleted_emp_punches:
            issues.append(f'بصمات لموظف محذوف/غير نشط: {deleted_emp_punches}')

        if issues:
            return CheckResult(True, '⚠ سلامة الربط', '; '.join(issues + detail_parts))

        return CheckResult(True, '✅ الربط والعلاقات', '; '.join(detail_parts))

    def _print_report(self, report: Report, *, verbose: bool) -> None:
        title = '═══ فحص البصمة / الإنتاج ═══'
        if report.deploy_mode:
            title += ' (وضع النشر — حرج فقط)'
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{title}\n'))
        django_env = os.environ.get('DJANGO_ENV', '?')
        env = 'إنتاج' if not settings.DEBUG else 'تطوير'
        self.stdout.write(f'البيئة: {env} | DJANGO_ENV={django_env} | DEBUG={settings.DEBUG}\n')

        for c in report.checks:
            style = self.style.SUCCESS if c.ok and '⚠' not in c.title else (
                self.style.WARNING if c.ok else self.style.ERROR
            )
            self.stdout.write(style(f'{c.title}'))
            if c.detail:
                self.stdout.write(f'   {c.detail}')
            if c.hint:
                self.stdout.write(self.style.NOTICE(f'   ← {c.hint}'))

        if verbose:
            self._print_verbose()

        self.stdout.write('')
        self.stdout.write(
            f'الملخص: {len(report.checks) - report.failures - report.warnings} ناجح | '
            f'{report.warnings} تحذير | {report.failures} فشل'
        )

    def _print_verbose(self) -> None:
        from apps.attendance.models import (
            AttendancePunch,
            BiometricDevice,
            BiometricDeviceUser,
            EmployeeBiometricEnrollment,
        )

        self.stdout.write(self.style.MIGRATE_HEADING('\n── تفاصيل ──'))
        for d in BiometricDevice.objects.filter(is_deleted=False).order_by('id')[:20]:
            sync = d.last_sync_at.strftime('%Y-%m-%d %H:%M') if d.last_sync_at else '—'
            branch = d.branch.name if d.branch_id else '—'
            self.stdout.write(
                f'  جهاز [{d.id}] {d.name} | {d.ip_address}:{d.port} | فرع: {branch} | '
                f'حالة: {d.connection_status} | آخر مزامنة: {sync}'
            )

        counts = {
            'attendance_biometricdeviceuser': BiometricDeviceUser.objects.filter(is_deleted=False).count(),
            'attendance_employeebiometricenrollment': EmployeeBiometricEnrollment.objects.filter(
                is_deleted=False,
            ).count(),
            'attendance_attendancepunch': AttendancePunch.objects.filter(is_deleted=False).count(),
        }
        self.stdout.write('\n  عدد الصفوف:')
        for table, n in counts.items():
            self.stdout.write(f'    {table}: {n}')

        recent = (
            AttendancePunch.objects.filter(is_deleted=False)
            .select_related('device', 'employee')
            .order_by('-punched_at')[:5]
        )
        if recent:
            self.stdout.write('\n  آخر 5 بصمات:')
            for p in recent:
                emp = p.employee.name if p.employee_id else '(غير مربوط)'
                self.stdout.write(
                    f'    {p.punched_at} | جهاز {p.device_id} | user {p.device_user_id} | {emp}'
                )

        self.stdout.write(self.style.NOTICE(
            '\n  جدول السجلات الرئيسي: attendance_attendancepunch'
            '\n  جدول مستخدمي الجهاز (مساعد): attendance_biometricdeviceuser'
        ))

    def _to_dict(self, report: Report) -> dict:
        return {
            'summary': {
                'ok': report.failures == 0,
                'failures': report.failures,
                'warnings': report.warnings,
                'deploy_mode': report.deploy_mode,
            },
            'checks': [
                {
                    'ok': c.ok,
                    'title': c.title,
                    'detail': c.detail,
                    'hint': c.hint,
                }
                for c in report.checks
            ],
        }
