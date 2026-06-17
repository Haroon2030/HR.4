"""تأكيد وجود جدول إعدادات تقرير العمليات والسجل الافتراضي بعد النشر."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'يُطبّق migrations لتطبيق setup عند الحاجة ويُنشئ سجل إعدادات تقرير العمليات (pk=1).'

    def handle(self, *args, **options):
        from apps.setup.models import OperationsReportSettings

        try:
            obj = OperationsReportSettings.get_solo()
            self.stdout.write(
                f'إعدادات تقرير العمليات جاهزة (enabled={obj.is_enabled}, send_time={obj.send_time}).'
            )
            return
        except OperationalError as exc:
            if 'setup_operationsreportsettings' not in str(exc).lower():
                raise
            self.stdout.write(self.style.WARNING(
                'جدول setup_operationsreportsettings غير موجود — تطبيق migrations لتطبيق setup...'
            ))

        call_command('migrate', 'setup', verbosity=1, interactive=False)

        try:
            obj = OperationsReportSettings.get_solo()
        except OperationalError as exc:
            self.stderr.write(self.style.ERROR(f'فشل إنشاء جدول إعدادات تقرير العمليات: {exc}'))
            raise SystemExit(1) from exc

        self.stdout.write(self.style.SUCCESS(
            f'تم إنشاء جدول إعدادات تقرير العمليات (enabled={obj.is_enabled}).'
        ))
