from django import template

from apps.payroll.models import PayrollRun
from apps.setup.models import Sponsorship

register = template.Library()


def _sponsorship_name(sponsorship) -> str:
    if not sponsorship:
        return ''
    return (getattr(sponsorship, 'company_name', None) or '').strip()


@register.simple_tag
def payroll_sponsorship_scope_label(
    run,
    all_sponsorships_selected=False,
    filtered_sponsorship_ids=None,
):
    """
    تسمية عمود شركة الكفالة في جدول المسيرات:
    - جميع الشركات (بدون فلتر كفالة) → «جميع الشركات»
    - شركة واحدة → اسم شركة الكفالة
    - مسير مرتبط بكفالة → اسم الكفالة
    """
    if not run or run.salary_mode != PayrollRun.SalaryMode.TRANSFER:
        return ''

    if all_sponsorships_selected:
        return 'جميع الشركات'

    sponsorship = getattr(run, 'sponsorship', None)
    name = _sponsorship_name(sponsorship)
    if name:
        return name

    ids = [int(x) for x in (filtered_sponsorship_ids or []) if x]
    if len(ids) == 1:
        sp = Sponsorship.objects.filter(pk=ids[0], is_deleted=False).first()
        name = _sponsorship_name(sp)
        if name:
            return name

    return 'جميع الشركات'


@register.simple_tag
def payroll_sponsorship_filter_label(
    all_sponsorships_selected=False,
    filtered_sponsorship_ids=None,
    sponsorships=None,
):
    """تسمية الكفالة في صف المسير الموحّد (بدون سجل مسير محدد)."""
    if all_sponsorships_selected:
        return 'جميع الشركات'

    ids = [int(x) for x in (filtered_sponsorship_ids or []) if x]
    if len(ids) == 1:
        if sponsorships:
            for sp in sponsorships:
                if sp.id == ids[0]:
                    name = _sponsorship_name(sp)
                    if name:
                        return name
        sp = Sponsorship.objects.filter(pk=ids[0], is_deleted=False).first()
        name = _sponsorship_name(sp)
        if name:
            return name

    if len(ids) > 1:
        return f'{len(ids)} شركات'

    return 'جميع الشركات'
