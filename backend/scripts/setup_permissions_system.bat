@echo off
REM =============================================================================
REM سكريپت الإعداد الكامل لنظام الصلاحيات الديناميكي - Windows
REM =============================================================================

echo 🚀 بدء إعداد نظام الصلاحيات الديناميكي...
echo.

REM 1. تطبيق Migrations
echo 📦 1/4 - تطبيق Migrations...
python manage.py migrate
if errorlevel 1 (
    echo ❌ فشل تطبيق Migrations
    exit /b 1
)
echo ✅ تم تطبيق Migrations بنجاح
echo.

REM 2. مزامنة الوحدات والصلاحيات
echo 🔄 2/4 - مزامنة الوحدات والصلاحيات...
python manage.py sync_permissions --create-basic
if errorlevel 1 (
    echo ❌ فشلت المزامنة
    exit /b 1
)
echo ✅ تمت المزامنة بنجاح
echo.

REM 3. إنشاء الأدوار
echo 👥 3/4 - إنشاء الأدوار الأربعة...
python manage.py setup_roles
if errorlevel 1 (
    echo ❌ فشل إنشاء الأدوار
    exit /b 1
)
echo ✅ تم إنشاء الأدوار بنجاح
echo.

REM 4. ربط المستخدمين
echo 🔗 4/4 - ربط المستخدمين بالأدوار...
python manage.py setup_user_profiles
if errorlevel 1 (
    echo ❌ فشل ربط المستخدمين
    exit /b 1
)
echo ✅ تم ربط المستخدمين بنجاح
echo.

REM عرض النتيجة
echo ═══════════════════════════════════════════════════════════
echo 🎉 تم إعداد نظام الصلاحيات الديناميكي بنجاح!
echo ═══════════════════════════════════════════════════════════
echo.

REM عرض الإحصائيات
echo 📊 الإحصائيات:
python manage.py shell -c "from apps.core.models import AppModule, Permission, Role; print(f'  📦 الوحدات: {AppModule.objects.count()}'); print(f'  🔐 الصلاحيات: {Permission.objects.count()}'); print(f'  👥 الأدوار: {Role.objects.count()}'); print(''); print('الأدوار:'); [print(f'  • {role.name}: {role.permissions.count()} صلاحية') for role in Role.objects.all()]"

echo.
echo ═══════════════════════════════════════════════════════════
echo 🌐 الآن يمكنك الوصول إلى:
echo    http://127.0.0.1:8000/roles/     - إدارة الأدوار
echo    http://127.0.0.1:8000/roles/add/ - إضافة دور جديد
echo ═══════════════════════════════════════════════════════════
echo.
echo 📖 للمزيد من المعلومات:
echo    - PERMISSIONS_SYSTEM.md
echo    - docs/USAGE_GUIDE.md
echo    - docs/example_add_module.py
echo ═══════════════════════════════════════════════════════════

pause
