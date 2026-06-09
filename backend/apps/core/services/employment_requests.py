"""دورة الموافقات الثلاثية لطلبات التوظيف.

نفس منطق `pending_actions` ولكن لكائن `EmploymentRequest` (يُنشئ موظفاً جديداً
بدلاً من تعديل موظف موجود).
"""
from django.db import transaction
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services import notifications as notif
from apps.core.services.approval_routing import notify_on_first_stage, resolve_first_approver


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


# ─── التحقق من اكتمال بيانات الموظف قبل الموافقة النهائية ────────────────
# (label, attr) — نستخدم الـ FK suffix `_id` لتجنّب لمس DB لأجل استرجاع الكائن
_REQUIRED_EMPLOYEE_FIELDS = [
    # نصوص أساسية
    ('رقم الهوية', 'id_number', 'str'),
    ('رقم الجوال', 'phone', 'str'),
    ('البريد الإلكتروني', 'email', 'str'),
    ('الرقم الوظيفي', 'employee_number', 'str'),
    # FKs
    ('الجنسية', 'nationality_id', 'fk'),
    ('المهنة', 'profession_id', 'fk'),
    ('الكفالة', 'sponsorship_id', 'fk'),
    # تواريخ
    ('تاريخ المباشرة', 'hire_date', 'date'),
    # راتب (نقبل صفر، نتأكد فقط أنها ليست None)
    ('الراتب الأساسي', 'basic_salary', 'decimal'),
    ('بدل سكن', 'housing_allowance', 'decimal'),
    ('بدل نقل', 'transport_allowance', 'decimal'),
    # مستندات
    ('صورة الهوية', 'id_document', 'file'),
]


def validate_employee_data_complete(req):
    """يرجع قائمة المسميات العربية للحقول الناقصة على طلب التوظيف.

    تُستدعى قبل `officer_approve` لمنع الموافقة النهائية بدون بيانات الموظف.
    """
    missing = []
    for label, attr, kind in _REQUIRED_EMPLOYEE_FIELDS:
        value = getattr(req, attr, None)
        if kind == 'str':
            if not value or not str(value).strip():
                missing.append(label)
        elif kind == 'fk':
            if value is None:
                missing.append(label)
        elif kind == 'date':
            if value is None:
                missing.append(label)
        elif kind == 'decimal':
            if value is None:
                missing.append(label)
        elif kind == 'file':
            if not value:
                missing.append(label)
    return missing


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
    """المرحلة الأولى (إدارة/فرع) توافق → الطلب ينتقل لمدير الموارد."""
    from apps.employees.models import EmploymentRequest
    if req.status not in {EmploymentRequest.Status.PENDING_BRANCH,
                          EmploymentRequest.Status.PENDING}:
        raise ValueError('هذا الطلب ليس في مرحلة الموافقة الأولى.')

    req.status = EmploymentRequest.Status.PENDING_GM
    req.branch_reviewed_by = user
    req.branch_reviewed_at = timezone.now()
    req.branch_notes = notes or ''
    req.save(update_fields=[
        'status', 'branch_reviewed_by', 'branch_reviewed_at', 'branch_notes'
    ])

    decision = resolve_first_approver(req)
    approver_label = decision.stage_label
    _notify_general_managers(
        req,
        title=f'طلب توظيف بانتظار موافقتك — {req.name}',
        message=f'الفرع: {req.branch.name if req.branch else "—"} • وافق عليه {approver_label}',
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

    # ✅ التحقق من اكتمال بيانات الموظف قبل السماح بالموافقة النهائية
    missing = validate_employee_data_complete(req)
    if missing:
        missing_str = '، '.join(missing)
        raise ValueError(
            'لا يمكن إكمال الموافقة قبل تعبئة بيانات الموظف.\n'
            f'الحقول الناقصة: {missing_str}.\n'
            'استخدم زر "تعديل البيانات" لإكمال المعلومات ثم أعد المحاولة.'
        )

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
            # الحقول الأصلية
            name=req.name,
            branch=req.branch,
            department=req.department,
            administration=req.administration,
            cost_center=req.cost_center,
            commencement_document=req.commencement_document,
            employment_request=req,
            status=Employee.Status.ACTIVE,
            # ✅ بيانات الموظف الكاملة المنسوخة من الطلب
            gender=req.gender or Employee.Gender.MALE,
            id_number=req.id_number,
            phone=req.phone,
            email=req.email,
            employee_number=req.employee_number,
            nationality=req.nationality,
            profession=req.profession,
            sponsorship=req.sponsorship,
            insurance=req.insurance,
            insurance_class=req.insurance_class,
            housing=req.housing,
            hire_date=req.hire_date,
            medical_insurance_expiry_date=req.medical_insurance_expiry_date,
            contract_expiry_date=req.contract_expiry_date,
            health_card_status=req.health_card_status or Employee.HealthCardStatus.NOT_AVAILABLE,
            health_card_expiry=req.health_card_expiry,
            basic_salary=req.basic_salary,
            housing_allowance=req.housing_allowance,
            transport_allowance=req.transport_allowance,
            other_allowance=req.other_allowance,
            cash_amount=req.cash_amount,
            meal_allowance=req.meal_allowance,
            insurance_deduction_rate=req.insurance_deduction_rate,
            bank=req.bank,
            iban=req.iban or '',
            account_type=req.account_type or '',
            id_document=req.id_document,
            passport_document=req.passport_document,
            contract_document=req.contract_document,
            other_documents=req.other_documents,
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
    notify_on_first_stage(
        req,
        title=f'طلب توظيف جديد بانتظار موافقتك — {req.name}',
        message=f'الفرع: {req.branch.name if req.branch else "—"}',
        icon='user-plus',
        color=Notification.Color.PRIMARY,
    )
