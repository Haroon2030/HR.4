"""توقيف الموظف وإلغاء توقيفه — بزر خاص بمدير الموارد البشرية والسوبر أدمن فقط.

طلبات التصفية لا تُوقِف الموظف؛ الحالة «موقوف» تُضبط من هذا الزر وحده.
"""
from __future__ import annotations


def user_can_suspend_employees(user) -> bool:
    """مدير الموارد البشرية أو السوبر أدمن."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.is_hr_manager)


def toggle_employee_suspension(employee) -> bool:
    """يقلب الحالة بين «موقوف» و«على رأس العمل». يُرجع True إذا أصبح موقوفاً.

    لا يُطبَّق على منتهي الخدمة (ValueError).
    """
    from apps.employees.models import Employee

    if employee.status == Employee.Status.TERMINATED:
        raise ValueError('لا يمكن توقيف موظف منتهي الخدمة.')
    suspend = employee.status != Employee.Status.SUSPENDED
    employee.status = Employee.Status.SUSPENDED if suspend else Employee.Status.ACTIVE
    employee.save(update_fields=['status', 'updated_at'])
    return suspend
