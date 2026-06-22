"""استجابة موحّدة عند تجاوز حد الطلبات (django-ratelimit)."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django_ratelimit.exceptions import Ratelimited


def ratelimited(request, exception=None):
    if exception is not None and not isinstance(exception, Ratelimited):
        from django.views.defaults import permission_denied

        return permission_denied(request, exception)

    message = 'تجاوزت عدد المحاولات المسموح. حاول مرة أخرى لاحقاً.'

    if request.path.startswith('/api/'):
        return JsonResponse(
            {
                'success': False,
                'status_code': 429,
                'message': message,
            },
            status=429,
        )

    messages.error(request, message)
    if '/login' in request.path:
        return render(request, 'auth/login.html')
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return redirect('web:dashboard')
    return redirect('web:auth:login')
