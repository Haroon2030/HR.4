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
    if branch_id is None:
        return False
    accessible = _user_accessible_branch_ids(user)
    if accessible is None:
        return True
    return branch_id in accessible


def _branch_from_employee_file(path: str) -> int | None:
    from apps.employees.models import Employee

    for field in _EMPLOYEE_FILE_FIELDS:
        emp = Employee.all_objects.filter(**{field: path}).only('branch_id').first()
        if emp and emp.branch_id:
            return emp.branch_id
    return None


def _branch_from_employment_file(path: str) -> int | None:
    from apps.employees.models import EmploymentRequest

    q = Q()
    for field in _EMPLOYMENT_FILE_FIELDS:
        q |= Q(**{field: path})
    req = EmploymentRequest.all_objects.filter(q).only('branch_id').first()
    if req and req.branch_id:
        return req.branch_id
    return None


def _branch_from_related_document(path: str) -> int | None:
    from apps.employees.models import (
        EmployeeAbsence,
        EmployeeBusinessTrip,
        EmployeeCustody,
        EmployeeJobOffer,
        EmployeeLeave,
        EmployeeLoan,
        EmployeeStatement,
    )

    for model in (
        EmployeeLeave,
        EmployeeStatement,
        EmployeeLoan,
        EmployeeAbsence,
        EmployeeJobOffer,
        EmployeeBusinessTrip,
    ):
        obj = (
            model.objects.filter(document=path)
            .select_related('employee')
            .only('employee__branch_id')
            .first()
        )
        if obj and obj.employee_id and obj.employee.branch_id:
            return obj.employee.branch_id

    custody = (
        EmployeeCustody.objects.filter(Q(document=path) | Q(return_document=path))
        .select_related('employee')
        .only('employee__branch_id')
        .first()
    )
    if custody and custody.employee_id and custody.employee.branch_id:
        return custody.employee.branch_id
    return None


def branch_id_for_media_path(path: str) -> int | None:
    """يُرجع branch_id المرتبط بالملف، أو None إن لم يُعرف."""
    if path.startswith('company/'):
        return None
    if path.startswith('avatars/'):
        return None

    for resolver in (
        _branch_from_employee_file,
        _branch_from_employment_file,
        _branch_from_related_document,
    ):
        branch_id = resolver(path)
        if branch_id is not None:
            return branch_id

    from apps.core.models import PendingAction

    pending = (
        PendingAction.objects.filter(attachment=path)
        .select_related('employee')
        .only('employee__branch_id')
        .first()
    )
    if pending and pending.employee_id and pending.employee.branch_id:
        return pending.employee.branch_id

    return None


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
        return has_permission(user, 'users.view')

    if path.startswith('pending_actions/'):
        if not has_permission(user, 'employees.view'):
            return False
        branch_id = branch_id_for_media_path(path)
        if branch_id is None:
            return False
        return _branch_allowed(user, branch_id)

    if path.startswith('employees/'):
        if not has_permission(user, 'employees.view'):
            return False
        branch_id = branch_id_for_media_path(path)
        if branch_id is None:
            return False
        return _branch_allowed(user, branch_id)

    if path.startswith('employment_requests/'):
        if not has_permission(user, 'employees.view'):
            return False
        branch_id = branch_id_for_media_path(path)
        if branch_id is None:
            return False
        return _branch_allowed(user, branch_id)

    return False
