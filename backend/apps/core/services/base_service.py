import logging
from django.db import transaction
from django.core.exceptions import ValidationError

# إعداد مسجل الأخطاء المركزي (Logger)
logger = logging.getLogger(__name__)

class BaseService:
    """
    الفئة الأساسية لطبقة الخدمات (Service Layer).
    الهدف من هذه الطبقة هو عزل منطق الأعمال (Business Logic) عن الـ Views،
    مما يجعل الـ Controllers نظيفة وسهلة القراءة وموجهة للـ Routing فقط.
    """
    
    @classmethod
    def execute_in_transaction(cls, func, *args, **kwargs):
        """
        دالة مساعدة لتغليف أي عملية معقدة داخل Transaction حقيقي،
        بحيث لو حدث خطأ في نصف العملية يتم التراجع عن جميع التغييرات (Rollback)
        حفاظاً على سلامة البيانات.
        """
        try:
            with transaction.atomic():
                return func(*args, **kwargs)
        except ValidationError as e:
            # نسجل محاولة غير ناجحة بسبب بيانات خاطئة
            logger.warning(f"تم إيقاف عملية في {cls.__name__} بسبب التحقق: {str(e)}")
            raise e
        except Exception as e:
            # نسجل الأخطاء الفادحة غير المتوقعة (Bugs)
            logger.error(f"خطأ حرج حدث في {cls.__name__} أثناء التنفيذ: {str(e)}")
            raise e
