"""
محرك MySQL/MariaDB للاستضافة المشتركة (Hostinger) — بدون جداول المناطق الزمنية.

المشكلة: Django يحوّل التواريخ في SQL عبر CONVERT_TZ(..., 'UTC', 'Asia/Riyadh').
على خوادم لم تُحمَّل فيها جداول mysql.time_zone* يُرجع CONVERT_TZ قيمة NULL، فتنكسر
كل الاستعلامات المجمّعة بالتاريخ المحلي (TruncDate، __date، تقارير الحضور اليومية...).

الحل: نفس محرك Django مع تمرير إزاحات رقمية (+00:00 ← +03:00) لا تحتاج تلك الجداول.
الرياض بلا توقيت صيفي فالإزاحة ثابتة؛ للمناطق ذات التوقيت الصيفي تُستخدم إزاحة اللحظة الحالية.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.backends.mysql import base as mysql_base
from django.db.backends.mysql.operations import DatabaseOperations as MySQLDatabaseOperations
from django.db.backends.utils import split_tzname_delta


def _format_offset(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    sign = '+' if total >= 0 else '-'
    total = abs(total)
    return f'{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}'


def numeric_tz_offset(tzname: str) -> str:
    """'UTC' ⇒ '+00:00'، 'Asia/Riyadh' ⇒ '+03:00'، 'UTC+03:00' ⇒ '+03:00'."""
    name, sign, offset = split_tzname_delta(tzname)
    try:
        base = datetime.now(ZoneInfo(name)).utcoffset() if name else timedelta(0)
    except Exception:  # اسم غير معروف لـ zoneinfo — نتركه كما هو
        return tzname
    if offset:
        hours, minutes = (offset.split(':') + ['0'])[:2]
        delta = timedelta(hours=int(hours), minutes=int(minutes))
        base = base + delta if sign == '+' else base - delta
    return _format_offset(base or timedelta(0))


class DatabaseOperations(MySQLDatabaseOperations):
    def _convert_sql_to_tz(self, sql, params, tzname):
        if tzname and settings.USE_TZ and self.connection.timezone_name != tzname:
            return f'CONVERT_TZ({sql}, %s, %s)', (
                *params,
                numeric_tz_offset(self.connection.timezone_name),
                numeric_tz_offset(tzname),
            )
        return sql, params


class DatabaseWrapper(mysql_base.DatabaseWrapper):
    ops_class = DatabaseOperations
