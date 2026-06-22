from django.conf import settings
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

_GENERIC_500_MESSAGE = 'حدث خطأ داخلي في الخادم. تم تسجيل الخطأ للمراجعة.'


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
        # توحيد هيكل الرد
        error_data = {
            "success": False,
            "status_code": response.status_code,
            "message": "حدث خطأ في المدخلات أو الصلاحيات",
            "errors": response.data # نترك التفاصيل هنا لكي يعرضها الفرونت إند في الحقول
        }
        
        # لو كان الخطأ هو رفض الوصول (403 Forbidden)
        if response.status_code == status.HTTP_403_FORBIDDEN:
            error_data["message"] = "غير مصرح لك بإجراء هذه العملية"
            
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
