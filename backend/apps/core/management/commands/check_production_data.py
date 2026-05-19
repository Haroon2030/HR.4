"""
فحص شامل لبيانات الإنتاج في قاعدة PostgreSQL المتصلة (DATABASE_URL).

الاستخدام داخل حاوية Docker:
  cd /app
  python manage.py check_production_data
  python manage.py check_production_data --details
  python manage.py check_production_data --json
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection

User = get_user_model()


@dataclass
class Row:
    label: str
    count: int
    note: str = ''


@dataclass
class Issue:
    level: str  # ok | warn | fail
    title: str
    detail: str = ''
    hint: str = ''


@dataclass
class AuditReport:
    issues: list[Issue] = field(default_factory=list)
    table_rows: list[Row] = field(default_factory=list)
    fails: int = 0
    warns: int = 0

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)
        if issue.level == 'fail':
            self.fails += 1
        elif issue.level == 'warn':
            self.warns += 1


class Command(BaseCommand):
    help = 'فحص شامل: اتصال DB، جداول، أعداد السجلات، وسلامة الربط في الإنتاج'

    def add_arguments(self, parser):
        parser.add_argument(
            '--details', '--detail', action='store_true', dest='details',
            help='تفاصيل إضافية (عينات، آخر نشاط)',
        )
        parser.add_argument('--json', action='store_true', help='إخراج JSON')
        parser.add_argument(
            '--deploy', action='store_true',
            help='وضع النشر: يفشل فقط عند DB أو جداول أساسية ناقصة',
        )

    def handle(self, *args, **options):
        report = self._build_report(details=options['details'], deploy=options['deploy'])
        if options['json']:
            self.stdout.write(json.dumps(self._as_dict(report), ensure_ascii=False, indent=2))
        else:
            self._print_report(report, details=options['details'])
        if report.fails:
            raise SystemExit(1)

    def _build_report(self, *, details: bool, deploy: bool) -> AuditReport:
        report = AuditReport()
        self._check_connection(report, deploy=deploy)
        self._collect_table_counts(report)
        self._check_core_data(report, deploy=deploy)
        self._check_employees(report, deploy=deploy)
        self._check_users(report, deploy=deploy)
        self._check_attendance(report, deploy=deploy)
        self._check_workflow(report, deploy=deploy)
        if details:
            self._details_extra = True
        else:
            self._details_extra = False
        return report

    def _check_connection(self, report: AuditReport, *, deploy: bool) -> None:
        try:
            with connection.cursor() as c:
                c.execute('SELECT 1')
                c.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
                public_tables = c.fetchone()[0]
            db = settings.DATABASES['default']
            host = db.get('HOST') or 'local'
            name = db.get('NAME') or '?'
            engine = db.get('ENGINE', '').rsplit('.', 1)[-1]
            url_hint = self._safe_db_label()
            report.add(Issue(
                'ok',
                'اتصال قاعدة البيانات',
                f'{engine} | قاعدة: {name} | host: {host} | جداول public: {public_tables}\n  {url_hint}',
            ))
        except Exception as exc:
            report.add(Issue(
                'fail',
                'اتصال قاعدة البيانات',
                str(exc),
                'تحقق من DATABASE_URL في Dokploy',
            ))

    def _safe_db_label(self) -> str:
        raw = os.environ.get('DATABASE_URL', '').strip()
        if not raw:
            return 'DATABASE_URL: (من إعدادات Django فقط)'
        try:
            p = urlparse(raw)
            user = p.username or '?'
            host = p.hostname or '?'
            port = p.port or ''
            dbname = (p.path or '/').lstrip('/') or '?'
            port_s = f':{port}' if port else ''
            return f'URL: {user}@{host}{port_s}/{dbname}'
        except Exception:
            return 'DATABASE_URL: (مضبوط)'

    def _collect_table_counts(self, report: AuditReport) -> None:
        from apps.attendance.models import (
            AttendancePunch,
            BiometricDevice,
            BiometricDeviceUser,
            EmployeeBiometricEnrollment,
        )
        from apps.core.models import (
            Branch,
            Company,
            Notification,
            PendingAction,
            Role,
            UserProfile,
        )
        from apps.cost_centers.models import CostCenter
        from apps.departments.models import Department
        from apps.employees.models import Employee, EmploymentRequest
        from apps.payroll.models import PayrollLine, PayrollRun
        from apps.setup.models import Bank, Building, Insurance, Nationality, Profession, Sponsorship

        groups: list[tuple[str, list]] = [
            ('النواة', [Company, Branch, Role, UserProfile, PendingAction, Notification]),
            ('الإعداد', [Nationality, Profession, Sponsorship, Insurance, Building, Bank]),
            ('الهيكل', [Department, CostCenter]),
            ('الموظفين', [Employee, EmploymentRequest]),
            ('الرواتب', [PayrollRun, PayrollLine]),
            ('البصمة', [
                BiometricDevice,
                BiometricDeviceUser,
                EmployeeBiometricEnrollment,
                AttendancePunch,
            ]),
            ('المستخدمون', [User]),
        ]

        existing = set(connection.introspection.table_names())
        missing_any = []

        for group_name, models in groups:
            for model in models:
                table = model._meta.db_table
                if table not in existing:
                    missing_any.append(table)
                    report.table_rows.append(Row(table, -1, 'جدول غير موجود'))
                    continue
                n = model.objects.filter(is_deleted=False).count() if hasattr(model, 'is_deleted') else model.objects.count()
                report.table_rows.append(Row(f'{group_name}: {model._meta.verbose_name}', n, table))

        if missing_any:
            report.add(Issue(
                'fail',
                'جداول ناقصة',
                ', '.join(missing_any[:15]) + ('...' if len(missing_any) > 15 else ''),
                'python manage.py migrate --noinput',
            ))
        else:
            report.add(Issue('ok', 'جداول التطبيق', 'كل الجداول الأساسية موجودة في PostgreSQL'))

    def _check_core_data(self, report: AuditReport, *, deploy: bool) -> None:
        from apps.core.models import Branch, Company

        companies = Company.objects.filter(is_deleted=False).count()
        branches = Branch.objects.filter(is_deleted=False).count()
        if companies == 0:
            level = 'fail' if deploy else 'warn'
            report.add(Issue(level, 'الشركة', 'لا توجد شركة في core_company', 'أكمل تهيئة النظام'))
        else:
            report.add(Issue('ok', 'الشركة', f'{companies} شركة'))
        if branches == 0:
            report.add(Issue('warn', 'الفروع', 'لا يوجد فرع — قد يتأثر الموظفون والبصمة'))
        else:
            report.add(Issue('ok', 'الفروع', f'{branches} فرع'))

    def _check_employees(self, report: AuditReport, *, deploy: bool) -> None:
        from apps.employees.models import Employee

        total = Employee.objects.filter(is_deleted=False).count()
        active = Employee.objects.filter(is_deleted=False, status=Employee.Status.ACTIVE).count()
        no_branch = Employee.objects.filter(is_deleted=False, branch__isnull=True).count()

        if total == 0:
            level = 'warn' if deploy else 'warn'
            report.add(Issue(level, 'الموظفون', 'لا يوجد موظفون — قاعدة جديدة أو استيراد لم يُنفَّذ'))
        else:
            report.add(Issue('ok', 'الموظفون', f'إجمالي {total} | نشط {active} | بدون فرع {no_branch}'))
        if total and no_branch > total * 0.2:
            report.add(Issue(
                'warn',
                'موظفون بدون فرع',
                f'{no_branch} من {total}',
                'راجع بيانات الموظفين من قائمة الموظفين',
            ))

    def _check_users(self, report: AuditReport, *, deploy: bool) -> None:
        users = User.objects.filter(is_active=True).count()
        profiles = 0
        missing_profile = 0
        try:
            from apps.core.models import UserProfile
            profiles = UserProfile.objects.filter(is_deleted=False).count()
            missing_profile = User.objects.filter(is_active=True).exclude(
                pk__in=UserProfile.objects.values_list('user_id', flat=True),
            ).count()
        except Exception:
            pass

        if users == 0:
            report.add(Issue('fail' if deploy else 'warn', 'المستخدمون', 'لا يوجد مستخدمون نشطون'))
        else:
            report.add(Issue('ok', 'المستخدمون', f'نشط {users} | ملفات {profiles} | بدون profile {missing_profile}'))
        if missing_profile:
            report.add(Issue(
                'warn',
                'ملفات مستخدمين',
                f'{missing_profile} مستخدم بدون UserProfile',
                'python manage.py setup_user_profiles',
            ))

    def _check_attendance(self, report: AuditReport, *, deploy: bool) -> None:
        from apps.attendance.models import (
            AttendancePunch,
            BiometricDevice,
            EmployeeBiometricEnrollment,
        )

        punches = AttendancePunch.objects.filter(is_deleted=False).count()
        devices = BiometricDevice.objects.filter(is_deleted=False).count()
        enrollments = EmployeeBiometricEnrollment.objects.filter(is_deleted=False).count()
        unmapped = AttendancePunch.objects.filter(is_deleted=False, employee_id__isnull=True).count()
        mapped_pct = int(100 * (punches - unmapped) / punches) if punches else 0

        never_synced = BiometricDevice.objects.filter(
            is_deleted=False, is_active=True, last_sync_at__isnull=True,
        ).count()

        if punches == 0:
            report.add(Issue(
                'warn' if deploy else 'warn',
                'سجلات البصمة',
                'attendance_attendancepunch فارغ',
                'شغّل وكيل الفرع أو pull_biometric_attendance',
            ))
        else:
            latest = (
                AttendancePunch.objects.filter(is_deleted=False)
                .order_by('-punched_at')
                .values_list('punched_at', flat=True)
                .first()
            )
            report.add(Issue(
                'ok',
                'سجلات البصمة',
                f'{punches} سجل | آخر بصمة: {latest} | أجهزة {devices} | ربط موظف {enrollments}',
            ))
        if punches and mapped_pct == 0:
            report.add(Issue(
                'warn',
                'ربط البصمة بالموظفين',
                f'0% مربوط ({unmapped}/{punches} بدون employee_id)',
                'من أجهزة البصمة: اربط device_user_id بكل موظف',
            ))
        elif punches and mapped_pct < 50:
            report.add(Issue(
                'warn',
                'ربط البصمة بالموظفين',
                f'{mapped_pct}% مربوط فقط',
            ))
        elif punches:
            report.add(Issue('ok', 'ربط البصمة بالموظفين', f'{mapped_pct}% مربوط بموظف HR'))

        if devices and never_synced:
            report.add(Issue(
                'warn',
                'مزامنة أجهزة البصمة',
                f'{never_synced} جهاز نشط لم يُزامَن أبداً',
            ))

        key = (getattr(settings, 'ATTENDANCE_AGENT_API_KEY', None) or '').strip()
        if not settings.DEBUG and not key:
            report.add(Issue(
                'fail' if deploy else 'warn',
                'مفتاح وكيل البصمة',
                'ATTENDANCE_AGENT_API_KEY غير مضبوط',
            ))
        elif key:
            report.add(Issue('ok', 'مفتاح وكيل البصمة', f'مضبوط ({len(key)} حرفاً)'))

    def _check_workflow(self, report: AuditReport, *, deploy: bool) -> None:
        from apps.core.models import PendingAction
        from apps.employees.models import EmploymentRequest

        open_pa = PendingAction.objects.filter(
            is_deleted=False,
        ).exclude(status=PendingAction.Status.APPROVED).count()
        open_er = EmploymentRequest.objects.filter(is_deleted=False).exclude(
            status__in=[
                EmploymentRequest.Status.APPROVED,
                EmploymentRequest.Status.REJECTED,
            ],
        ).count()
        report.add(Issue(
            'ok',
            'طلبات العمل',
            f'عمليات معلّقة {open_pa} | طلبات توظيف مفتوحة {open_er}',
        ))

    def _print_report(self, report: AuditReport, *, details: bool) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING('\n═══ فحص بيانات الإنتاج (DATABASE_URL) ═══\n'))
        django_env = os.environ.get('DJANGO_ENV', '?')
        self.stdout.write(f'البيئة: DJANGO_ENV={django_env} | DEBUG={settings.DEBUG}\n')

        for issue in report.issues:
            if issue.level == 'ok':
                style = self.style.SUCCESS
                prefix = '✅'
            elif issue.level == 'warn':
                style = self.style.WARNING
                prefix = '⚠'
            else:
                style = self.style.ERROR
                prefix = '❌'
            self.stdout.write(style(f'{prefix} {issue.title}'))
            if issue.detail:
                for line in issue.detail.split('\n'):
                    self.stdout.write(f'   {line}')
            if issue.hint:
                self.stdout.write(self.style.NOTICE(f'   ← {issue.hint}'))

        self.stdout.write(self.style.MIGRATE_HEADING('\n── أعداد السجلات (غير محذوف) ──'))
        current_group = ''
        for row in report.table_rows:
            if row.count < 0:
                self.stdout.write(self.style.ERROR(f'  ❌ {row.note} — مفقود'))
                continue
            label = row.label
            if ':' in label:
                grp, name = label.split(':', 1)
                if grp != current_group:
                    current_group = grp
                    self.stdout.write(self.style.HTTP_INFO(f'\n  [{grp}]'))
                label = name.strip()
            self.stdout.write(f'    {label}: {row.count:,}  ({row.note})')

        if details and getattr(self, '_details_extra', False):
            self._print_details()

        self.stdout.write('')
        self.stdout.write(
            f'الملخص: {len(report.issues) - report.fails - report.warns} ناجح | '
            f'{report.warns} تحذير | {report.fails} فشل'
        )
        if report.fails:
            self.stdout.write(self.style.ERROR('\n❌ يوجد مشاكل حرجة.'))
        elif report.warns:
            self.stdout.write(self.style.WARNING('\n⚠ البيانات موجودة مع تحذيرات — راجع أعلاه.'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ البيانات في قاعدة الإنتاج تبدو سليمة ومكتملة.'))

    def _print_details(self) -> None:
        from apps.attendance.models import AttendancePunch
        from apps.employees.models import Employee

        self.stdout.write(self.style.MIGRATE_HEADING('\n── عينات ──'))
        emp = Employee.objects.filter(is_deleted=False).order_by('-id').first()
        if emp:
            self.stdout.write(f'  آخر موظف: [{emp.id}] {emp.name}')
        for p in AttendancePunch.objects.filter(is_deleted=False).order_by('-punched_at')[:3]:
            emp_name = p.employee.name if p.employee_id else '(غير مربوط)'
            self.stdout.write(
                f'  بصمة: {p.punched_at} | جهاز {p.device_id} | user {p.device_user_id} | {emp_name}'
            )

    def _as_dict(self, report: AuditReport) -> dict:
        return {
            'summary': {'fails': report.fails, 'warns': report.warns},
            'issues': [
                {'level': i.level, 'title': i.title, 'detail': i.detail, 'hint': i.hint}
                for i in report.issues
            ],
            'tables': [
                {'label': r.label, 'count': r.count, 'table': r.note}
                for r in report.table_rows
            ],
        }
