# Generated manually — dedupe + unique fingerprint per device punch

from django.db import migrations, models
from django.db.models import Count, Min


def dedupe_attendance_punches(apps, schema_editor):
    AttendancePunch = apps.get_model('attendance', 'AttendancePunch')

    # تكرار بنفس uid على الجهاز
    dup_uids = (
        AttendancePunch.objects.filter(device_record_uid__isnull=False)
        .values('device_id', 'device_record_uid')
        .annotate(c=Count('id'), keep_id=Min('id'))
        .filter(c__gt=1)
    )
    for row in dup_uids:
        AttendancePunch.objects.filter(
            device_id=row['device_id'],
            device_record_uid=row['device_record_uid'],
        ).exclude(pk=row['keep_id']).delete()

    # تكرار بنفس المستخدم والوقت (ثانية)
    seen: set[tuple] = set()
    to_delete: list[int] = []
    for p in AttendancePunch.objects.order_by('id').iterator(chunk_size=2000):
        ts = p.punched_at.replace(microsecond=0)
        key = (p.device_id, p.device_user_id, ts)
        if key in seen:
            to_delete.append(p.id)
        else:
            seen.add(key)
    if to_delete:
        AttendancePunch.objects.filter(id__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_attendancepunch_punch_type_source'),
    ]

    operations = [
        migrations.RunPython(dedupe_attendance_punches, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='attendancepunch',
            constraint=models.UniqueConstraint(
                fields=['device', 'device_user_id', 'punched_at'],
                name='uniq_device_user_punch_time',
            ),
        ),
    ]
