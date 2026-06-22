"""تأكيد وجود جدول إعدادات واتساب — سير العمل والسجل الافتراضي بعد النشر."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'يُطبّق migrations لتطبيق setup عند الحاجة ويُنشئ سجل إعدادات واتساب سير العمل (pk=1).'

    def handle(self, *args, **options):
        from apps.setup.models import WorkflowWhatsAppSettings

        try:
            obj = WorkflowWhatsAppSettings.get_solo()
            self.stdout.write(
                f'إعدادات واتساب — سير العمل جاهزة (enabled={obj.is_enabled}).'
            )
            return
        except OperationalError as exc:
            if 'setup_workflowwhatsappsettings' not in str(exc).lower():
                raise
            self.stdout.write(self.style.WARNING(
                'جدول setup_workflowwhatsappsettings غير موجود — تطبيق migrations لتطبيق setup...'
            ))

        call_command('migrate', 'setup', verbosity=1, interactive=False)

        try:
            obj = WorkflowWhatsAppSettings.get_solo()
        except OperationalError as exc:
            self.stderr.write(self.style.ERROR(
                f'فشل إنشاء جدول إعدادات واتساب — سير العمل: {exc}'
            ))
            raise SystemExit(1) from exc

        self.stdout.write(self.style.SUCCESS(
            f'تم إنشاء جدول إعدادات واتساب — سير العمل (enabled={obj.is_enabled}).'
        ))
