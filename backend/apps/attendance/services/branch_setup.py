"""إعداد فرع للبصمة عند عدم وجود فروع في النظام."""
from __future__ import annotations

import re
import unicodedata

from django.db import transaction

from apps.core.models import Branch, Company


def _slug_code(name: str, *, prefix: str = 'BR') -> str:
    """رمز فرع فريد من الاسم."""
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9]+', '', ascii_name).upper()[:12]
    if not slug:
        slug = 'BRANCH'
    base = f'{prefix}-{slug}'[:18]
    code = base
    n = 1
    while Branch.objects.filter(code=code).exists():
        code = f'{base[:15]}{n}'[:20]
        n += 1
    return code


def get_or_create_default_company() -> Company:
    company = Company.objects.filter(is_deleted=False).order_by('id').first()
    if company:
        return company
    return Company.objects.create(
        name='الشركة الرئيسية',
        tax_number='',
        commercial_record='',
    )


@transaction.atomic
def ensure_branch_for_device(
    *,
    branch_id: int | None = None,
    branch_name: str | None = None,
    device_name: str | None = None,
) -> Branch:
    """
    يعيد فرعاً للجهاز:
    - branch_id إن وُجد
    - أو إنشاء/جلب فرع بالاسم (من branch_name أو اسم الجهاز)
    """
    if branch_id:
        return Branch.objects.get(pk=branch_id, is_deleted=False)

    name = (branch_name or device_name or '').strip()
    if not name:
        raise ValueError('branch_name_required')

    existing = Branch.objects.filter(is_deleted=False, name__iexact=name).first()
    if existing:
        return existing

    company = get_or_create_default_company()
    return Branch.objects.create(
        name=name,
        code=_slug_code(name),
        company=company,
        is_active=True,
    )
