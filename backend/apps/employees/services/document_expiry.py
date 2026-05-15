"""
جمع وثائق الموظفين التي تنتهي ضمن نافذة زمنية.

يشمل: جواز، كرت صحي، إقامة، انتهاء بوليصة تأمين طبي للموظف، تاريخ انتهاء العقد المخطط.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from django.db.models import Q

from apps.employees.models import Employee

# (حقل النموذج، مفتاح الإشعار، عنوان عربي)
_DOCUMENT_DATE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ('passport_expiry_date', 'passport', 'جواز السفر'),
    ('health_card_expiry', 'health_card', 'الكرت الصحي'),
    ('residency_expiry_date', 'residency', 'الإقامة'),
    ('medical_insurance_expiry_date', 'medical_insurance', 'التأمين الطبي'),
    ('contract_expiry_date', 'contract', 'العقد'),
)


@dataclass(frozen=True)
class ExpiringDocumentRow:
    employee_id: int
    employee_name: str
    document_code: str
    document_label: str
    expiry_date: date
    days_until: int


def document_expiry_dedupe_prefix(
    *, employee_id: int, document_code: str, expiry_date: date
) -> str:
    """بادئة ثابتة في نص الإشعار لمنع التكرار ضمن نافذة زمنية."""
    return f'[doc_expiry:{document_code}:{employee_id}:{expiry_date.isoformat()}]'


def collect_expiring_documents(
    *,
    reference_date: date,
    horizon_days: int,
    statuses: Sequence[str] | None = None,
) -> list[ExpiringDocumentRow]:
    """
    يُرجع صفوفاً لكل وثيقة ضمن [reference_date, reference_date + horizon_days] (شاملة).

    يُستثنى الموظفون المُصفّون (terminated) افتراضياً.
    """
    if horizon_days < 0:
        raise ValueError('horizon_days يجب أن يكون ≥ 0')
    end = reference_date + timedelta(days=horizon_days)
    status_in = statuses or (
        Employee.Status.ACTIVE,
        Employee.Status.LEAVE,
        Employee.Status.SUSPENDED,
    )

    date_q = Q()
    for fname, _, _ in _DOCUMENT_DATE_FIELDS:
        date_q |= Q(
            **{
                f'{fname}__isnull': False,
                f'{fname}__gte': reference_date,
                f'{fname}__lte': end,
            }
        )

    qs = Employee.objects.filter(status__in=status_in).filter(date_q)

    only_names = ['id', 'name', 'status'] + [t[0] for t in _DOCUMENT_DATE_FIELDS]
    rows: list[ExpiringDocumentRow] = []
    for emp in qs.only(*only_names):
        for fname, code, label in _DOCUMENT_DATE_FIELDS:
            exp: date | None = getattr(emp, fname, None)
            if exp and reference_date <= exp <= end:
                rows.append(
                    ExpiringDocumentRow(
                        employee_id=emp.id,
                        employee_name=emp.name,
                        document_code=code,
                        document_label=label,
                        expiry_date=exp,
                        days_until=(exp - reference_date).days,
                    )
                )
    rows.sort(key=lambda r: (r.expiry_date, r.employee_name, r.document_code))
    return rows
