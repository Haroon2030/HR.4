"""
Decorators لفحص الصلاحيات في Views
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied


def permission_required(permission_code, raise_exception=False):
    """
    Decorator للتحقق من أن المستخدم لديه صلاحية معينة
    
    الاستخدام:
        @login_required
        @permission_required('employees.view')
        def list_employees(request):
            ...
    
    Args:
        permission_code (str): كود الصلاحية مثل 'employees.view'
        raise_exception (bool): رفع استثناء 403 بدلاً من redirect
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # السوبر يوزر لديه كل الصلاحيات
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # التحقق من وجود profile
            if not hasattr(request.user, 'profile') or not request.user.profile:
                messages.error(request, 'لا يوجد ملف مستخدم مرتبط بحسابك')
                if raise_exception:
                    raise PermissionDenied('لا يوجد ملف مستخدم')
                return redirect('web:dashboard')
            
            # التحقق من وجود دور
            profile = request.user.profile
            if not profile.role:
                messages.error(request, 'لم يتم تعيين دور لحسابك')
                if raise_exception:
                    raise PermissionDenied('لم يتم تعيين دور')
                return redirect('web:dashboard')
            
            # الأدمن (RoleType.ADMIN) يمرّ تلقائياً
            from apps.core.models import Role
            if profile.role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
            
            # التحقق من الصلاحية
            user_permissions = profile.role.permissions.filter(
                code=permission_code,
                is_active=True
            ).exists()
            
            if not user_permissions:
                messages.error(request, f'ليس لديك صلاحية للوصول إلى هذه الصفحة')
                if raise_exception:
                    raise PermissionDenied(f'الصلاحية {permission_code} مطلوبة')
                return redirect('web:dashboard')
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def any_permission_required(*permission_codes, raise_exception=False):
    """
    Decorator للتحقق من أن المستخدم لديه أي صلاحية من القائمة
    
    الاستخدام:
        @login_required
        @any_permission_required('employees.view', 'employees.manage')
        def list_employees(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # السوبر يوزر لديه كل الصلاحيات
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # التحقق من وجود profile وdور
            if not hasattr(request.user, 'profile') or not request.user.profile:
                messages.error(request, 'لا يوجد ملف مستخدم مرتبط بحسابك')
                if raise_exception:
                    raise PermissionDenied('لا يوجد ملف مستخدم')
                return redirect('web:dashboard')
            
            profile = request.user.profile
            if not profile.role:
                messages.error(request, 'لم يتم تعيين دور لحسابك')
                if raise_exception:
                    raise PermissionDenied('لم يتم تعيين دور')
                return redirect('web:dashboard')
            
            # الأدمن (RoleType.ADMIN) يمرّ تلقائياً
            from apps.core.models import Role
            if profile.role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
            
            # التحقق من وجود أي صلاحية من القائمة
            has_permission = profile.role.permissions.filter(
                code__in=permission_codes,
                is_active=True
            ).exists()
            
            if not has_permission:
                messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
                if raise_exception:
                    raise PermissionDenied(f'أحد الصلاحيات {permission_codes} مطلوبة')
                return redirect('web:dashboard')
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def all_permissions_required(*permission_codes, raise_exception=False):
    """
    Decorator للتحقق من أن المستخدم لديه جميع الصلاحيات في القائمة
    
    الاستخدام:
        @login_required
        @all_permissions_required('employees.view', 'employees.edit')
        def edit_employee(request, employee_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # السوبر يوزر لديه كل الصلاحيات
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # التحقق من وجود profile ودور
            if not hasattr(request.user, 'profile') or not request.user.profile:
                messages.error(request, 'لا يوجد ملف مستخدم مرتبط بحسابك')
                if raise_exception:
                    raise PermissionDenied('لا يوجد ملف مستخدم')
                return redirect('web:dashboard')
            
            profile = request.user.profile
            if not profile.role:
                messages.error(request, 'لم يتم تعيين دور لحسابك')
                if raise_exception:
                    raise PermissionDenied('لم يتم تعيين دور')
                return redirect('web:dashboard')
            
            # الأدمن (RoleType.ADMIN) يمرّ تلقائياً
            from apps.core.models import Role
            if profile.role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
            
            # التحقق من وجود كل الصلاحيات
            user_permission_codes = set(
                profile.role.permissions.filter(is_active=True).values_list('code', flat=True)
            )
            required_permissions = set(permission_codes)
            
            if not required_permissions.issubset(user_permission_codes):
                missing = required_permissions - user_permission_codes
                messages.error(request, f'تحتاج إلى صلاحيات إضافية للوصول')
                if raise_exception:
                    raise PermissionDenied(f'الصلاحيات {missing} مطلوبة')
                return redirect('web:dashboard')
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def has_permission(user, permission_code):
    """
    Helper function للتحقق من صلاحية في Template أو View
    
    الاستخدام في View:
        if has_permission(request.user, 'employees.edit'):
            # السماح بالتعديل
    
    الاستخدام في Template:
        {% if request.user|has_permission:'employees.edit' %}
            <button>تعديل</button>
        {% endif %}
    """
    # السوبر يوزر لديه كل الصلاحيات
    if user.is_superuser:
        return True
    
    # التحقق من وجود profile ودور
    if not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        return False

    # الأدمن (RoleType.ADMIN) يحصل تلقائياً على كل الصلاحيات
    from apps.core.models import Role
    if user.profile.role.role_type == Role.RoleType.ADMIN:
        return True

    # التحقق من الصلاحية
    return user.profile.role.permissions.filter(
        code=permission_code,
        is_active=True
    ).exists()


def get_user_permissions(user):
    """
    الحصول على قائمة كل صلاحيات المستخدم
    
    الاستخدام:
        permissions = get_user_permissions(request.user)
        if 'employees.edit' in permissions:
            # السماح بالتعديل
    """
    # السوبر يوزر لديه كل الصلاحيات
    if user.is_superuser:
        from apps.core.models import Permission
        return list(Permission.objects.filter(is_active=True).values_list('code', flat=True))
    
    # التحقق من وجود profile ودور
    if not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        return []

    # الأدمن (RoleType.ADMIN) يحصل تلقائياً على كل الصلاحيات
    from apps.core.models import Permission, Role
    if user.profile.role.role_type == Role.RoleType.ADMIN:
        return list(Permission.objects.filter(is_active=True).values_list('code', flat=True))

    # إرجاع قائمة الصلاحيات
    return list(
        user.profile.role.permissions.filter(is_active=True).values_list('code', flat=True)
    )
