"""
دوال مساعدة لواجهات الويب — Web Views Helpers
===============================================
هذا الملف يحتوي على أدوات مشتركة تُستخدم من قِبل كل Views الويب:

1. Decorators لفحص الأدوار:
   - admin_required — يتطلب دور أدمن
   - branch_manager_required — يتطلب أن يكون مدير فرع
   - general_manager_required — يتطلب مدير عام أو مدير موارد
   - hr_officer_required — يتطلب موظف موارد
   - employee_branch_access_required — يتحقق من أن المستخدم له حق الوصول لفرع الموظف

2. دوال فحص الأدوار:
   - _is_branch_manager — هل يدير فرعاً واحداً على الأقل؟
   - _is_general_manager — هل هو مدير عام / مدير موارد / سوبر يوزر؟
   - _is_hr_officer — هل هو موظف موارد؟
   - _can_act_at_stage — هل يحق له اتخاذ قرار في مرحلة معينة من دورة الموافقات؟
"""
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from functools import wraps

from apps.core.models import Role


# ══════════════════════════════════════════════════════════════════════════════
# Decorator: فحص دور الأدمن
# ══════════════════════════════════════════════════════════════════════════════

def admin_required(view_func):
    """
    يتحقق من أن المستخدم لديه دور أدمن أو أنه superuser.
    يُستخدم لحماية صفحات الإدارة العامة (إعدادات، مستخدمين، إلخ).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        
        # السوبر يوزر يمر مباشرة
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # فحص دور الأدمن عبر الـ Profile
        try:
            user_profile = request.user.profile
            if user_profile.role and user_profile.role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
        except Exception as e:
            # المستخدم ليس لديه profile
            pass
        
        messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
        return redirect('web:dashboard')
    return wrapper


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


def _is_administration_manager(user):
    """هل المستخدم مدير إدارة (معيّن على إدارة أو بدور مدير إدارة)؟"""
    if user.is_superuser:
        return True
    if user.managed_administrations.filter(is_deleted=False).exists():
        return True
    profile = getattr(user, 'profile', None)
    return bool(
        profile
        and profile.role
        and profile.role.role_type == Role.RoleType.ADMIN_MANAGER
    )


def branch_manager_required(view_func):
    """Decorator: يتطلب أن يكون المستخدم مدير فرع."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        if _is_branch_manager(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'هذه الصفحة متاحة لمدراء الفروع فقط')
        return redirect('web:dashboard')
    return wrapper


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
        employee = get_object_or_404(Employee, id=employee_id)
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


def hr_officer_required(view_func):
    """Decorator: يتطلب أن يكون المستخدم موظف موارد أو سوبر يوزر."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web:auth:login')
        if _is_hr_officer(request.user) or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'هذه الصفحة متاحة لموظفي الموارد فقط')
        return redirect('web:dashboard')
    return wrapper
