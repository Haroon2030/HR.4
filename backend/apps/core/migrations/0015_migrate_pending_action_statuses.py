"""
Data migration: convert legacy PendingAction.status values to the new
multi-stage values introduced with the 4-stage approval workflow.

Mapping:
    pending  → pending_branch  (لم يبدأ في الموافقة)
    rejected → returned        (مرتجَع لإعادة الإرسال — لا يوجد رفض نهائي)
    approved → approved        (يبقى كما هو)
"""
from django.db import migrations


STATUS_MAP = {
    'pending': 'pending_branch',
    'rejected': 'returned',
}


def forwards(apps, schema_editor):
    PendingAction = apps.get_model('core', 'PendingAction')
    HistoricalPendingAction = apps.get_model('core', 'HistoricalPendingAction')

    for old, new in STATUS_MAP.items():
        PendingAction.objects.filter(status=old).update(status=new)
        HistoricalPendingAction.objects.filter(status=old).update(status=new)


def backwards(apps, schema_editor):
    PendingAction = apps.get_model('core', 'PendingAction')
    HistoricalPendingAction = apps.get_model('core', 'HistoricalPendingAction')

    reverse = {
        'pending_branch': 'pending',
        'pending_gm': 'pending',
        'pending_officer': 'pending',
        'returned': 'rejected',
    }
    for old, new in reverse.items():
        PendingAction.objects.filter(status=old).update(status=new)
        HistoricalPendingAction.objects.filter(status=old).update(status=new)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0014_notification_historicalpendingaction_assigned_at_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
