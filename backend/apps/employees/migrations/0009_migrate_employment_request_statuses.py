"""ترقية حالات طلبات التوظيف القديمة إلى دورة الموافقات الثلاثية الجديدة.

- 'pending'   → 'pending_branch'  (لم يبتّ به مدير الفرع بعد)
- 'approved'  ← يبقى كما هو (طلبات قديمة كان مدير الفرع يوافق ويُنشئ الموظف فوراً)
- 'rejected'  ← يبقى كما هو
"""
from django.db import migrations


def forward(apps, schema_editor):
    EmploymentRequest = apps.get_model('employees', 'EmploymentRequest')
    EmploymentRequest.objects.filter(status='pending').update(status='pending_branch')


def reverse(apps, schema_editor):
    EmploymentRequest = apps.get_model('employees', 'EmploymentRequest')
    EmploymentRequest.objects.filter(
        status__in=['pending_branch', 'pending_gm', 'pending_officer']
    ).update(status='pending')


class Migration(migrations.Migration):
    dependencies = [
        ('employees', '0008_employmentrequest_assigned_at_and_more'),
    ]
    operations = [migrations.RunPython(forward, reverse)]
