# 📚 مجلد الوثائق - Documentation

هذا المجلد يحتوي على جميع الوثائق التفصيلية للمشروع.

## 📑 محتويات المجلد

### وثائق النظام الأساسية:
- **[PERMISSIONS_SYSTEM.md](PERMISSIONS_SYSTEM.md)** - دليل شامل لنظام الصلاحيات الديناميكي
- **[DYNAMIC_PERMISSIONS_COMPLETED.md](DYNAMIC_PERMISSIONS_COMPLETED.md)** - تفاصيل إنجاز نظام الصلاحيات
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - هيكل المشروع المفصل
- **[CHANGELOG.md](CHANGELOG.md)** - سجل التغييرات والتحديثات

### أدلة الاستخدام:
- **[USAGE_GUIDE.md](USAGE_GUIDE.md)** - دليل الاستخدام اليومي
- **[example_add_module.py](example_add_module.py)** - مثال عملي لإضافة وحدة جديدة

## 🚀 البدء السريع

### إعداد نظام الصلاحيات:

**Windows:**
```cmd
cd backend\scripts
setup_permissions_system.bat
```

**Linux/Mac:**
```bash
cd backend/scripts
chmod +x setup_permissions_system.sh
./setup_permissions_system.sh
```

**يدوياً:**
```bash
cd backend
python manage.py migrate
python manage.py sync_permissions --create-basic
python manage.py setup_roles
python manage.py setup_user_profiles
```

## 📖 المزيد من المعلومات

للحصول على نظرة عامة على المشروع، راجع [README.md](../README.md) في الجذر الرئيسي.

**النتيجة:** تُضاف الوحدة تلقائياً مع 5 صلاحيات أساسية! ✨

## حماية View 🔒

```python
from apps.core.decorators import permission_required

@login_required
@permission_required('employees.edit')
def edit_employee(request, pk):
    # فقط من لديه الصلاحية يمكنه الوصول
    ...
```

## إخفاء محتوى في Template 👁️

```django
{% load custom_tags %}

{% if request.user|has_permission:'employees.delete' %}
    <button>حذف</button>
{% endif %}
```

## الأدوار الأساسية 👥

| الدور | الصلاحيات | الاستخدام |
|------|-----------|----------|
| **الأدمن** | 57 (كل شيء) | مدير النظام الكامل |
| **الموارد البشرية** | 31 | إدارة الموظفين والرواتب |
| **مدير فرع/قسم** | 11 | إدارة الفرع/القسم |
| **موظف** | 4 | عرض البيانات الشخصية |

## الأوامر المتاحة 🔧

```bash
# مزامنة الوحدات
python manage.py sync_permissions

# مزامنة + إنشاء صلاحيات
python manage.py sync_permissions --create-basic

# إنشاء الأدوار
python manage.py setup_roles

# إعادة إنشاء الأدوار
python manage.py setup_roles --reset

# ربط المستخدمين
python manage.py setup_user_profiles
```

## روابط مهمة 🔗

- **إدارة الأدوار:** http://127.0.0.1:8000/roles/
- **إضافة دور:** http://127.0.0.1:8000/roles/add/

## المكونات الرئيسية 🧩

### Models
- `AppModule` - الوحدات
- `Permission` - الصلاحيات
- `Role` - الأدوار
- `UserProfile` - ملف المستخدم

### Decorators
- `@permission_required('code')` - صلاحية واحدة
- `@any_permission_required('c1', 'c2')` - أي صلاحية
- `@all_permissions_required('c1', 'c2')` - كل الصلاحيات

### Template Tags
- `{% if user|has_permission:'code' %}` - فلتر
- `{% user_has_permission 'code' as var %}` - تاغ
- `{% user_permissions as perms %}` - كل الصلاحيات

### Helpers
- `has_permission(user, code)` - تحقق يدوي
- `get_user_permissions(user)` - قائمة الصلاحيات

## الهيكل 🏗️

```
AppModule (الوحدات)
    ↓
Permission (الصلاحيات)
    ↓
Role (الأدوار)
    ↓
UserProfile → User
```

## مثال كامل 📝

### 1. إنشاء وحدة "المشتريات"

```bash
python manage.py startapp purchases
# أضف 'apps.purchases' إلى INSTALLED_APPS
python manage.py sync_permissions --create-basic
```

### 2. إضافة View محمية

```python
# في apps/purchases/views.py
from apps.core.decorators import permission_required

@login_required
@permission_required('purchases.view')
def list_purchases(request):
    return render(request, 'purchases/list.html')
```

### 3. إضافة صلاحية مخصصة

```python
from apps.core.models import AppModule, Permission

module = AppModule.objects.get(code='purchases')
Permission.objects.create(
    code='purchases.approve',
    name='الموافقة على المشتريات',
    module=module,
    is_active=True
)
```

### 4. تحديث الأدوار

```bash
# عدّل apps/core/management/commands/setup_roles.py
# أضف 'purchases.approve' لدور HR
python manage.py setup_roles
```

## الدعم والمساعدة 🤝

للأسئلة والمشاكل:
1. راجع [USAGE_GUIDE.md](USAGE_GUIDE.md) للأمثلة
2. راجع [PERMISSIONS_SYSTEM.md](../PERMISSIONS_SYSTEM.md) للتفاصيل
3. راجع [example_add_module.py](example_add_module.py) للأمثلة الكاملة

---

**✨ نظام صلاحيات احترافي جاهز للإنتاج!**
