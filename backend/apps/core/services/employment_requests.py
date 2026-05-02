"""دورة الموافقات الثلاثية لطلبات التوظيف.

نفس منطق `pending_actions` ولكن لكائن `EmploymentRequest` (يُنشئ موظفاً جديداً
بدلاً من تعديل موظف موجود).
"""
from django.db import transaction
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services import notifications as notif


# ─── روابط ──────────────────────────────────────────────────────────────────
def employment_request_url(req):
    try:
        return reverse('web:list_employment_requests')
    except NoReverseMatch:
        return ''


def _notify_user(user, req, *, title, message='', icon='user-plus',
                 color=Notification.Color.PRIMARY):
    if not user:
        return
    notif.notify(
        user, title=title, message=message,
        link=employment_request_url(req),
        icon=icon, color=color,
    )


def _notify_branch_manager(req, **kwargs):
    branch = req.branch
    manager = getattr(branch, 'manager', None) if branch else None
    _notify_user(manager, req, **kwargs)


def _notify_general_managers(req, **kwargs):
    from django.contrib.auth import get_user_model
    from apps.core.models import Role
    User = get_user_model()
    users = User.objects.filter(
        is_active=True,
        profile__role__role_type__in=[Role.RoleType.ADMIN, Role.RoleType.HR_MANAGER],
    ).distinct()
    for u in users:
        _notify_user(u, req, **kwargs)


# ─── تحوّلات الحالة ────────────────────────────────────────────────────────
@transaction.atomic
def branch_approve(req, user, notes=''):
    """مدير الفرع يوافق → الطلب ينتقل لمدير الموارد."""
    from apps.employees.models import EmploymentRequest
    if req.status not in {EmploymentRequest.Status.PENDING_BRANCH,
                          EmploymentRequest.Status.PENDING}:
        raise ValueError('هذا الطلب ليس في مرحلة موافقة مدير الفرع.')

    req.status = EmploymentRequest.Status.PENDING_GM
    req.branch_reviewed_by = user
    req.branch_reviewed_at = timezone.now()
    req.branch_notes = notes or ''
    req.save(update_fields=[
        'status', 'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes'
    ])

    _notify_general_managers(
        req,
        title=f'طلب توظيف بانتظار موافقتك — {req.name}',
        message=f'الفرع: {req.branch.name if req.branch else "—"} • وافق عليه مدير الفرع',
        icon='user-cog', color=Notification.Color.AMBER,
    )
    return req


@transaction.atomic
def gm_approve_and_assign(req, user, officer, notes=''):
    """مدير الموارد يوافق ويُسند الطلب لأخصائي."""
    from apps.employees.models import EmploymentRequest
    from apps.core.models import Role

    if req.status != EmploymentRequest.Status.PENDING_GM:
        raise ValueError('هذا الطلب ليس في مرحلة موافقة مدير الموارد.')
    if not officer or not officer.is_active:
        raise ValueError('يجب اختيار أخصائي موارد فعّال للإسناد.')
    profile = getattr(officer, 'profile', None)
    if not profile or not profile.role or profile.role.role_type != Role.RoleType.HR_OFFICER:
        raise ValueError('المستخدم المختار ليس "أخصائي موارد بشرية".')

    now = timezone.now()
    req.status = EmploymentRequest.Status.PENDING_OFFICER
    req.gm_reviewed_by = user
    req.gm_reviewed_at = now
    req.gm_notes = notes or ''
    req.assigned_officer = officer
    req.assigned_at = now
    req.save(update_fields=[
        'status', 'gm_reviewed_by', 'gm_reviewed_at', 'gm_notes',
        'assigned_officer', 'assigned_at'
    ])

    _notify_user(
        officer, req,
        title=f'طلب توظيف مُسند إليك — {req.name}',
        message=f'الفرع: {req.branch.name if req.branch else "—"} • أسنده {user.get_full_name() or user.username}',
        icon='clipboard-check', color=Notification.Color.INDIGO,
    )
    return req


@transaction.atomic
def officer_approve(req, user, notes=''):
    """الأخصائي يوافق → يُنشَأ الموظف فعلياً."""
    from apps.employees.models import EmploymentRequest, Employee

    if req.status != EmploymentRequest.Status.PENDING_OFFICER:
        raise ValueError('هذا الطلب ليس في مرحلة الأخصائي.')
    if req.assigned_officer_id != user.id and not user.is_superuser:
        raise ValueError('هذا الطلب غير مُسند إليك.')

    now = timezone.now()
    req.status = EmploymentRequest.Status.APPROVED
    req.officer_reviewed_at = now
    req.officer_notes = notes or ''
    req.reviewed_by = user
    req.reviewed_at = now
    req.review_notes = notes or ''
    req.save(update_fields=[
        'status', 'officer_reviewed_at', 'officer_notes',
        'reviewed_by', 'reviewed_at', 'review_notes',
    ])

    # إنشاء الموظف فعلياً (إن لم يكن مُنشأ من قبل)
    if not Employee.objects.filter(employment_request=req).exists():
        Employee.objects.create(
            name=req.name,
            branch=req.branch,
            department=req.department,
            cost_center=req.cost_center,
            commencement_document=req.commencement_document,
            employment_request=req,
            status=Employee.Status.ACTIVE,
        )

    # إشعارات الإكمال
    if req.requested_by_id:
        _notify_user(
            req.requested_by, req,
            title=f'تمت الموافقة على طلب توظيف — {req.name}',
            message='تم اعتماد الطلب وإضافة الموظف لقائمة العاملين.',
            icon='check-circle', color=Notification.Color.EMERALD,
        )
    return req


@transaction.atomic
def reject(req, user, notes=''):
    """رفض نهائي للطلب من أي مرحلة."""
    from apps.employees.models import EmploymentRequest
    if req.status in {EmploymentRequest.Status.APPROVED,
                      EmploymentRequest.Status.REJECTED}:
        raise ValueError('لا يمكن تغيير حالة طلب مكتمل.')

    now = timezone.now()
    req.status = EmploymentRequest.Status.REJECTED
    req.reviewed_by = user
    req.reviewed_at = now
    req.review_notes = notes or ''
    req.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])

    if req.requested_by_id:
        _notify_user(
            req.requested_by, req,
            title=f'رُفض طلب التوظيف — {req.name}',
            message=notes or 'تم رفض الطلب.',
            icon='x-circle', color=Notification.Color.RED,
        )
    return req


def notify_branch_on_create(req):
    """يُستدعى مرة واحدة عند إنشاء طلب توظيف جديد."""
    _notify_branch_manager(
        req,
        title=f'طلب توظيف جديد بانتظار موافقتك — {req.name}',
        message=f'الفرع: {req.branch.name if req.branch else "—"}',
        icon='user-plus', color=Notification.Color.PRIMARY,
    )
