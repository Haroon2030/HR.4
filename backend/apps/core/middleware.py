import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import status

logger = logging.getLogger(__name__)


class AccessControlMiddleware:
    """
    طبقة وسيطة (Middleware) مركزية للتحكم في الوصول.
    تعمل هذه الطبقة كحارس بوابة (Security Guard) يعترض كل الطلبات.
    المميزات:
    1. تخطي مسارات تسجيل الدخول والملفات الثابتة.
    2. التحقق التلقائي من تسجيل الدخول لمسارات الـ API.
    3. قراءة الصلاحية المطلوبة (required_permission) من الـ View والتحقق منها.
    4. إعطاء تصريح عبور تلقائي لمدير النظام الشامل (Admin).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.startswith('/api/'):
            return None

        if request.path.startswith('/api/auth/') or request.path.startswith('/api/token/'):
            return None

        if request.path.startswith('/api/v1/attendance/agent/'):
            return None

        if not request.user.is_authenticated:
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication

                auth_result = JWTAuthentication().authenticate(request)
                if auth_result is not None:
                    request.user, _ = auth_result
            except Exception:
                pass

        if not request.user.is_authenticated:
            return JsonResponse(
                {'detail': 'غير مصرح بالدخول. يرجى إرسال التوكن (Token) أو تسجيل الدخول.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        required_permission = None
        if hasattr(view_func, 'view_class'):
            required_permission = getattr(view_func.view_class, 'required_permission', None)
        else:
            required_permission = getattr(view_func, 'required_permission', None)

        if required_permission:
            try:
                profile = getattr(request.user, 'profile', None)
                if not profile:
                    return JsonResponse(
                        {'detail': 'ملف المستخدم غير مكتمل في النظام.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if profile.is_admin:
                    return None

                user_permissions = profile.get_permissions()
                if required_permission not in user_permissions:
                    logger.warning(
                        f"محاولة وصول مرفوضة: المستخدم {request.user.username} "
                        f"حاول فتح {request.path} وكان يفتقد لصلاحية '{required_permission}'."
                    )
                    return JsonResponse(
                        {
                            'detail': (
                                f"عذراً، ليس لديك الصلاحية الكافية للقيام بهذا الإجراء. "
                                f"مطلوب صلاحية: {required_permission}"
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            except Exception as e:
                logger.error(f"خطأ غير متوقع أثناء التحقق من الصلاحيات: {str(e)}")
                return JsonResponse(
                    {'detail': 'حدث خطأ داخلي أثناء التحقق من صلاحياتك.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return None


_SKIP_SESSION_ACTIVITY_PREFIXES = (
    '/static/',
    '/health/',
    '/media/',
    '/auth/login',
    '/auth/logout',
    '/auth/idle-logout',
)


def _is_api_request(request) -> bool:
    path = request.path or ''
    if path.startswith('/api/'):
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def _is_background_session_poll(request) -> bool:
    """طلبات تحديث جدول الجلسات — لا تُمدّد مهلة الخمول."""
    return request.headers.get('X-Sessions-Poll') == '1'


class UserSessionActivityMiddleware:
    """مهلة خمول الجلسة + تحديث last_seen_at."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        skip = any(path.startswith(prefix) for prefix in _SKIP_SESSION_ACTIVITY_PREFIXES)

        if not skip and getattr(request, 'user', None) and request.user.is_authenticated:
            try:
                from apps.core.services.user_sessions import (
                    enforce_idle_timeout,
                    idle_timeout_message,
                )

                if enforce_idle_timeout(request):
                    if _is_api_request(request):
                        return JsonResponse(
                            {'detail': idle_timeout_message()},
                            status=401,
                        )
                    messages.warning(request, idle_timeout_message())
                    return redirect(f"{reverse('web:auth:login')}?idle=1")
            except Exception:
                logger.exception('UserSessionActivityMiddleware idle check failed')

        response = self.get_response(request)

        if skip:
            return response

        if getattr(request, 'user', None) and request.user.is_authenticated:
            try:
                from apps.core.services.user_sessions import touch_session

                if not _is_background_session_poll(request):
                    touch_session(request)
            except Exception:
                logger.exception('UserSessionActivityMiddleware touch failed')
        return response
