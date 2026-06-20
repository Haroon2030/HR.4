"""
دوال مساعدة لواجهات الويب — Web Views Helpers
===============================================
أدوات مشتركة تُستخدم من قِبل Views الويب:

1. Decorators:
   - general_manager_required — مدير عام أو مدير موارد
   - employee_branch_access_required — صلاحية فرع الموظف

2. دوال فحص الأدوار:
   - _is_branch_manager — مدير فرع؟
   - _is_general_manager — مدير عام / مدير موارد؟
   - _is_hr_officer — موظف موارد؟
   - _can_act_at_stage — صلاحية مرحلة الموافقات
"""
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from functools import wraps

from apps.core.models import Role


# ══════════════════════════════════════════════════════════════════════════════
# دوال فحص الأدوار
# ══════════════════════════════════════════════════════════════════════════════

def _is_branch_manager(user):
    """
    هل المستخدم مدير فرع؟ 
    يكون مديراً إذا كان يدير فرعاً واحداً على الأقل (عبر managed_branches).
    السوبر يوزر يُعتبر مديراً لكل الفروع.
    """
    return (
        user.is_superuser
        or user.managed_branches.filter(is_deleted=False).exists()
    )


def _is_branch_accountant(user):
    """هل المستخدم محاسب فرع (دور BRANCH_ACCOUNTANT)؟"""
    from apps.employees.services.cash_shortage_access import is_branch_accountant
    return is_branch_accountant(user) or user.is_superuser


def filter_employees_queryset_for_user(user, queryset):
    """Restrict employee queryset to branches the user may access."""
    branch_ids = _user_accessible_branch_ids(user)
    if branch_ids is None:
        return queryset
    return queryset.filter(branch_id__in=branch_ids)


def _user_accessible_branch_ids(user):
    """Delegates to centralized branch scoping (see access_control)."""
    from apps.core.services.access_control import get_accessible_branch_ids

    return get_accessible_branch_ids(user)


def get_active_employee_or_redirect(request, employee_id):
    """
    يجلب موظفاً نشطاً (غير محذوف) أو يُعيد توجيهاً لقائمة الموظفين مع رسالة.
    يُرجع (employee, None) أو (None, HttpResponseRedirect).
    """
    from apps.employees.models import Employee

    try:
        return Employee.objects.get(pk=employee_id), None
    except Employee.DoesNotExist:
        pass

    row = Employee.all_objects.filter(pk=employee_id).only('id', 'name', 'is_deleted').first()
    if row and row.is_deleted:
        messages.warning(request, f'ملف الموظف «{row.name}» محذوف ولا يمكن عرضه.')
    else:
        messages.error(request, 'الموظف غير موجود.')
    return None, redirect('web:list_employees')


