"""تعديل أخصائي الموارد على خصومات التصفية قبل الموافقة النهائية.

تُحفظ التعديلات في payload الطلب تحت المفتاح ``settlement_override`` وتُطبَّق على:
- تنفيذ تصفية نهاية الخدمة (end_of_service)،
- نموذج التصفية المطبوع (للنوعين terminate و end_of_service).
"""
from decimal import Decimal, InvalidOperation

from django.utils import timezone

OVERRIDE_KEY = 'settlement_override'

# الخصومات القابلة للتعديل (نفس مفاتيح compute_settlement_financials)
DEDUCTION_FIELDS = (
    ('loans_deduction', 'السلف والقروض'),
    ('absences_deduction', 'الغيابات'),
    ('penalties_deduction', 'مخالفات غير محتسبة'),
    ('cash_shortages_deduction', 'عجز كاشير غير محتسب'),
    ('overpaid_salary_recovery', 'استرداد راتب صُرف زيادة'),
)
MANUAL_KINDS = {'deduction': 'خصم', 'addition': 'استحقاق إضافي'}
MAX_MANUAL_ITEMS = 10
MAX_AMOUNT = Decimal('9999999.99')
FORM_DEDUCTION_SLOTS = 3  # عدد صفوف «خصم» الفارغة في نموذج التصفية المطبوع


def _to_decimal(raw, label, errors):
    text = str(raw or '').strip().replace(',', '')
    if text == '':
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        errors.append(f'{label}: قيمة غير صالحة.')
        return None
    if value < 0:
        errors.append(f'{label}: لا يمكن أن تكون سالبة.')
        return None
    if value > MAX_AMOUNT:
        errors.append(f'{label}: القيمة كبيرة جداً.')
        return None
    return value.quantize(Decimal('0.01'))


def parse_override_post(post, user, base_financials):
    """يقرأ نموذج التعديل. يُرجع (override, errors).

    يحفظ فقط الخصومات التي تختلف قيمتها عن المحسوبة تلقائياً، ويشترط سبباً
    مكتوباً عند وجود أي تعديل أو بند يدوي.
    """
    errors = []
    override = {}
    for field, label in DEDUCTION_FIELDS:
        value = _to_decimal(post.get(f'ov_{field}'), label, errors)
        if value is None:
            continue
        if value != Decimal(str(base_financials.get(field) or 0)).quantize(Decimal('0.01')):
            override[field] = str(value)

    labels = post.getlist('manual_label')
    amounts = post.getlist('manual_amount')
    kinds = post.getlist('manual_kind')
    items = []
    for index, raw_label in enumerate(labels[:MAX_MANUAL_ITEMS]):
        label = (raw_label or '').strip()
        raw_amount = amounts[index] if index < len(amounts) else ''
        if not label and not str(raw_amount).strip():
            continue  # صف فارغ
        kind = kinds[index] if index < len(kinds) else 'deduction'
        if kind not in MANUAL_KINDS:
            errors.append('نوع البند اليدوي غير صالح.')
            continue
        if not label:
            errors.append('اكتب بياناً لكل بند يدوي.')
            continue
        amount = _to_decimal(raw_amount, f'مبلغ «{label[:30]}»', errors)
        if amount is None or amount == 0:
            if not errors:
                errors.append(f'أدخل مبلغاً أكبر من صفر للبند «{label[:30]}».')
            continue
        items.append({'label': label[:120], 'amount': str(amount), 'kind': kind})
    if items:
        override['manual_items'] = items

    reason = (post.get('ov_reason') or '').strip()
    if override and not reason:
        errors.append('اكتب سبب التعديل (إلزامي عند تغيير أي رقم أو إضافة بند).')
    if override:
        override['reason'] = reason[:500]
        override['edited_by'] = getattr(user, 'get_full_name', lambda: '')() or user.get_username()
        override['edited_by_id'] = user.pk
        override['edited_at'] = timezone.now().isoformat(timespec='seconds')
    return override, errors


