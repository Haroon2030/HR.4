"""إزالة السجلات المكررة يدوياً (نفس الجهاز + مستخدم + وقت)."""
from django.core.management.base import BaseCommand
from django.db.models import Count, Min

from apps.attendance.models import AttendancePunch


class Command(BaseCommand):
    help = 'حذف سجلات الحضور المكررة مع الإبقاء على أقدم سجل لكل بصمة'

    def add_arguments(self, parser):
        parser.add_argument('--device', type=int, help='تقييد بحذف مكررات جهاز واحد')
        parser.add_argument('--dry-run', action='store_true', help='عرض العدد دون حذف')

    def handle(self, *args, **options):
        qs = AttendancePunch.objects.all()
        if options.get('device'):
            qs = qs.filter(device_id=options['device'])

        deleted = 0
        dup_uids = (
            qs.filter(device_record_uid__isnull=False)
            .values('device_id', 'device_record_uid')
            .annotate(c=Count('id'), keep_id=Min('id'))
            .filter(c__gt=1)
        )
        for row in dup_uids:
            dup_qs = qs.filter(
                device_id=row['device_id'],
                device_record_uid=row['device_record_uid'],
            ).exclude(pk=row['keep_id'])
            count = dup_qs.count()
            if not options['dry_run']:
                dup_qs.delete()
            deleted += count

        seen: set[tuple] = set()
        to_delete: list[int] = []
        for p in qs.order_by('id').iterator(chunk_size=5000):
            key = (p.device_id, p.device_user_id, p.punched_at.replace(microsecond=0))
            if key in seen:
                to_delete.append(p.id)
            else:
                seen.add(key)

        if options['dry_run']:
            self.stdout.write(f'سيتم حذف {deleted + len(to_delete)} سجل مكرر')
            return

        if to_delete:
            AttendancePunch.objects.filter(id__in=to_delete).delete()
        deleted += len(to_delete)
        self.stdout.write(self.style.SUCCESS(f'تم حذف {deleted} سجل مكرر'))