def employee_branch_access_required(view_func):
    """
    Decorator: يمنع الوصول لملف الموظف ما لم يكن المستخدم:
      - admin / superuser
      - أو مدير فرع الموظف
      - أو مدير إدارة الموظف
      - أو أخصائي مُعيّن على فرع الموظف

    يعتمد على أن مسار الـ URL يتضمن مجموعة اسمها ``employee_id`` (مثل
    ``<int:employee_id>`` أو ``…/<str:form_type>/<int:employee_id>/``).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        from apps.employees.models import Employee
        employee_id = kwargs.get('employee_id')
        if employee_id is None and kwargs.get('statement_id') is not None:
            from apps.employees.models import EmployeeStatement
            statement = get_object_or_404(EmployeeStatement, id=kwargs['statement_id'])
            employee_id = statement.employee_id
            kwargs['employee_id'] = employee_id
        if employee_id is None:
            from django.http import Http404
            raise Http404('employee_id غير موجود في الرابط')
        employee, missing_resp = get_active_employee_or_redirect(request, employee_id)
        if missing_resp is not None:
            return missing_resp
        if (
            employee.administration_id
            and request.user.managed_administrations.filter(id=employee.administration_id).exists()
        ):
            return view_func(request, *args, **kwargs)
        accessible = _user_accessible_branch_ids(request.user)
        if accessible is not None and employee.branch_id not in accessible:
            messages.error(request, 'لا تملك صلاحية على فرع هذا الموظف.')
            return redirect('web:list_employees')
        return view_func(request, *args, **kwargs)
    return wrapper


def _can_review_action(user, action):
    """
    هل يستطيع المستخدم الموافقة/الرفض على طلب معيّن؟
    يُستخدم في المرحلة الأولى (مدير الفرع).
    """
    from apps.core.services.approval_routing import user_can_first_approve
    return user_can_first_approve(user, action)


# ══════════════════════════════════════════════════════════════════════════════
# دورة الموافقات متعددة المراحل — فحص الصلاحيات
# ══════════════════════════════════════════════════════════════════════════════

def _user_role_type(user):
    """يُرجع نوع دور المستخدم (role_type) أو None إذا بدون دور."""
    profile = getattr(user, 'profile', None)
    if profile and profile.role:
        return profile.role.role_type
    return None


def _is_general_manager(user):
    """
    هل المستخدم مدير عام؟
    المدير العام = superuser أو دور admin أو دور hr_manager.
    هؤلاء هم من يرون كل الطلبات ويوافقون في مرحلة PENDING_GM.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    rt = _user_role_type(user)
    return rt in {Role.RoleType.ADMIN, Role.RoleType.HR_MANAGER}


def _is_hr_officer(user):
    """
    هل المستخدم موظف موارد؟
    موظف الموارد = الذي يستلم المهام المُسندة من المدير العام وينفّذها.
    """
    if not user.is_authenticated:
        return False
    return _user_role_type(user) == Role.RoleType.HR_OFFICER


def _can_act_at_stage(user, action, stage):
    """
    هل يحق للمستخدم اتخاذ قرار (موافقة/إرجاع) في مرحلة معينة؟
    يتطلب صلاحية operations.* المناسبة + نطاق الدور/الفرع.
    """
    from apps.core.models import PendingAction
    from apps.core.services.workflow_access import stage_permission_required

    if user.is_superuser:
        return True

    if not stage_permission_required(user, stage):
        return False

    if stage == PendingAction.Stage.BRANCH:
        if action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
            from apps.employees.services.cash_shortage_access import user_can_approve_cash_shortage
            return user_can_approve_cash_shortage(user, action)
        return _can_review_action(user, action)

    if stage == PendingAction.Stage.GM:
        return True

    if stage == PendingAction.Stage.OFFICER:
        return action.assigned_officer_id == user.id

    return False


def _role_ok_at_stage(user, action, stage):
    """نطاق الدور/الفرع للمرحلة — بدون فحص صلاحية operations.*."""
    from apps.core.models import PendingAction

    if stage == PendingAction.Stage.BRANCH:
        if action.action_type == PendingAction.ActionType.CASH_SHORTAGE:
            from apps.employees.services.cash_shortage_access import user_can_approve_cash_shortage
            return user_can_approve_cash_shortage(user, action)
        return _can_review_action(user, action)
    if stage == PendingAction.Stage.GM:
        return True
    if stage == PendingAction.Stage.OFFICER:
        return action.assigned_officer_id == user.id
    return False


def _can_return_at_stage(user, action, stage):
    """إرجاع الطلب — operations.return + نطاق المرحلة."""
    from apps.core.models import Permission
    from apps.core.services.workflow_access import can_return_operation

    if user.is_superuser:
        return True
    if not stage or not _role_ok_at_stage(user, action, stage):
        return False
    return can_return_operation(user)


def general_manager_required(view_func):
    """Decorator: يتطلب أن يكون المستخدم مديراً عاماً أو مدير موارد."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        if _is_general_manager(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'هذه الصفحة متاحة للمدير العام / مدير الموارد فقط')
        return redirect('web:dashboard')
    return wrapper
