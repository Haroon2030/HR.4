"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.core.models import AppModule, Permission, Role
from apps.core.forms import RoleForm


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.decorators import permission_required


def _build_role_permissions_matrix(role):
    """جدول وحدات × عمليات لنموذج/صفحة صلاحيات الدور."""
    modules = AppModule.objects.filter(is_active=True).prefetch_related('permissions')
    operations = list(Permission.Operation.choices)
    is_admin_role = role.role_type == Role.RoleType.ADMIN
    role_perm_ids = set(role.permissions.values_list('id', flat=True))

    matrix = []
    for m in modules:
        cells = []
        for op_code, op_label in operations:
            perm = next(
                (p for p in m.permissions.all() if p.operation == op_code and p.is_active),
                None,
            )
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'checked': bool(perm and (is_admin_role or perm.id in role_perm_ids)),
                'available': perm is not None,
            })
        matrix.append({'module': m, 'cells': cells})

    return {
        'role': role,
        'is_admin_role': is_admin_role,
        'operations': operations,
        'matrix': matrix,
    }


def _role_form_context(role=None):
    if role:
        return _build_role_permissions_matrix(role)
    return {
        'role': None,
        'is_admin_role': False,
        'operations': list(Permission.Operation.choices),
        'matrix': [],
    }

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

    ctx = _build_role_permissions_matrix(role)
    ctx['is_admin_role'] = is_admin_role
    return render(request, 'pages/roles/form.html', ctx)

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
            messages.success(
                request,
                f'تم إنشاء الدور "{role.name}" — يمكنك الآن تحديد الصلاحيات',
            )
            return redirect('web:edit_role', role_id=role.id)
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/roles/form.html', _role_form_context())


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

    ctx = _build_role_permissions_matrix(role)
    ctx['is_admin_role'] = is_admin_role
    return render(request, 'pages/roles/permissions.html', ctx)


# =============================================================================
# Branches Management
# =============================================================================

