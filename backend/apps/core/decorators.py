"""
Decorators لفحص الصلاحيات في Views
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from apps.core.permissions_registry import register_permission as _register_perm


# ============================================================================
# Helpers — مشتركة بين كل decorators لتجنب التكرار وتقليل الـ queries
# ============================================================================

def _ensure_profile_role(request, raise_exception):
    """يتأكد من وجود profile + role. يُرجع profile أو response عند الفشل.

    Returns:
        UserProfile إذا الكل موجود، أو HttpResponse (redirect) إذا لا.
    """
    user = request.user
    if not hasattr(user, 'profile') or not user.profile:
        messages.error(request, 'لا يوجد ملف مستخدم مرتبط بحسابك')
        if raise_exception:
            raise PermissionDenied('لا يوجد ملف مستخدم')
        return redirect('web:dashboard')

    profile = user.profile
    if not profile.role:
        messages.error(request, 'لم يتم تعيين دور لحسابك')
        if raise_exception:
            raise PermissionDenied('لم يتم تعيين دور')
        return redirect('web:dashboard')

    return profile


def _is_super_or_admin(user):
    """فحص سريع — superuser أو role.role_type == ADMIN."""
    if user.is_superuser:
        return True
    if not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        return False
    from apps.core.models import Role
    return user.profile.role.role_type == Role.RoleType.ADMIN


def get_user_permissions(user):
    """
    صلاحيات المستخدم كـ set من الأكواد. يُحسب مرة واحدة لكل instance ويُخزَّن مؤقتاً.

    - superuser / admin → كل الصلاحيات النشطة
    - غيرهم → (صلاحيات الدور ∪ extra) − denied

    استخدام:
        codes = get_user_permissions(request.user)
        if 'employees.edit' in codes: ...
    """
    # Cache على المستخدم نفسه — يُحدَّد على instance واحد لكل request (django.contrib.auth)
    cached = getattr(user, '_perm_codes_cache', None)
    if cached is not None:
        return cached

    from apps.core.models import Permission, Role

    if user.is_superuser:
        codes = set(Permission.objects.filter(is_active=True).values_list('code', flat=True))
    elif not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        codes = set()
    elif user.profile.role.role_type == Role.RoleType.ADMIN:
        codes = set(Permission.objects.filter(is_active=True).values_list('code', flat=True))
    else:
        profile = user.profile
        # 3 queries فقط — ثم لا queries إضافية لبقية الـ request
        role_codes = set(profile.role.permissions.filter(is_active=True).values_list('code', flat=True))
        extra_codes = set(profile.extra_permissions.filter(is_active=True).values_list('code', flat=True))
        denied_codes = set(profile.denied_permissions.filter(is_active=True).values_list('code', flat=True))
        codes = (role_codes | extra_codes) - denied_codes

    user._perm_codes_cache = codes
    return codes


def has_permission(user, permission_code):
    """
    فحص O(1) لصلاحية واحدة (يستخدم cache المستخدم).

    Template:
        {% if request.user|has_permission:'employees.edit' %}
    View:
        if has_permission(request.user, 'employees.edit'): ...
    """
    if not user or not user.is_authenticated:
        return False
    return permission_code in get_user_permissions(user)


def _check_or_redirect(request, has_perm, raise_exception, deny_msg, exc_msg):
    """مساعد مشترك: يُرجع None إذا الصلاحية موجودة، أو redirect/raise إذا لا."""
    if has_perm:
        return None
    messages.error(request, deny_msg)
    if raise_exception:
        raise PermissionDenied(exc_msg)
    return redirect('web:dashboard')


# ============================================================================
# Decorators
# ============================================================================

def permission_required(permission_code, raise_exception=False):
    """
    Decorator للتحقق من أن المستخدم لديه صلاحية معينة

    Args:
        permission_code (str): كود الصلاحية مثل 'employees.view'
        raise_exception (bool): رفع استثناء 403 بدلاً من redirect
    """
    _register_perm(permission_code)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            profile_or_resp = _ensure_profile_role(request, raise_exception)
            if not hasattr(profile_or_resp, 'role'):  # response
                return profile_or_resp

            if _is_super_or_admin(request.user):
                return view_func(request, *args, **kwargs)

            resp = _check_or_redirect(
                request,
                has_permission(request.user, permission_code),
                raise_exception,
                'ليس لديك صلاحية للوصول إلى هذه الصفحة',
                f'الصلاحية {permission_code} مطلوبة',
            )
            if resp is not None:
                return resp
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def any_permission_required(*permission_codes, raise_exception=False):
    """التحقق من أن المستخدم لديه أي صلاحية من القائمة."""
    for _c in permission_codes:
        _register_perm(_c)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            profile_or_resp = _ensure_profile_role(request, raise_exception)
            if not hasattr(profile_or_resp, 'role'):
                return profile_or_resp

            if _is_super_or_admin(request.user):
                return view_func(request, *args, **kwargs)

            user_perms = get_user_permissions(request.user)
            resp = _check_or_redirect(
                request,
                any(c in user_perms for c in permission_codes),
                raise_exception,
                'ليس لديك صلاحية للوصول إلى هذه الصفحة',
                f'أحد الصلاحيات {permission_codes} مطلوبة',
            )
            if resp is not None:
                return resp
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def all_permissions_required(*permission_codes, raise_exception=False):
    """التحقق من أن المستخدم لديه جميع الصلاحيات في القائمة."""
    for _c in permission_codes:
        _register_perm(_c)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            profile_or_resp = _ensure_profile_role(request, raise_exception)
            if not hasattr(profile_or_resp, 'role'):
                return profile_or_resp

            if _is_super_or_admin(request.user):
                return view_func(request, *args, **kwargs)

            user_perms = get_user_permissions(request.user)
            missing = [c for c in permission_codes if c not in user_perms]
            resp = _check_or_redirect(
                request,
                not missing,
                raise_exception,
                'تحتاج إلى صلاحيات إضافية للوصول',
                f'الصلاحيات {set(missing)} مطلوبة',
            )
            if resp is not None:
                return resp
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
