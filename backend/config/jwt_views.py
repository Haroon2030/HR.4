"""JWT endpoints with rate limiting (DRF throttling + django-ratelimit)."""
from django.conf import settings
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)


class _LoginAnonThrottle(AnonRateThrottle):
    scope = 'login'


class _LoginUserThrottle(UserRateThrottle):
    scope = 'login_user'


def _api_token_ip_ratelimit(view_cls):
    def _rate(group, request):
        return settings.RATELIMIT_API_TOKEN_IP

    return method_decorator(
        ratelimit(
            key='ip',
            rate=_rate,
            method='POST',
            block=True,
            group='api_token_ip',
        ),
        name='dispatch',
    )(view_cls)


@_api_token_ip_ratelimit
class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]


@_api_token_ip_ratelimit
class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]


@_api_token_ip_ratelimit
class ThrottledTokenVerifyView(TokenVerifyView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]
