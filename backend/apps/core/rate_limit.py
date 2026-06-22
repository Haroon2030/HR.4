"""محدّدات الطلبات المشتركة — django-ratelimit."""
from django.conf import settings
from django_ratelimit.decorators import ratelimit


def _rate_from_setting(setting_name: str):
    def _rate(group, request):
        return getattr(settings, setting_name)

    return _rate


def limit_web_login(view_func):
    """حدّ مزدوج لتسجيل الدخول: عنوان IP + اسم المستخدم."""
    view_func = ratelimit(
        key='ip',
        rate=_rate_from_setting('RATELIMIT_LOGIN_IP'),
        method='POST',
        block=False,
        group='web_login_ip',
    )(view_func)
    return ratelimit(
        key='post:username',
        rate=_rate_from_setting('RATELIMIT_LOGIN_USER'),
        method='POST',
        block=False,
        group='web_login_user',
    )(view_func)


def limit_password_change(view_func):
    return ratelimit(
        key='user',
        rate=_rate_from_setting('RATELIMIT_PASSWORD_CHANGE'),
        method='POST',
        block=False,
        group='password_change',
    )(view_func)


def limit_health_check(view_func):
    return ratelimit(
        key='ip',
        rate=_rate_from_setting('RATELIMIT_HEALTH_IP'),
        method='GET',
        block=True,
        group='health_check',
    )(view_func)
