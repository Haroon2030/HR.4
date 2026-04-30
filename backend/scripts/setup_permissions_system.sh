#!/bin/bash

# =============================================================================
# سكريبت الإعداد الكامل لنظام الصلاحيات الديناميكي
# =============================================================================

echo "🚀 بدء إعداد نظام الصلاحيات الديناميكي..."
echo ""

# 1. تطبيق Migrations
echo "📦 1/4 - تطبيق Migrations..."
python manage.py migrate
if [ $? -ne 0 ]; then
    echo "❌ فشل تطبيق Migrations"
    exit 1
fi
echo "✅ تم تطبيق Migrations بنجاح"
echo ""

# 2. مزامنة الوحدات والصلاحيات
echo "🔄 2/4 - مزامنة الوحدات والصلاحيات..."
python manage.py sync_permissions --create-basic
if [ $? -ne 0 ]; then
    echo "❌ فشلت المزامنة"
    exit 1
fi
echo "✅ تمت المزامنة بنجاح"
echo ""

# 3. إنشاء الأدوار
echo "👥 3/4 - إنشاء الأدوار الأربعة..."
python manage.py setup_roles
if [ $? -ne 0 ]; then
    echo "❌ فشل إنشاء الأدوار"
    exit 1
fi
echo "✅ تم إنشاء الأدوار بنجاح"
echo ""

# 4. ربط المستخدمين
echo "🔗 4/4 - ربط المستخدمين بالأدوار..."
python manage.py setup_user_profiles
if [ $? -ne 0 ]; then
    echo "❌ فشل ربط المستخدمين"
    exit 1
fi
echo "✅ تم ربط المستخدمين بنجاح"
echo ""

# عرض النتيجة
echo "═══════════════════════════════════════════════════════════"
echo "🎉 تم إعداد نظام الصلاحيات الديناميكي بنجاح!"
echo "═══════════════════════════════════════════════════════════"
echo ""

# عرض الإحصائيات
echo "📊 الإحصائيات:"
python manage.py shell -c "
from apps.core.models import AppModule, Permission, Role
print(f'  📦 الوحدات: {AppModule.objects.count()}')
print(f'  🔐 الصلاحيات: {Permission.objects.count()}')
print(f'  👥 الأدوار: {Role.objects.count()}')
print('')
print('الأدوار:')
for role in Role.objects.all():
    print(f'  • {role.name}: {role.permissions.count()} صلاحية')
"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🌐 الآن يمكنك الوصول إلى:"
echo "   http://127.0.0.1:8000/roles/     - إدارة الأدوار"
echo "   http://127.0.0.1:8000/roles/add/ - إضافة دور جديد"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📖 للمزيد من المعلومات:"
echo "   - PERMISSIONS_SYSTEM.md"
echo "   - docs/USAGE_GUIDE.md"
echo "   - docs/example_add_module.py"
echo "═══════════════════════════════════════════════════════════"
