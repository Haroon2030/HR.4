"""قواعد عقد العمل — سعودي / أجنبي."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.setup.models import Nationality

# نسب خصم التأمينات (GOSI) للموظف السعودي
SAUDI_GOSI_EMPLOYEE_RATES: tuple[Decimal, ...] = (
    Decimal('10.75'),
    Decimal('10.25'),
    Decimal('9.75'),
)

SAUDI_GOSI_EMPLOYEE_RATE_CHOICES: tuple[tuple[str, str], ...] = (
    ('10.75', '10.75%'),
    ('10.25', '10.25%'),
    ('9.75', '9.75%'),
)


class ContractType:
    FIXED = 'fixed'
    UNLIMITED = 'unlimited'

    CHOICES = (
        (FIXED, 'محدد المدة'),
        (UNLIMITED, 'غير محدد المدة'),
    )


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def normalize_insurance_rate(rate) -> Decimal | None:
    if rate is None or rate == '':
        return None
    return Decimal(str(rate)).quantize(Decimal('0.01'))


def is_valid_saudi_insurance_rate(rate) -> bool:
    normalized = normalize_insurance_rate(rate)
    return normalized in SAUDI_GOSI_EMPLOYEE_RATES if normalized is not None else False


def validate_insurance_deduction_rate_for_nationality(rate, nationality) -> None:
    """السعودي: قائمة GOSI الثابتة. غير السعودي: 0–100%."""
    if is_saudi_nationality(nationality):
        if not is_valid_saudi_insurance_rate(rate):
            raise ValidationError(
                'نسبة خصم التأمين للسعودي يجب اختيارها من: 10.75، 10.25، 9.75.'
            )
        return
    normalized = normalize_insurance_rate(rate)
    if normalized is None:
        return
    if normalized < 0 or normalized > 100:
        raise ValidationError('نسبة التأمين يجب أن تكون بين 0 و 100.')


def is_saudi_nationality(nationality) -> bool:
    if not nationality:
        return False
    name = (getattr(nationality, 'name', None) or '').strip()
    code = (getattr(nationality, 'code', None) or '').strip().upper()
    if code in {'SA', 'SAU', 'SAUDI', '1'}:
        return True
    lowered = name.replace(' ', '')
    return 'سعود' in lowered


@lru_cache(maxsize=1)
def saudi_nationality_ids() -> tuple[int, ...]:
    return _query_saudi_nationality_ids()


def _query_saudi_nationality_ids() -> tuple[int, ...]:
    return tuple(
        Nationality.objects.filter(
            Q(name__icontains='سعود')
            | Q(code__iexact='SA')
            | Q(code__iexact='SAU')
            | Q(code__iexact='SAUDI')
            | Q(code='1'),
            is_deleted=False,
        ).values_list('id', flat=True)
    )


def refresh_saudi_nationality_ids_cache() -> tuple[int, ...]:
    saudi_nationality_ids.cache_clear()
    return saudi_nationality_ids()


def _add_months(d: date, months: int) -> date:
    import calendar

    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_contract_expiry(start: date, months: int) -> date:
    """نهاية العقد = بداية + المدة بالأشهر."""
    return _add_months(start, months)


def fourth_year_start(hire_date: date) -> date:
    """بداية السنة الرابعة من تاريخ التعيين."""
    return _add_years(hire_date, 3)


def should_auto_unlimited(*, hire_date: date | None, nationality, today: date | None = None) -> bool:
    if not hire_date or not is_saudi_nationality(nationality):
        return False
    return (today or date.today()) >= fourth_year_start(hire_date)


def default_contract_type(*, nationality, hire_date: date | None, today: date | None = None) -> str:
    if should_auto_unlimited(hire_date=hire_date, nationality=nationality, today=today):
        return ContractType.UNLIMITED
    return ContractType.FIXED


def sync_employee_contract(employee, *, today: date | None = None) -> bool:
    """
    يطبّق قواعد العقد على كائن الموظف (قبل الحفظ).
    يُرجع True إذا تغيّرت حقول.
    """
    today = today or date.today()
    changed = False
    nationality = getattr(employee, 'nationality', None)

    if should_auto_unlimited(
        hire_date=employee.hire_date,
        nationality=nationality,
        today=today,
    ):
        if employee.contract_type != ContractType.UNLIMITED:
            employee.contract_type = ContractType.UNLIMITED
            changed = True
        if employee.contract_duration_months is not None:
            employee.contract_duration_months = None
            changed = True
        if employee.contract_duration_text:
            employee.contract_duration_text = ''
            changed = True
        if employee.contract_expiry_date is not None:
            employee.contract_expiry_date = None
            changed = True
        return changed

    if not employee.contract_type:
        employee.contract_type = ContractType.FIXED
        changed = True

    if employee.contract_type == ContractType.FIXED:
        if (
            is_saudi_nationality(nationality)
            and employee.contract_start_date
            and employee.contract_duration_months
            and not employee.contract_expiry_date
        ):
            employee.contract_expiry_date = compute_contract_expiry(
                employee.contract_start_date,
                employee.contract_duration_months,
            )
            changed = True

    return changed


def validate_contract_fields(
    *,
    nationality,
    hire_date,
    contract_type: str,
    contract_duration_months,
    contract_duration_text: str,
    contract_start_date,
    contract_expiry_date,
    today: date | None = None,
) -> dict[str, str]:
    """أخطاء التحقق — مفتاح = اسم الحقل."""
    errors: dict[str, str] = {}
    saudi = is_saudi_nationality(nationality)
    today = today or date.today()

    if saudi and contract_type == ContractType.UNLIMITED and hire_date:
        if today < fourth_year_start(hire_date):
            errors['contract_type'] = (
                'لا يُسمح بـ «غير محدد المدة» للسعودي قبل بداية السنة الرابعة من تاريخ التعيين.'
            )

    if contract_type == ContractType.FIXED and saudi:
        if contract_duration_months is not None and contract_duration_months > 12:
            errors['contract_duration_months'] = 'مدة عقد السعودي لا تتجاوز 12 شهراً (سنة واحدة).'
        if contract_duration_months is not None and contract_duration_months < 1:
            errors['contract_duration_months'] = 'أدخل مدة العقد بالأشهر (1–12).'

    if contract_start_date and contract_expiry_date and contract_expiry_date < contract_start_date:
        errors['contract_expiry_date'] = 'تاريخ نهاية العقد يجب أن يكون بعد تاريخ البداية.'

    if (
        contract_type == ContractType.FIXED
        and saudi
        and contract_start_date
        and contract_duration_months
        and not contract_expiry_date
    ):
        # لا خطأ — يمكن حساب النهاية لاحقاً
        pass

    if contract_type == ContractType.FIXED and not saudi and not (contract_duration_text or '').strip():
        if contract_duration_months is None and not contract_expiry_date:
            errors['contract_duration_text'] = 'أدخل مدة العقد للأجنبي (مثال: سنتان / 24 شهر).'

    return errors
