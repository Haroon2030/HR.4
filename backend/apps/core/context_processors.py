"""
معالجات سياق القوالب — Context Processors
==========================================
هذه الدوال تُضاف تلقائياً لكل صفحة في النظام عبر إعدادات TEMPLATES.
تُوفر بيانات مشتركة لكل القوالب بدون الحاجة لتمريرها يدوياً من كل View.

المتغيرات التي تُضاف:
  - pending_actions_count: عدد الطلبات المعلّقة (لشارة القائمة الجانبية)
  - pending_for_me_count: عدد الطلبات التي تحتاج إجراء من المستخدم الحالي
  - unread_notifications_count: عدد الإشعارات غير المقروءة

⚠️ هذه الدوال تُنفَّذ في كل طلب HTTP — لذلك يجب أن تكون سريعة وخفيفة.
"""
import logging
from django.db.models import Q

logger = logging.getLogger(__name__)


def _pending_statuses():
    """الحالات التي تُعتبر 'معلّقة' لـ PendingAction."""
    from apps.core.models import PendingAction
    return [
        PendingAction.Status.PENDING_BRANCH,   # بانتظار مدير الفرع
        PendingAction.Status.PENDING_GM,        # بانتظار المدير العام
        PendingAction.Status.PENDING_OFFICER,   # بانتظار موظف الموارد
    ]


def _hire_pending_statuses():
    """الحالات التي تُعتبر 'معلّقة' لطلبات التوظيف."""
    from apps.employees.models import EmploymentRequest
    return [
        EmploymentRequest.Status.PENDING_BRANCH,
        EmploymentRequest.Status.PENDING_GM,
        EmploymentRequest.Status.PENDING_OFFICER,
    ]


def pending_actions_count(request):
    """
    إجمالي الطلبات المعلّقة الظاهرة لهذا المستخدم.
    يُستخدم لعرض الرقم في شارة (badge) القائمة الجانبية.

    يشمل:
      - PendingAction (إجازات، سلف، غياب، نقل، تصفية، إلخ)
      - EmploymentRequest (طلبات التوظيف)

    المتغير الناتج: {{ pending_actions_count }}
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from apps.core.models import PendingAction
        from apps.employees.models import EmploymentRequest

        # ── عدّاد PendingAction ──
        qs = PendingAction.objects.filter(status__in=_pending_statuses())
        if user.is_superuser:
            # السوبر يوزر يرى كل الطلبات
            pa_count = qs.count()
        else:
            # غير السوبر يوزر: يرى فقط طلباته + طلبات فروعه + المُسندة إليه
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            f = Q(requested_by=user) | Q(assigned_officer=user)
            if managed_ids:
                f |= Q(branch_id__in=managed_ids)
            pa_count = qs.filter(f).distinct().count()

        # ── عدّاد طلبات التوظيف ──
        qs_hire = EmploymentRequest.objects.filter(status__in=_hire_pending_statuses())
        if user.is_superuser:
            hire_count = qs_hire.count()
        else:
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            f2 = Q(requested_by=user) | Q(assigned_officer=user)
            if managed_ids:
                f2 |= Q(branch_id__in=managed_ids)
            hire_count = qs_hire.filter(f2).distinct().count()

        # المجموع الكلي
        return {'pending_actions_count': pa_count + hire_count}
    except Exception as e:
        logger.warning("pending_actions_count context failed: %s", e)
        return {'pending_actions_count': 0}


def approval_inbox(request):
    """
    عدد الطلبات التي تنتظر إجراءً من المستخدم الحالي + عدد الإشعارات غير المقروءة.

    يختلف عن pending_actions_count في أنه يُظهر فقط الطلبات التي يجب
    على المستخدم الحالي اتخاذ قرار بشأنها (حسب دوره ومرحلة الطلب).

    مثال:
      - مدير فرع يرى فقط الطلبات في مرحلة PENDING_BRANCH لفروعه
      - المدير العام يرى فقط PENDING_GM
      - موظف الموارد يرى فقط PENDING_OFFICER المُسندة إليه

    المتغيرات الناتجة:
      {{ pending_for_me_count }}        — الطلبات المنتظرة
      {{ unread_notifications_count }}  — الإشعارات غير المقروءة
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    try:
        from apps.core.models import PendingAction, Notification
        from apps.employees.models import EmploymentRequest
        from apps.core.web_views._helpers import (
            _is_branch_manager, _is_general_manager, _is_hr_officer,
        )

        # ── صندوق وارد PendingAction ──
        f = Q()

        # المدير العام / مدير الموارد يرى الطلبات بمرحلة المدير العام
        if user.is_superuser or _is_general_manager(user):
            f |= Q(status=PendingAction.Status.PENDING_GM)

        # مدير الفرع يرى طلبات فروعه فقط في مرحلة مدير الفرع
        if _is_branch_manager(user):
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            if managed_ids:
                f |= Q(status=PendingAction.Status.PENDING_BRANCH, branch_id__in=managed_ids)

        # السوبر يوزر يرى كل المراحل
        if user.is_superuser:
            f |= Q(status=PendingAction.Status.PENDING_BRANCH)

        # موظف الموارد يرى الطلبات المُسندة إليه
        if _is_hr_officer(user):
            f |= Q(status=PendingAction.Status.PENDING_OFFICER, assigned_officer=user)
        elif user.is_superuser:
            f |= Q(status=PendingAction.Status.PENDING_OFFICER)

        # الطلبات المرتجعة للأخصائي (مقدّم الطلب)
        f |= Q(status=PendingAction.Status.RETURNED, requested_by=user)
        pa_count = PendingAction.objects.filter(f).distinct().count()

        # ── صندوق وارد طلبات التوظيف ──
        f2 = Q()
        if user.is_superuser or _is_general_manager(user):
            f2 |= Q(status=EmploymentRequest.Status.PENDING_GM)
        if _is_branch_manager(user):
            managed_ids = list(user.managed_branches.values_list('id', flat=True))
            if managed_ids:
                f2 |= Q(status=EmploymentRequest.Status.PENDING_BRANCH, branch_id__in=managed_ids)
        if user.is_superuser:
            f2 |= Q(status=EmploymentRequest.Status.PENDING_BRANCH)
        if _is_hr_officer(user) or user.is_superuser:
            f2 |= (
                Q(status=EmploymentRequest.Status.PENDING_OFFICER, assigned_officer=user)
                if not user.is_superuser
                else Q(status=EmploymentRequest.Status.PENDING_OFFICER)
            )
        hire_count = EmploymentRequest.objects.filter(f2).distinct().count() if f2 else 0

        # عدد الإشعارات غير المقروءة
        unread = Notification.objects.filter(recipient=user, is_read=False).count()

        return {
            'pending_for_me_count': pa_count + hire_count,
            'unread_notifications_count': unread,
        }
    except Exception as e:
        logger.warning("approval_inbox context failed: %s", e)
        return {
            'pending_for_me_count': 0,
            'unread_notifications_count': 0,
        }
