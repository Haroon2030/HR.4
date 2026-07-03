from django.conf import settings
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

_GENERIC_500_MESSAGE = 'حدث خطأ داخلي في الخادم. تم تسجيل الخطأ للمراجعة.'


def _message_for_status(status_code: int) -> str:
    if status_code == status.HTTP_403_FORBIDDEN:
        return 'غير مصرح لك بإجراء هذه العملية'
    if status_code == status.HTTP_404_NOT_FOUND:
        return 'العنصر المطلوب غير موجود'
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return 'يجب تسجيل الدخول أولاً'
    return 'حدث خطأ في المدخلات أو الصلاحيات'


def _sanitize_errors(response) -> dict | list | None:
    """في الإنتاج: أخطاء الحقول فقط — بدون تفاصيل داخلية لـ 403/404."""
    if response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY):
        return response.data
    return None


def custom_api_exception_handler(exc, context):
    """
    معالج الأخطاء المركزي الخاص بـ (Django Rest Framework).
    يوحد جميع أشكال وحالات الأخطاء الخارجة من النظام إلى شكل JSON قياسي
    ليسهل على مطور الواجهات (الفرونت إند) قراءتها برمجياً.
  """
    
    # استدعاء المعالج الافتراضي الخاص بـ DRF أولاً
    response = exception_handler(exc, context)

    # إذا كان الخطأ معروفاً للـ DRF (مثل Validation أو Authentication)
    if response is not None:
        errors = response.data if settings.DEBUG else _sanitize_errors(response)
        error_data = {
            "success": False,
            "status_code": response.status_code,
            "message": _message_for_status(response.status_code),
        }
        if errors is not None:
            error_data["errors"] = errors
        
        response.data = error_data
    else:
        # خطأ غير متوقع (500) — لا تُعرض تفاصيل تقنية للمستخدم في الإنتاج
        request = context.get('request')
        path = getattr(request, 'path', '?')
        logger.exception('خطأ داخلي (500) في %s', path, exc_info=exc)

        error_data = {
            "success": False,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": _GENERIC_500_MESSAGE,
        }
        if settings.DEBUG:
            error_data["errors"] = str(exc)

        response = Response(error_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response
