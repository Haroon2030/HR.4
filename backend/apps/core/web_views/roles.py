"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from functools import wraps

from apps.core.models import Role
from apps.core.forms import RoleForm
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    admin_required, _is_branch_manager, branch_manager_required,
    _user_accessible_branch_ids, employee_branch_access_required, _can_review_action,
)
from apps.core.decorators import permission_required

@login_required
@permission_required('users.view')
def list_roles(request):
    """قائمة الأدوار"""
    roles = Role.objects.all().prefetch_related('users')
    return render(request, 'pages/roles/list.html', {'roles': roles})

@login_required
@permission_required('users.view')
def view_role(request, role_id):
    """عرض تفاصيل دور معين"""
    from django.shortcuts import get_object_or_404
    role = get_object_or_404(Role, id=role_id)
    return render(request, 'pages/roles/detail.html', {'role': role})

@login_required
@permission_required('users.edit')
def edit_role(request, role_id):
    """تعديل دور (يشمل تعديل الصلاحيات في نفس الصفحة)"""
    from django.shortcuts import get_object_or_404
    from apps.core.models import AppModule, Permission

    role = get_object_or_404(Role, id=role_id)
    is_admin_role = role.role_type == Role.RoleType.ADMIN

    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            # حفظ الصلاحيات (إلا للأدمن — صلاحياته ثابتة)
            if not is_admin_role:
                selected_ids = request.POST.getlist('permissions')
                try:
                    selected_ids = [int(x) for x in selected_ids if str(x).isdigit()]
                except (TypeError, ValueError):
                    selected_ids = []
                perms = Permission.objects.filter(id__in=selected_ids, is_active=True)
                role.permissions.set(perms)
                messages.success(
                    request,
                    f'تم تحديث الدور "{role.name}" وحفظ {perms.count()} صلاحية'
                )
            else:
                messages.success(request, f'تم تحديث الدور "{role.name}" بنجاح')
            return redirect('web:list_roles')
        for err in form.errors.values():
            messages.error(request, err[0])

    # بناء جدول الصلاحيات (وحدات × عمليات)
    modules = AppModule.objects.filter(is_active=True).prefetch_related('permissions')
    operations = list(Permission.Operation.choices)
    role_perm_ids = set(role.permissions.values_list('id', flat=True))

    matrix = []
    for m in modules:
        cells = []
        for op_code, op_label in operations:
            perm = next((p for p in m.permissions.all() if p.operation == op_code and p.is_active), None)
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'checked': bool(perm and (is_admin_role or perm.id in role_perm_ids)),
                'available': perm is not None,
            })
        matrix.append({'module': m, 'cells': cells})

    return render(request, 'pages/roles/form.html', {
        'role': role,
        'is_admin_role': is_admin_role,
        'operations': operations,
        'matrix': matrix,
    })

@login_required
@permission_required('users.add')
def add_role(request):
    """إضافة دور جديد"""
    
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.is_system_role = False
            role.save()
            messages.success(request, f'تم إنشاء الدور "{role.name}" بنجاح')
            return redirect('web:list_roles')
        for err in form.errors.values():
            messages.error(request, err[0])
    
    return render(request, 'pages/roles/form.html')


@login_required
@permission_required('users.delete')
def delete_role(request, role_id):
    """حذف دور (غير سيستمي وبدون مستخدمين)"""
    role = get_object_or_404(Role, id=role_id)

    if role.is_system_role:
        messages.error(request, 'لا يمكن حذف دور نظامي')
        return redirect('web:list_roles')

    users_count = role.users.count()
    if users_count > 0:
        messages.error(request, f'لا يمكن حذف الدور "{role.name}" لأنه مرتبط بـ {users_count} مستخدم')
        return redirect('web:list_roles')

    if request.method == 'POST':
        name = role.name
        role.delete()
        messages.success(request, f'تم حذف الدور "{name}" بنجاح')
        return redirect('web:list_roles')

    return redirect('web:list_roles')


# =============================================================================
# Role Permissions Management
# =============================================================================
@login_required
@permission_required('users.edit')
def manage_role_permissions(request, role_id):
    """إدارة صلاحيات دور (جدول وحدات × عمليات)"""
    from apps.core.models import AppModule, Permission

    role = get_object_or_404(Role, id=role_id)
    is_admin_role = role.role_type == Role.RoleType.ADMIN

    if request.method == 'POST':
        if is_admin_role:
            messages.warning(request, 'دور الأدمن لديه جميع الصلاحيات تلقائياً ولا يمكن تعديلها')
            return redirect('web:manage_role_permissions', role_id=role.id)

        selected_ids = request.POST.getlist('permissions')
        try:
            selected_ids = [int(x) for x in selected_ids if str(x).isdigit()]
        except (TypeError, ValueError):
            selected_ids = []
        perms = Permission.objects.filter(id__in=selected_ids, is_active=True)
        role.permissions.set(perms)
        messages.success(request, f'تم حفظ صلاحيات الدور "{role.name}" ({perms.count()} صلاحية)')
        return redirect('web:manage_role_permissions', role_id=role.id)

    # بناء جدول وحدات × عمليات
    modules = AppModule.objects.filter(is_active=True).prefetch_related('permissions')
    operations = list(Permission.Operation.choices)  # [('view','عرض'),...]
    role_perm_ids = set(role.permissions.values_list('id', flat=True))

    matrix = []
    for m in modules:
        cells = []
        for op_code, op_label in operations:
            perm = next((p for p in m.permissions.all() if p.operation == op_code and p.is_active), None)
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'checked': bool(perm and (is_admin_role or perm.id in role_perm_ids)),
                'available': perm is not None,
            })
        matrix.append({'module': m, 'cells': cells})

    return render(request, 'pages/roles/permissions.html', {
        'role': role,
        'is_admin_role': is_admin_role,
        'operations': operations,
        'matrix': matrix,
    })


# =============================================================================
# Branches Management
# =============================================================================

