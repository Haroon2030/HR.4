"""حساب مكافأة نهاية الخدمة عند التصفية."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

ARTICLE_77_PENALTY_MONTHS = 2
ARTICLE_74_EMPLOYEE_POST_FIVE_FACTOR = Decimal('2') / Decimal('3')  # ⅔ راتب/سنة بعد 5 سنوات

SETTLEMENT_TYPE_LABELS = {
    'company': 'تصفية نهاية خدمة (من قِبل الشركة)',
    'employee': 'استقالة (من قِبل الموظف)',
    'contract_expiry': 'انتهاء العقد بانتهاء مدته',
    'article_74': 'إنهاء العقد بالتراضي (المادة 74)',
    'article_77': 'إنهاء العقد — سبب غير مشروع (المادة 77)',
    'article_80': 'إنهاء العقد — سبب مشروع (المادة 80)',
    'probation_end': 'إنهاء العقد — نهاية فترة التجربة',
}

LEAVE_ONLY_SETTLEMENTS = frozenset({'article_80', 'probation_end'})

TERMINATION_PARTY_LABELS = {
    'company': 'من قِبل الشركة',
    'employee': 'من قِبل الموظف',
}

# توافق مع الحقل القديم
ARTICLE_77_PARTY_LABELS = TERMINATION_PARTY_LABELS

from apps.core.salary_month import (
    FIRST_TIER_LEAVE_CAP,
    FIRST_TIER_SERVICE_DAYS,
    LEAVE_DAYS_QUANT,
    STANDARD_YEAR_DAYS,
)

DAYS_PER_YEAR = Decimal(str(STANDARD_YEAR_DAYS))
FIVE_SERVICE_YEARS_DAYS = FIRST_TIER_SERVICE_DAYS
LEAVE_DAYS_FIRST_FIVE_YEARS = Decimal('21')
LEAVE_DAYS_AFTER_FIVE_YEARS = Decimal('30')


def settlement_type_label(settlement_type: str, *, article_party: str = '', article_77_party: str = '') -> str:
    party = article_party or article_77_party
    base = SETTLEMENT_TYPE_LABELS.get(settlement_type, settlement_type)
    if settlement_type in ('article_77', 'article_74') and party:
        party_label = TERMINATION_PARTY_LABELS.get(party, party)
        return f'{base} — {party_label}'
    return base


def resolve_eosb_settlement_type(settlement_type: str, article_party: str = '', article_77_party: str = '') -> str:
    """يُحوّل نوع التصفية إلى قاعدة حساب المكافأة."""
    party = article_party or article_77_party
    if settlement_type in ('article_77', 'article_74'):
        return 'employee' if party == 'employee' else 'company'
    return settlement_type


def compute_two_month_penalty(total_salary: Decimal) -> Decimal:
    return (Decimal(total_salary) * ARTICLE_77_PENALTY_MONTHS).quantize(Decimal('0.01'))


def compute_tiered_leave_accrued_days(service_days: int) -> Decimal:
    """21 يوم/سنة أول 5 سنوات، 30 يوم/سنة من السنة السادسة (سنة = 360 يوماً)."""
    if service_days <= 0:
        return Decimal('0.00')
    service_days_dec = Decimal(service_days)
    if service_days_dec <= FIVE_SERVICE_YEARS_DAYS:
        return (service_days_dec / DAYS_PER_YEAR * LEAVE_DAYS_FIRST_FIVE_YEARS).quantize(LEAVE_DAYS_QUANT)
    extra_service_days = service_days_dec - FIVE_SERVICE_YEARS_DAYS
    extra_leave = (extra_service_days / DAYS_PER_YEAR * LEAVE_DAYS_AFTER_FIVE_YEARS).quantize(LEAVE_DAYS_QUANT)
    return (FIRST_TIER_LEAVE_CAP + extra_leave).quantize(LEAVE_DAYS_QUANT)


def compute_flat_21_leave_accrued_days(service_days: int) -> Decimal:
    """21 يوم/سنة — بدون تدرج (سنة = 360 يوماً)."""
    if service_days <= 0:
        return Decimal('0.00')
    return (Decimal(service_days) / DAYS_PER_YEAR * LEAVE_DAYS_FIRST_FIVE_YEARS).quantize(LEAVE_DAYS_QUANT)


def _compute_leave_only_settlement(
    *,
    employee,
    as_of: date | None = None,
    flat_21_only: bool = False,
    title: str,
) -> tuple[Decimal, Decimal, str]:
    from apps.employees.services.leave_balance import settlement_leave_for_employee

    _, _, remaining, amount, text = settlement_leave_for_employee(
        employee,
        as_of=as_of,
        flat_21_only=flat_21_only,
        title=title,
    )
    return remaining, amount, text


def compute_article_80_leave_settlement(
    *,
    employee,
    as_of: date | None = None,
    total_salary: Decimal | None = None,
    used_leave_days: Decimal | None = None,
    eligible: bool | None = None,
    service_days: int | None = None,
) -> tuple[Decimal, Decimal, str]:
    """المادة 80 — رصيد إجازات فقط بدون مكافأة نهاية الخدمة."""
    del total_salary, used_leave_days, eligible, service_days
    return _compute_leave_only_settlement(
        employee=employee,
        as_of=as_of,
        flat_21_only=False,
        title='المادة 80',
    )


def compute_probation_end_leave_settlement(
    *,
    employee,
    as_of: date | None = None,
    total_salary: Decimal | None = None,
    used_leave_days: Decimal | None = None,
    eligible: bool | None = None,
    service_days: int | None = None,
) -> tuple[Decimal, Decimal, str]:
    """نهاية فترة التجربة — 21 يوم/سنة فقط."""
    del total_salary, used_leave_days, eligible, service_days
    return _compute_leave_only_settlement(
        employee=employee,
        as_of=as_of,
        flat_21_only=True,
        title='نهاية فترة التجربة',
    )


def compute_standard_eosb(
    *,
    last_salary: Decimal,
    service_days: int,
    service_years: Decimal,
    eligible: bool,
) -> tuple[Decimal, str]:
    """نصف راتب × السنوات الخمس الأولى + راتب كامل × ما زاد (نظام العمل)."""
    if not eligible:
        return Decimal('0.00'), 'لا يوجد كفالة — لا تُحسب مكافأة نهاية الخدمة'
    if service_days <= 180:
        return Decimal('0.00'), 'فترة تجربة (بدون مكافأة مالية)'

    half_salary = (last_salary / 2).quantize(Decimal('0.01'))
    if service_years <= 5:
        eosb = (half_salary * service_years).quantize(Decimal('0.01'))
        category = f'أول 5 سنوات — ½ راتب × {service_years} سنة'
    else:
        first_5 = (half_salary * 5).quantize(Decimal('0.01'))
        extra_years = service_years - 5
        extra = (last_salary * extra_years).quantize(Decimal('0.01'))
        eosb = first_5 + extra
        category = f'½ راتب × 5 = {first_5} + راتب كامل × {extra_years} = {extra}'
    return eosb, category


def compute_article_74_eosb(
    *,
    last_salary: Decimal,
    service_days: int,
    service_years: Decimal,
    party: str,
    eligible: bool,
) -> tuple[Decimal, str]:
    """المادة 74 — إنهاء بالتراضي."""
    if not eligible:
        return Decimal('0.00'), 'لا يوجد كفالة — لا تُحسب مكافأة نهاية الخدمة'
    if service_days <= 180:
        return Decimal('0.00'), 'فترة تجربة (بدون مكافأة مالية)'

    if party == 'company':
        return compute_standard_eosb(
            last_salary=last_salary,
            service_days=service_days,
            service_years=service_years,
            eligible=True,
        )

    third_salary = (last_salary / Decimal('3')).quantize(Decimal('0.01'))
    two_thirds_salary = (last_salary * ARTICLE_74_EMPLOYEE_POST_FIVE_FACTOR).quantize(Decimal('0.01'))
    if service_years <= 5:
        eosb = (third_salary * service_years).quantize(Decimal('0.01'))
        category = f'المادة 74 — ⅓ راتب ({third_salary}) × {service_years} سنة'
    else:
        first_5 = (third_salary * Decimal('5')).quantize(Decimal('0.01'))
        extra_years = service_years - 5
        extra = (two_thirds_salary * extra_years).quantize(Decimal('0.01'))
        eosb = first_5 + extra
        category = (
            f'المادة 74 — ⅓ راتب ({third_salary}) × 5 = {first_5} + '
            f'⅔ راتب ({two_thirds_salary}) × {extra_years} = {extra}'
        )
    return eosb, category


def compute_resignation_factor(service_years: Decimal) -> tuple[Decimal, str]:
    if service_years < 2:
        return Decimal('0.0'), 'استقالة أقل من سنتين — لا مكافأة'
    if service_years < 5:
        return Decimal('1') / Decimal('3'), 'استقالة 2-5 سنوات — ثلث المكافأة'
    if service_years < 10:
        return Decimal('2') / Decimal('3'), 'استقالة 5-10 سنوات — ثلثي المكافأة'
    return Decimal('1.0'), 'استقالة +10 سنوات — المكافأة كاملة'


def compute_settlement_eosb(
    *,
    last_salary: Decimal,
    service_days: int,
    service_years: Decimal,
    settlement_type: str,
    eligible: bool,
    article_party: str = '',
    article_77_party: str = '',
) -> tuple[Decimal, Decimal, str, str]:
    """يُرجع: المكافأة قبل المعامل، بعد المعامل، الفئة، ملاحظة الاستقالة."""
    party = article_party or article_77_party
    if settlement_type == 'article_80':
        return (
            Decimal('0.00'),
            Decimal('0.00'),
            'المادة 80 — لا تُحسب مكافأة نهاية الخدمة',
            '',
        )
    if settlement_type == 'probation_end':
        return (
            Decimal('0.00'),
            Decimal('0.00'),
            'نهاية فترة التجربة — لا تُحسب مكافأة نهاية الخدمة',
            '',
        )
    if settlement_type == 'article_74':
        eosb, category = compute_article_74_eosb(
            last_salary=last_salary,
            service_days=service_days,
            service_years=service_years,
            party=party or 'company',
            eligible=eligible,
        )
        return eosb, eosb, category, ''

    eosb_type = resolve_eosb_settlement_type(settlement_type, party)
    eosb_before, category = compute_standard_eosb(
        last_salary=last_salary,
        service_days=service_days,
        service_years=service_years,
        eligible=eligible,
    )
    resignation_note = ''
    factor = Decimal('1.0')
    if eligible and eosb_type == 'employee':
        factor, resignation_note = compute_resignation_factor(service_years)
    eosb_after = (eosb_before * factor).quantize(Decimal('0.01'))
    return eosb_before, eosb_after, category, resignation_note


def compute_transfer_commitment_eosb_amounts(
    employee,
    *,
    as_of: date | None = None,
    hire_date: date | None = None,
) -> dict[str, str | None]:
    """
    مستحقات نهاية الخدمة لنموذج التزام تحويل الراتب —
    نفس منطق «تصفية نهاية خدمة / استقالة» حتى تاريخ اليوم (أو تاريخ التوقف).
    """
    from apps.core.salary_month import employment_service_days, service_years_30day

    effective_hire = hire_date or getattr(employee, 'hire_date', None)
    if not effective_hire:
        return {'eosb_entitlement': None, 'eosb_resignation': None}

    as_of = as_of or getattr(employee, 'end_date', None) or date.today()
    service_days = employment_service_days(effective_hire, as_of)
    if service_days < 1:
        return {'eosb_entitlement': None, 'eosb_resignation': None}

    service_years = service_years_30day(service_days)
    last_salary = Decimal(employee.salary_for_end_of_service or 0)
    eligible = bool(getattr(employee, 'sponsorship_id', None)) and last_salary > 0

    _, eosb_company, _, _ = compute_settlement_eosb(
        last_salary=last_salary,
        service_days=service_days,
        service_years=service_years,
        settlement_type='company',
        eligible=eligible,
    )
    _, eosb_resignation, _, _ = compute_settlement_eosb(
        last_salary=last_salary,
        service_days=service_days,
        service_years=service_years,
        settlement_type='employee',
        eligible=eligible,
    )

    def _eosb_form_value(amount: Decimal) -> str | None:
        q = amount.quantize(Decimal('0.01'))
        return None if q <= 0 else f'{q:.2f}'

    return {
        'eosb_entitlement': _eosb_form_value(eosb_company),
        'eosb_resignation': _eosb_form_value(eosb_resignation),
    }