def get_override(payload):
    value = (payload or {}).get(OVERRIDE_KEY)
    return value if isinstance(value, dict) else {}


def manual_totals(override):
    """(إجمالي الخصومات اليدوية، إجمالي الاستحقاقات اليدوية)."""
    deductions = additions = Decimal('0')
    for item in override.get('manual_items') or []:
        amount = Decimal(str(item.get('amount') or 0))
        if item.get('kind') == 'addition':
            additions += amount
        else:
            deductions += amount
    return deductions, additions


def apply_override_to_financials(financials, override):
    """نسخة من بنود compute_settlement_financials بعد تطبيق التعديل.

    تُضاف المفاتيح: manual_deductions, manual_additions, manual_items.
    """
    result = dict(financials)
    if not override:
        result.setdefault('manual_deductions', Decimal('0'))
        result.setdefault('manual_additions', Decimal('0'))
        result.setdefault('manual_items', [])
        return result
    for field, _label in DEDUCTION_FIELDS:
        if field in override:
            result[field] = Decimal(str(override[field]))
    manual_ded, manual_add = manual_totals(override)
    result['manual_deductions'] = manual_ded
    result['manual_additions'] = manual_add
    result['manual_items'] = list(override.get('manual_items') or [])
    result['total_deductions'] = (
        sum((Decimal(str(result.get(f) or 0)) for f, _ in DEDUCTION_FIELDS), Decimal('0'))
        + manual_ded
    ).quantize(Decimal('0.01'))
    return result


def apply_override_to_form_context(context, override):
    """يطبّق التعديل على سياق نموذج التصفية المطبوع ويعيد حساب الصافي."""
    override = override or {}

    def num(key):
        try:
            return Decimal(str(context.get(key) or '0'))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0')

    for field, _label in DEDUCTION_FIELDS:
        if field in override:
            context[field] = str(Decimal(str(override[field])))
    manual_ded, manual_add = manual_totals(override)
    context['manual_items'] = list(override.get('manual_items') or [])
    context['override_reason'] = override.get('reason', '')
    # الخصومات الأخرى + البنود اليدوية تُعبَّأ في صفوف «خصم 1..3» الفارغة في النموذج
    entries = []
    for field, label in DEDUCTION_FIELDS:
        if field in ('loans_deduction', 'absences_deduction'):
            continue  # لها صفوف ثابتة في النموذج
        amount = num(field)
        if amount > 0:
            entries.append((amount, label))
    for item in override.get('manual_items') or []:
        if item.get('kind') != 'addition':
            entries.append((Decimal(str(item.get('amount') or 0)), item.get('label', '')))
    if len(entries) > FORM_DEDUCTION_SLOTS:
        head = entries[:FORM_DEDUCTION_SLOTS - 1]
        tail = entries[FORM_DEDUCTION_SLOTS - 1:]
        entries = head + [(sum((a for a, _ in tail), Decimal('0')), ' + '.join(l for _, l in tail))]
    slots = [{'amount': f'{a:.2f}', 'label': l} for a, l in entries]
    slots += [{'amount': '', 'label': ''}] * (FORM_DEDUCTION_SLOTS - len(slots))
    context['deduction_slots'] = slots
    context['manual_additions_items'] = [i for i in context['manual_items'] if i.get('kind') == 'addition']

    slots_total = sum((a for a, _ in entries), Decimal('0'))
    gross = num('eosb_amount') + num('leave_comp') + num('prorated_salary') + num('penalty_amount') + manual_add
    fixed_deductions = num('loans_deduction') + num('absences_deduction')
    net = gross - fixed_deductions - slots_total
    context['total_entitlement'] = str(net.quantize(Decimal('0.01')))
    # أساس سكربت الصفحة: الصافي قبل صفوف «خصم 1..3» (حتى لا تُطرح مرتين عند تعديلها)
    context['net_base'] = str((net + slots_total).quantize(Decimal('0.01')))
    return context
