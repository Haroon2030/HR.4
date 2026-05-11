"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.core.models import Role, Branch, UserProfile
from apps.core.forms import UserCreateForm, UserEditForm
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
def list_users(request):
    """قائمة المستخدمين والأدوار"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.select_related('profile__role', 'profile__branch').all()
    roles = Role.objects.all().prefetch_related('users')
    return render(request, 'pages/users/list.html', {
        'users': users,
        'roles': roles
    })

@login_required
@permission_required('users.view')
def view_user(request, user_id):
    """عرض تفاصيل مستخدم معين"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User.objects.select_related('profile__role', 'profile__branch'), id=user_id)
    return render(request, 'pages/users/detail.html', {'user_obj': user})


@login_required
@permission_required('users.delete')
def delete_user(request, user_id):
    """حذف مستخدم (للأدمن فقط)"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User, id=user_id)

    # منع حذف الذات
    if user.id == request.user.id:
        messages.error(request, 'لا يمكنك حذف حسابك الخاص')
        return redirect('web:list_users')

    # منع حذف المستخدمين المحميين
    profile = getattr(user, 'profile', None)
    if profile and getattr(profile, 'is_protected', False):
        messages.error(request, f'لا يمكن حذف المستخدم المحمي "{user.username}"')
        return redirect('web:list_users')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'تم حذف المستخدم "{username}" بنجاح')
        return redirect('web:list_users')

    return redirect('web:list_users')

@login_required
@permission_required('users.edit')
def edit_user(request, user_id):
    """تعديل مستخدم"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    roles = Role.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'pages/users/form.html', {
                'user_obj': user, 'roles': roles, 'branches': branches
            })
        cd = form.cleaned_data

        # تحديث بيانات المستخدم الأساسية
        user.username = cd['username']
        user.first_name = cd.get('first_name', '') or user.first_name
        user.last_name = cd.get('last_name', '') or user.last_name
        user.email = cd.get('email', '') or user.email
        if cd.get('is_active') is not None:
            user.is_active = cd['is_active']
        
        # تحديث كلمة المرور إذا تم إدخالها
        password = cd.get('password')
        if password:
            user.set_password(password)
        
        user.save()
        
        # تحديث البروفايل
        profile.role = cd.get('role')
        profile.branch = cd.get('branch')
        profile.user_number = cd.get('user_number')
        profile.phone = cd.get('phone', '')
        profile.position = cd.get('position', '')
        profile.save()
        
        # تحديث الفروع المكلف بها (للأخصائيين)
        assigned_branches = cd.get('assigned_branches')
        if profile.role and profile.role.role_type == 'specialist':
            profile.assigned_branches.set(assigned_branches or [])
        else:
            profile.assigned_branches.clear()
        
        messages.success(request, f'تم تحديث المستخدم "{user.username}" بنجاح')
        return redirect('web:list_users')
    
    return render(request, 'pages/users/form.html', {
        'user_obj': user,
        'roles': roles,
        'branches': branches
    })

