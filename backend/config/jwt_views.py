"""JWT endpoints with rate limiting."""
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


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]


class ThrottledTokenVerifyView(TokenVerifyView):
    throttle_classes = [_LoginAnonThrottle, _LoginUserThrottle]
