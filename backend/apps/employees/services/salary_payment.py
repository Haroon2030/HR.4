"""
توزيع الراتب بين النقدي والتحويل البنكي — متوافق مع مسير الرواتب.

القاعدة المعتمدة:
  • موظف بكفالة → الراتب كله تحويل بنكي (مسير التحويل).
  • موظف بدون كفالة → الراتب كله نقدي (مسير النقدي).
"""
from __future__ import annotations

from decimal import Decimal


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'))


def payroll_salary_mode_for_employee(employee) -> str:
    """transfer إن وُجدت كفالة، وإلا cash — يطابق PayrollRun.SalaryMode."""
    if getattr(employee, 'sponsorship_id', None):
        return 'transfer'
    return 'cash'


def payroll_salary_mode_label(employee) -> str:
    mode = payroll_salary_mode_for_employee(employee)
    if mode == 'transfer':
        name = ''
        sponsorship = getattr(employee, 'sponsorship', None)
        if sponsorship is not None:
            name = getattr(sponsorship, 'company_name', '') or ''
        if name:
            return f'تحويل بنكي كامل — {name}'
        return 'تحويل بنكي كامل (موظف بكفالة)'
    return 'صرف نقدي كامل (بدون كفالة)'


def is_bank_transfer_employee(employee) -> bool:
    return payroll_salary_mode_for_employee(employee) == 'transfer'


def account_type_export_label(employee) -> str:
    """تسمية طبيعة الحساب للتصدير — فارغة للموظف النقدي."""
    if not is_bank_transfer_employee(employee):
        return ''
    code = (getattr(employee, 'account_type', None) or '').strip()
    if not code:
        return ''
    return employee.get_account_type_display()


def contract_bank_transfer_amount(employee) -> Decimal:
    """مبلغ العقد المخصص للتحويل — كامل الإجمالي إن وُجدت كفالة."""
    gross = Decimal(getattr(employee, 'total_salary', 0) or 0)
    if is_bank_transfer_employee(employee):
        return _q(gross)
    return Decimal('0')


def split_net_by_payment_mode(
    net_salary: Decimal | int | float | str | None,
    employee,
) -> tuple[Decimal, Decimal]:
    """
    يوزّع الصافي حسب الكفالة:
      بكفالة → (0, صافي)  |  بدون كفالة → (صافي, 0)
    """
    net = _q(Decimal(net_salary or 0))
    if net <= 0:
        return Decimal('0'), Decimal('0')
    if is_bank_transfer_employee(employee):
        return Decimal('0'), net
    return net, Decimal('0')


def normalize_salary_payment_fields(cleaned: dict, instance=None) -> dict:
    """
    يطبّق قواعد الصرف على cleaned_data قبل الحفظ.
    يُصفّر cash_amount (لم يعد يُستخدم كبدل منفصل).
    """
    sponsorship = cleaned.get('sponsorship')
    if sponsorship is None and instance is not None and getattr(instance, 'pk', None):
        sponsorship = getattr(instance, 'sponsorship', None)

    if 'cash_amount' in cleaned:
        cleaned['cash_amount'] = Decimal('0')

    if sponsorship:
        return cleaned

    if 'bank' in cleaned:
        cleaned['bank'] = None
    if 'iban' in cleaned:
        cleaned['iban'] = ''
    if 'account_type' in cleaned:
        cleaned['account_type'] = ''
    return cleaned


def validate_salary_payment_fields(form, cleaned: dict, instance=None) -> None:
    """تحقق: بكفالة يتطلب بنك+آيبان؛ بدون كفالة لا يُسمح ببقاء بيانات بنك."""
    sponsorship = cleaned.get('sponsorship')
    if sponsorship is None and instance is not None and getattr(instance, 'pk', None):
        sponsorship = getattr(instance, 'sponsorship', None)

    bank = cleaned.get('bank')
    if bank is None and instance is not None and getattr(instance, 'pk', None):
        bank = getattr(instance, 'bank', None)
    iban = (cleaned.get('iban') or '').strip()
    if not iban and instance is not None and getattr(instance, 'pk', None):
        iban = (getattr(instance, 'iban', None) or '').strip()

    account_type = (cleaned.get('account_type') or '').strip()
    if not account_type and instance is not None and getattr(instance, 'pk', None):
        account_type = (getattr(instance, 'account_type', None) or '').strip()

    if sponsorship:
        if not bank and 'bank' in form.fields:
            form.add_error('bank', 'الموظف على كفالة — أدخل بيانات البنك للتحويل.')
        if not iban and 'iban' in form.fields:
            form.add_error('iban', 'الموظف على كفالة — أدخل رقم الآيبان للتحويل.')
        if not account_type and 'account_type' in form.fields:
            form.add_error('account_type', 'الموظف على كفالة — اختر طبيعة الحساب.')
        return

    if bank and 'bank' in form.fields:
        form.add_error('bank', 'الموظف بدون كفالة — الصرف نقدي ولا حاجة لبيانات البنك.')
    if iban and 'iban' in form.fields:
        form.add_error('iban', 'الموظف بدون كفالة — الصرف نقدي ولا حاجة للآيبان.')
    if account_type and 'account_type' in form.fields:
        form.add_error('account_type', 'طبيعة الحساب للموظفين على الكفالة فقط.')
