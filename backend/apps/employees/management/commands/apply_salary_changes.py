"""تطبيق تعديلات الرواتب التي حان شهر سريانها على ملفات الموظفين (يُجدول يومياً)."""
from django.core.management.base import BaseCommand

from apps.employees.services.salary_changes import apply_due_salary_changes


class Command(BaseCommand):
    help = 'يطبّق تعديلات الراتب المعلّقة التي حان شهر سريانها.'

    def handle(self, *args, **options):
        count = apply_due_salary_changes()
        self.stdout.write(f'تم تطبيق {count} تعديل راتب.')
