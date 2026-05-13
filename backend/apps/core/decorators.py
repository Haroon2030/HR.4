"""
نظام الصلاحيات — Decorators
============================
هذا الملف يحتوي على أدوات فحص الصلاحيات (Decorators) المُستخدمة لحماية الـ Views.

المكونات الرئيسية:
  1. get_user_permissions(user) — جلب كل صلاحيات المستخدم كـ set (مُخزّن مؤقتاً)
  2. has_permission(user, code) — فحص سريع O(1) لصلاحية واحدة
  3. @permission_required — يتطلب صلاحية واحدة محددة
  4. @any_permission_required — يتطلب أي صلاحية من قائمة
  5. @all_permissions_required — يتطلب كل الصلاحيات في القائمة

منطق الصلاحيات:
  - السوبر يوزر والأدمن → لهم كل الصلاحيات تلقائياً
  - المستخدمون الآخرون → (صلاحيات الدور ∪ الإضافية) − المحرومة
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from apps.core.permissions_registry import register_permission as _register_perm


# ══════════════════════════════════════════════════════════════════════════════
# دوال مساعدة — مشتركة بين كل الـ decorators لتجنب التكرار وتقليل الاستعلامات
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_profile_role(request, raise_exception):
    """
    يتأكد من وجود ملف المستخدم (UserProfile) ودور مُعيَّن (Role).
    
    المخرجات:
        - UserProfile إذا كل شيء موجود
        - HttpResponse (إعادة توجيه) إذا لا يوجد profile أو role
    """
    user = request.user

    # فحص: هل المستخدم لديه ملف (UserProfile)؟
    if not hasattr(user, 'profile') or not user.profile:
        messages.error(request, 'لا يوجد ملف مستخدم مرتبط بحسابك')
        if raise_exception:
            raise PermissionDenied('لا يوجد ملف مستخدم')
        return redirect('web:dashboard')

    profile = user.profile

    # فحص: هل الملف مرتبط بدور؟
    if not profile.role:
        messages.error(request, 'لم يتم تعيين دور لحسابك')
        if raise_exception:
            raise PermissionDenied('لم يتم تعيين دور')
        return redirect('web:dashboard')

    return profile


def _is_super_or_admin(user):
    """فحص سريع — هل المستخدم superuser أو له دور أدمن؟"""
    if user.is_superuser:
        return True
    if not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        return False
    from apps.core.models import Role
    return user.profile.role.role_type == Role.RoleType.ADMIN


def get_user_permissions(user):
    """
    جلب كل صلاحيات المستخدم كـ set من الأكواد.
    يُحسب مرة واحدة ويُخزَّن مؤقتاً على المستخدم نفسه (لكل request).

    القواعد:
        - superuser / admin → كل الصلاحيات النشطة في النظام
        - غيرهم → (صلاحيات الدور ∪ الإضافية) − المحرومة

    الاستخدام في الـ View:
        codes = get_user_permissions(request.user)
        if 'employees.edit' in codes: ...

    الاستخدام في الـ Template:
        {% if request.user|has_permission:'employees.edit' %}
    """
    # التخزين المؤقت — يُحسب مرة واحدة لكل request
    cached = getattr(user, '_perm_codes_cache', None)
    if cached is not None:
        return cached

    from apps.core.models import Permission, Role

    if user.is_superuser:
        # السوبر يوزر → كل الصلاحيات
        codes = set(Permission.objects.filter(is_active=True).values_list('code', flat=True))
    elif not hasattr(user, 'profile') or not user.profile or not user.profile.role:
        # بدون ملف أو دور → بدون صلاحيات
        codes = set()
    elif user.profile.role.role_type == Role.RoleType.ADMIN:
        # الأدمن → كل الصلاحيات (مثل السوبر يوزر)
        codes = set(Permission.objects.filter(is_active=True).values_list('code', flat=True))
    else:
        # المستخدم العادي → (دور + إضافية) − محرومة
        profile = user.profile
        # 3 استعلامات فقط — ثم لا استعلامات إضافية لبقية الـ request
        role_codes = set(profile.role.permissions.filter(is_active=True).values_list('code', flat=True))
        extra_codes = set(profile.extra_permissions.filter(is_active=True).values_list('code', flat=True))
        denied_codes = set(profile.denied_permissions.filter(is_active=True).values_list('code', flat=True))
        codes = (role_codes | extra_codes) - denied_codes

    # حفظ في الكاش
    user._perm_codes_cache = codes
    return codes


def has_permission(user, permission_code):
    """
    فحص سريع O(1) لصلاحية واحدة — يستخدم الكاش المُخزّن.

    الاستخدام في القوالب (كـ template filter):
        {% if request.user|has_permission:'employees.edit' %}

    الاستخدام في الكود:
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


# ══════════════════════════════════════════════════════════════════════════════
# الـ Decorators — تُوضع فوق الـ View لحمايته
# ══════════════════════════════════════════════════════════════════════════════

def permission_required(permission_code, raise_exception=False):
    """
    Decorator يتحقق من أن المستخدم لديه صلاحية معينة.

    الاستخدام:
        @login_required
        @permission_required('employees.edit')
        def edit_employee(request, employee_id): ...

    المعاملات:
        permission_code: كود الصلاحية (مثل 'employees.view')
        raise_exception: إذا True يرفع 403 بدلاً من إعادة التوجيه
    """
    # تسجيل الصلاحية تلقائياً في سجل النظام
    _register_perm(permission_code)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # السوبر يوزر يمر مباشرة
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # التأكد من وجود profile + role
            profile_or_resp = _ensure_profile_role(request, raise_exception)
            if not hasattr(profile_or_resp, 'role'):  # يعني أنه response
                return profile_or_resp

            # الأدمن يمر مباشرة
            if _is_super_or_admin(request.user):
                return view_func(request, *args, **kwargs)

            # فحص الصلاحية المطلوبة
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
    """
    Decorator يتحقق من أن المستخدم لديه أي صلاحية واحدة على الأقل من القائمة.

    الاستخدام:
        @any_permission_required('employees.view', 'employees.edit')
        def some_view(request): ...
    """
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
    """
    Decorator يتحقق من أن المستخدم لديه جميع الصلاحيات في القائمة.

    الاستخدام:
        @all_permissions_required('employees.edit', 'payroll.manage')
        def sensitive_view(request): ...
    """
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
