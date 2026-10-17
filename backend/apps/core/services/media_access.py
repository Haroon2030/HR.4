"""التحكم في الوصول لملفات media حسب المسار والفرع والصلاحية."""
from __future__ import annotations

from django.db.models import Q

from apps.core.decorators import has_permission
from apps.core.models import Role
from apps.core.web_views._helpers import _user_accessible_branch_ids

_EMPLOYEE_FILE_FIELDS = (
    'commencement_document',
    'id_document',
    'passport_document',
    'contract_document',
    'other_documents',
)

_EMPLOYMENT_FILE_FIELDS = (
    'commencement_document',
    'id_document',
    'passport_document',
    'contract_document',
    'other_documents',
)


def _is_privileged(user) -> bool:
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if not profile or not profile.role:
        return False
    return profile.role.role_type in (
        Role.RoleType.ADMIN,
        Role.RoleType.HR_MANAGER,
    )


def _branch_allowed(user, branch_id: int | None) -> bool:
    accessible = _user_accessible_branch_ids(user)
    if accessible is None:
        return True
    if branch_id is None:
        return False
    return branch_id in accessible


def _scope_from_employee_file(path: str):
    from apps.employees.models import Employee

    for field in _EMPLOYEE_FILE_FIELDS:
        emp = (
            Employee.all_objects.filter(**{field: path})
            .only('branch_id', 'administration_id').first()
        )
        if emp:
            return emp.branch_id, emp.administration_id
    return None


def _scope_from_employment_file(path: str):
    from apps.employees.models import EmploymentRequest

    q = Q()
    for field in _EMPLOYMENT_FILE_FIELDS:
        q |= Q(**{field: path})
    req = (
        EmploymentRequest.all_objects.filter(q)
        .only('branch_id', 'administration_id').first()
    )
    if req:
        return req.branch_id, req.administration_id
    return None


def _scope_from_related_document(path: str):
    from apps.employees.models import (
        EmployeeAbsence,
        EmployeeBusinessTrip,
        EmployeeCashShortage,
        EmployeeCustody,
        EmployeeJobOffer,
        EmployeeLeave,
        EmployeeLoan,
        EmployeeStatement,
    )

    cs = (
        EmployeeCashShortage.objects.filter(document=path)
        .select_related('branch', 'employee')
        .first()
    )
    if cs:
        emp = cs.employee if cs.employee_id else None
        return (
            cs.branch_id or (emp.branch_id if emp else None),
            emp.administration_id if emp else None,
        )

    for model in (
        EmployeeLeave,
        EmployeeStatement,
        EmployeeLoan,
        EmployeeAbsence,
        EmployeeJobOffer,
        EmployeeBusinessTrip,
    ):
        obj = model.objects.filter(document=path).select_related('employee').first()
        if obj and obj.employee_id:
            return obj.employee.branch_id, obj.employee.administration_id

    custody = (
        EmployeeCustody.objects.filter(Q(document=path) | Q(return_document=path))
        .select_related('employee')
        .first()
    )
    if custody and custody.employee_id:
        return custody.employee.branch_id, custody.employee.administration_id
    return None


def scope_for_media_path(path: str):
    """(branch_id, administration_id) لمالك الملف، أو None إن لم يُعرف المالك."""
    if path.startswith('company/') or path.startswith('avatars/'):
        return None

    for resolver in (
        _scope_from_employee_file,
        _scope_from_employment_file,
        _scope_from_related_document,
    ):
        scope = resolver(path)
        if scope is not None:
            return scope

    from apps.core.models import PendingAction

    pending = (
        PendingAction.objects.filter(attachment=path)
        .select_related('employee')
        .first()
    )
    if pending:
        emp = pending.employee if pending.employee_id else None
        return (
            (emp.branch_id if emp else None) or pending.branch_id,
            (emp.administration_id if emp else None) or pending.administration_id,
        )
    return None


def branch_id_for_media_path(path: str) -> int | None:
    """يُرجع branch_id المرتبط بالملف، أو None إن لم يُعرف."""
    scope = scope_for_media_path(path)
    return scope[0] if scope else None


def _scope_allowed(user, path: str) -> bool:
    """نفس منطق الوصول لملف الموظف: نطاق الإدارة ثم الفرع."""
    from apps.core.services.access_control import get_scoped_administration_ids

    scope = scope_for_media_path(path)
    if scope is None:
        return False
    branch_id, administration_id = scope

    scoped_admins = get_scoped_administration_ids(user)
    if scoped_admins is not None:
        return administration_id in scoped_admins
    if administration_id and user.managed_administrations.filter(id=administration_id).exists():
        return True
    return _branch_allowed(user, branch_id)


def user_may_access_media_path(user, path: str) -> bool:
    if not user.is_authenticated:
        return False
    if _is_privileged(user):
        return True

    if path.startswith('company/'):
        return has_permission(user, 'users.view') or has_permission(user, 'employees.view')

    if path.startswith('avatars/'):
        profile = getattr(user, 'profile', None)
        if profile and profile.avatar and path in str(profile.avatar):
            return True
        from apps.core.models import UserProfile
        from apps.core.services.access_control import can_view_user

        owner = (
            UserProfile.objects.filter(avatar=path)
            .select_related('user')
            .first()
        )
        if owner and has_permission(user, 'users.edit') and can_view_user(user, owner.user):
            return True
        return False

    if path.startswith('pending_actions/') or path.startswith('HR/pending_actions/'):
        if not (
            has_permission(user, 'employees.view')
            or has_permission(user, 'cash_shortages.view')
        ):
            return False
        return _scope_allowed(user, path)

    if path.startswith('employees/') or path.startswith('HR/employees/'):
        if not (
            has_permission(user, 'employees.view')
            or has_permission(user, 'cash_shortages.view')
        ):
            return False
        return _scope_allowed(user, path)

    if path.startswith('employment_requests/') or path.startswith('HR/employment_requests/'):
        if not has_permission(user, 'employees.view'):
            return False
        return _scope_allowed(user, path)

    return False
