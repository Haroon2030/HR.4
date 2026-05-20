"""تحويل سجلات البصمة لجدول التصدير."""
from __future__ import annotations

from django.utils import timezone

from apps.attendance.models import AttendancePunch


def punches_to_table_rows(qs) -> dict:
    columns = [
        'التاريخ', 'الوقت', 'معرف ZK', 'رقم المستخدم', 'الاسم على الجهاز',
        'موظف HR', 'الرقم الوظيفي', 'نوع الحركة', 'St', 'التحقق', 'Vm',
        'الجهاز', 'IP',
    ]
    rows = []
    for p in qs.iterator(chunk_size=5000):
        local = timezone.localtime(p.punched_at)
        rows.append([
            local.strftime('%Y-%m-%d'),
            local.strftime('%H:%M:%S'),
            str(p.device_record_uid or ''),
            str(p.device_user_id),
            p.device_user_name or '—',
            p.employee.name if p.employee else 'غير مربوط',
            p.employee.employee_number if p.employee else '—',
            p.get_punch_type_display(),
            str(p.raw_status if p.raw_status is not None else '—'),
            p.verify_mode_label or '—',
            str(p.verify_mode if p.verify_mode is not None else '—'),
            p.device.name,
            p.device.ip_address,
        ])
    return {'columns': columns, 'rows': rows}