@login_required
@permission_required('users.add')
def add_user(request):
    """إضافة مستخدم جديد"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    roles = Role.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)
    
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if not form.is_valid():
            for err in form.errors.values():
                messages.error(request, err[0])
            return render(request, 'pages/users/form.html', {
                'roles': roles, 'branches': branches
            })
        cd = form.cleaned_data
        is_active = cd.get('is_active')
        if is_active is None:
            is_active = True
        
        user = User.objects.create_user(
            username=cd['username'],
            email=cd.get('email', '') or '',
            password=cd['password'],
            first_name=cd.get('first_name', '') or '',
            last_name=cd.get('last_name', '') or '',
            is_active=is_active,
        )
        
        # إنشاء البروفايل
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = cd.get('role')
        profile.branch = cd.get('branch')
        profile.user_number = cd.get('user_number')
        profile.phone = cd.get('phone', '')
        profile.position = cd.get('position', '')
        profile.save()
        
        # تحديث الفروع المكلف بها (للأخصائيين)
        assigned_branches = cd.get('assigned_branches')
        if profile.role and profile.role.role_type == 'specialist' and assigned_branches:
            profile.assigned_branches.set(assigned_branches)
        
        messages.success(request, f'تم إنشاء المستخدم "{user.username}" بنجاح')
        return redirect('web:list_users')
    
    return render(request, 'pages/users/form.html', {
        'roles': roles,
        'branches': branches
    })


# =============================================================================
# User Permissions Override
# =============================================================================
@login_required
@permission_required('users.edit')
def manage_user_permissions(request, user_id):
    """إدارة الصلاحيات على مستوى المستخدم (تعديل فوق صلاحيات الدور).

    لكل خانة (وحدة×عملية) ثلاث حالات:
      - inherit  : اتبع صلاحيات الدور (افتراضي)
      - grant    : امنح صراحةً (ستظهر في extra_permissions)
      - deny     : امنع صراحةً (ستظهر في denied_permissions)
    """
    from django.contrib.auth import get_user_model
    from apps.core.models import AppModule, Permission

    User = get_user_model()
    user_obj = get_object_or_404(User.objects.select_related('profile__role'), id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user_obj)
    role = profile.role
    is_admin_user = bool(user_obj.is_superuser or (role and role.role_type == Role.RoleType.ADMIN))

    if request.method == 'POST':
        if is_admin_user:
            messages.warning(request, 'الأدمن/السوبر يوزر يملك جميع الصلاحيات تلقائياً')
            return redirect('web:manage_user_permissions', user_id=user_obj.id)

        extra_ids, denied_ids = [], []
        for key, val in request.POST.items():
            if not key.startswith('perm_'):
                continue
            try:
                pid = int(key[5:])
            except ValueError:
                continue
            if val == 'grant':
                extra_ids.append(pid)
            elif val == 'deny':
                denied_ids.append(pid)
            # 'inherit' => لا شيء

        extra_qs = Permission.objects.filter(id__in=extra_ids, is_active=True)
        denied_qs = Permission.objects.filter(id__in=denied_ids, is_active=True)
        profile.extra_permissions.set(extra_qs)
        profile.denied_permissions.set(denied_qs)
        messages.success(
            request,
            f'تم حفظ صلاحيات المستخدم "{user_obj.username}" '
            f'(+{extra_qs.count()} ممنوحة، -{denied_qs.count()} مرفوضة)'
        )
        return redirect('web:manage_user_permissions', user_id=user_obj.id)

    # بناء الجدول
    modules = AppModule.objects.filter(is_active=True).prefetch_related('permissions')
    operations = list(Permission.Operation.choices)
    role_perm_ids = set(role.permissions.values_list('id', flat=True)) if role else set()
    extra_ids = set(profile.extra_permissions.values_list('id', flat=True))
    denied_ids = set(profile.denied_permissions.values_list('id', flat=True))

    matrix = []
    for m in modules:
        cells = []
        for op_code, op_label in operations:
            perm = next((p for p in m.permissions.all() if p.operation == op_code and p.is_active), None)
            if not perm:
                cells.append({'op_code': op_code, 'op_label': op_label, 'available': False})
                continue
            in_role = perm.id in role_perm_ids
            if perm.id in denied_ids:
                state = 'deny'
            elif perm.id in extra_ids:
                state = 'grant'
            else:
                state = 'inherit'
            effective = is_admin_user or (state == 'grant') or (state == 'inherit' and in_role)
            cells.append({
                'op_code': op_code,
                'op_label': op_label,
                'perm': perm,
                'available': True,
                'in_role': in_role,
                'state': state,
                'effective': effective,
            })
        matrix.append({'module': m, 'cells': cells})

    return render(request, 'pages/users/permissions.html', {
        'user_obj': user_obj,
        'profile': profile,
        'role': role,
        'is_admin_user': is_admin_user,
        'operations': operations,
        'matrix': matrix,
    })

