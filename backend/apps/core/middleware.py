import logging
from django.http import JsonResponse
from rest_framework import status

# إعداد الـ Logger المركزي لتسجيل محاولات الوصول المرفوضة
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
        # هذا الكود ينفذ قبل الوصول إلى الروابط (Views)
        response = self.get_response(request)
        # هذا الكود ينفذ بعد الرد (Response)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        يتم تنفيذ هذه الدالة قبل أن يقرر النظام أي View سيتم تشغيله مباشرة.
        وهنا نقوم بفحص الصلاحيات بذكاء.
        """
        
        # 1. تخطي الفحص إذا لم يكن الطلب ضمن مسارات الـ API
        # (حتى لا نؤثر على لوحة تحكم الإدمن الافتراضية أو الشاشات العادية)
        if not request.path.startswith('/api/'):
            return None

        # 2. تخطي مسارات التوثيق وتسجيل الدخول
        if request.path.startswith('/api/auth/') or request.path.startswith('/api/token/'):
            return None

        # 2b. وكيل البصمة المحلي — مصادقة بمفتاح API داخل DRF (ليس JWT)
        if request.path.startswith('/api/v1/attendance/agent/'):
            return None

        # 3. التأكد من أن المستخدم مسجل الدخول أساساً (Authentication)
        if not request.user.is_authenticated:
            return JsonResponse(
                {'detail': 'غير مصرح بالدخول. يرجى إرسال التوكن (Token) أو تسجيل الدخول.'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 4. محاولة قراءة 'الصلاحية المطلوبة' المربوطة بالـ View
        # مستقبلاً، في أي View نقوم بإنشائه سنكتب داخله: required_permission = 'view_employees'
        required_permission = None
        if hasattr(view_func, 'view_class'):
            required_permission = getattr(view_func.view_class, 'required_permission', None)
        else:
            required_permission = getattr(view_func, 'required_permission', None)

        if required_permission:
            try:
                # محاولة جلب ملف المستخدم (Profile) الذي يحتوي على الأدوار
                profile = getattr(request.user, 'profile', None)
                if not profile:
                    return JsonResponse(
                        {'detail': 'ملف المستخدم غير مكتمل في النظام.'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )

                # 5. القاعدة الذهبية: مدير النظام (Admin) لديه وصول كامل دائماً
                if profile.is_admin:
                    return None

                # 6. التحقق من وجود الصلاحية المطلوبة لدى المستخدم
                user_permissions = profile.get_permissions()
                if required_permission not in user_permissions:
                    # تسجيل الحادثة للأمان (Audit/Log)
                    logger.warning(
                        f"محاولة وصول مرفوضة: المستخدم {request.user.username} "
                        f"حاول فتح {request.path} وكان يفتقد لصلاحية '{required_permission}'."
                    )
                    return JsonResponse(
                        {'detail': f"عذراً، ليس لديك الصلاحية الكافية للقيام بهذا الإجراء. مطلوب صلاحية: {required_permission}"}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            except Exception as e:
                logger.error(f"خطأ غير متوقع أثناء التحقق من الصلاحيات: {str(e)}")
                return JsonResponse(
                    {'detail': 'حدث خطأ داخلي أثناء التحقق من صلاحياتك.'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # إذا لم يمر الطلب بأي حالة رفض، اتركه يمر بسلام
        return None
