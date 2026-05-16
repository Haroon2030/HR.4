"""اكتشاف Comm Key الصحيح لجهاز ZKTeco (شغّله من PC على شبكة الفرع + VPN)."""
from django.core.management.base import BaseCommand, CommandError

from apps.attendance.models import BiometricDevice
from apps.attendance.services.zk_client import probe_device

# قيم شائعة على أجهزة ZKTeco قبل المسح الكامل
COMMON_KEYS = (0, 1, 12345, 54321, 888888, 666666, 111111)


class Command(BaseCommand):
    help = 'يجرب Comm Key حتى ينجح الاتصال بالجهاز (من شبكة الفرع فقط)'

    def add_arguments(self, parser):
        parser.add_argument('--device', type=int, required=True, help='معرّف الجهاز في النظام')
        parser.add_argument('--max', type=int, default=50, help='أقصى رقم للمسح بعد القيم الشائعة')
        parser.add_argument('--apply', action='store_true', help='حفظ المفتاح في قاعدة البيانات')

    def handle(self, *args, **options):
        try:
            device = BiometricDevice.objects.get(pk=options['device'], is_deleted=False)
        except BiometricDevice.DoesNotExist as exc:
            raise CommandError(f'جهاز {options["device"]} غير موجود') from exc

        keys_to_try: list[int] = []
        seen: set[int] = set()
        for k in list(COMMON_KEYS) + list(range(0, max(0, options['max']) + 1)):
            if k in seen:
                continue
            seen.add(k)
            keys_to_try.append(k)

        self.stdout.write(
            f'الجهاز: {device.name} ({device.ip_address}:{device.port}) — '
            f'Comm Key الحالي في DB: {device.comm_key}'
        )

        for key in keys_to_try:
            device.comm_key = key
            result = probe_device(device, force_mock=False)
            if result.ok:
                self.stdout.write(self.style.SUCCESS(
                    f'نجح الاتصال بـ Comm Key = {key} — {result.message}'
                ))
                if options['apply']:
                    BiometricDevice.objects.filter(pk=device.pk).update(comm_key=key)
                    self.stdout.write(self.style.SUCCESS('تم حفظ Comm Key في قاعدة البيانات.'))
                else:
                    self.stdout.write(
                        'أعد التشغيل مع --apply لحفظ القيمة، أو عدّلها من «إعداد الأجهزة».'
                    )
                return

        raise CommandError(
            'لم يُعثر على Comm Key ضمن النطاق. '
            'اقرأ القيمة من الجهاز: Menu → Comm → PC Connection.'
        )
