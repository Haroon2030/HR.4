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
    - مسير مرتبط بكفالة → اسم الكفالة دائماً (حتى مع خيار «جميع الشركات»)
    - شركة واحدة في الفلتر → اسم شركة الكفالة
    - غير ذلك → «جميع الشركات»
    """
    if not run or run.salary_mode != PayrollRun.SalaryMode.TRANSFER:
        return ''

    sponsorship = getattr(run, 'sponsorship', None)
    name = _sponsorship_name(sponsorship)
    if name:
        return name

    if all_sponsorships_selected:
        return 'جميع الشركات'

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


@register.simple_tag
def payroll_sponsorship_names(runs, all_sponsorships_selected=False, filtered_sponsorship_ids=None, sponsorships=None):
    """
    أسماء شركات الكفالة في صف المسير الموحّد (بدل عبارة «جميع الشركات» العامة):
    الشركات التي لها مسيرات في هذه الفترة، وإلا شركات الفلتر المختارة.
    قائمة أسماء فريدة مرتبة؛ فارغة إن تعذّر تحديد الأسماء.
    """
    names = {
        _sponsorship_name(getattr(r, 'sponsorship', None))
        for r in (runs or [])
        if getattr(r, 'sponsorship_id', None)
    }
    if not names:
        ids = {int(x) for x in (filtered_sponsorship_ids or []) if x}
        pool = list(sponsorships or [])
        if all_sponsorships_selected:
            names = {_sponsorship_name(sp) for sp in pool}
        else:
            names = {_sponsorship_name(sp) for sp in pool if sp.id in ids}
    return sorted(n for n in names if n)
