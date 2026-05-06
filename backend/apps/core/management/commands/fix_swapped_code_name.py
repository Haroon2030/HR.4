"""إصلاح السجلات التي أُدخل فيها code/name بالعكس (الاسم رقم والكود نص)."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Swap code<->name for Department/CostCenter/Branch when name is numeric and code is text."

    def handle(self, *args, **options):
        from apps.departments.models import Department
        from apps.cost_centers.models import CostCenter
        from apps.core.models import Branch

        for model, label in [(Department, 'Department'), (CostCenter, 'CostCenter'), (Branch, 'Branch')]:
            fixed = 0
            for obj in model.objects.all():
                code = (obj.code or '').strip()
                name = (obj.name or '').strip()
                if (name.isdigit() or not name) and code and not code.isdigit():
                    obj.code, obj.name = (name or code), code
                    try:
                        obj.save(update_fields=['code', 'name'])
                        fixed += 1
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"{label} {obj.pk}: {e}"))
            self.stdout.write(self.style.SUCCESS(f"{label}: fixed {fixed}"))
