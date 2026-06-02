from django.db import migrations


def backfill_administration(apps, schema_editor):
    PendingAction = apps.get_model('core', 'PendingAction')

    for action in PendingAction.objects.filter(administration_id__isnull=True).iterator(chunk_size=2000):
        employee = getattr(action, 'employee', None)
        admin_id = getattr(employee, 'administration_id', None)
        if admin_id:
            action.administration_id = admin_id
            action.save(update_fields=['administration'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_pendingaction_administration'),
        ('employees', '0029_employmentrequest_administration'),
    ]

    operations = [
        migrations.RunPython(backfill_administration, migrations.RunPython.noop),
    ]
