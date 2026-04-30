# دليل الاستخدام السريع - نظام الصلاحيات 🚀

## سيناريوهات الاستخدام اليومية

### 1️⃣ إضافة صفحة جديدة محمية بصلاحية

```python
# في apps/employees/views.py
from django.contrib.auth.decorators import login_required
from apps.core.decorators import permission_required

@login_required
@permission_required('employees.edit')
def edit_employee(request, employee_id):
    # يمكن الوصول فقط لمن لديهم صلاحية employees.edit
    employee = get_object_or_404(Employee, id=employee_id)
    # ... منطق التعديل
    return render(request, 'employees/edit.html', {'employee': employee})
```

### 2️⃣ إخفاء أزرار حسب الصلاحيات في Template

```django
{% load custom_tags %}

<!-- طريقة 1: Filter -->
{% if request.user|has_permission:'employees.edit' %}
    <a href="{% url 'edit_employee' employee.id %}" class="btn btn-primary">
        تعديل
    </a>
{% endif %}

<!-- طريقة 2: Tag -->
{% user_has_permission 'employees.delete' as can_delete %}
{% if can_delete %}
    <button class="btn btn-danger">حذف</button>
{% endif %}

<!-- طريقة 3: Multiple Permissions -->
{% user_permissions as perms %}
{% if 'employees.edit' in perms or 'employees.manage' in perms %}
    <div class="admin-panel">
        <!-- محتوى للمدراء فقط -->
    </div>
{% endif %}
```

### 3️⃣ التحقق من صلاحيات متعددة (أي واحدة)

```python
from apps.core.decorators import any_permission_required

@login_required
@any_permission_required('employees.view', 'employees.manage')
def list_employees(request):
    # يمكن الوصول لمن لديه أي من الصلاحيتين
    employees = Employee.objects.all()
    return render(request, 'employees/list.html', {'employees': employees})
```

### 4️⃣ التحقق من صلاحيات متعددة (كلها مطلوبة)

```python
from apps.core.decorators import all_permissions_required

@login_required
@all_permissions_required('employees.view', 'employees.edit_salary')
def edit_salary(request, employee_id):
    # يحتاج الصلاحيتين معاً
    employee = get_object_or_404(Employee, id=employee_id)
    # ... منطق تعديل الراتب
    return render(request, 'employees/edit_salary.html')
```

### 5️⃣ التحقق اليدوي في View

```python
from apps.core.decorators import has_permission

@login_required
def employee_detail(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    
    # التحقق اليدوي
    can_edit = has_permission(request.user, 'employees.edit')
    can_delete = has_permission(request.user, 'employees.delete')
    
    return render(request, 'employees/detail.html', {
        'employee': employee,
        'can_edit': can_edit,
        'can_delete': can_delete,
    })
```

### 6️⃣ إضافة صلاحية مخصصة برمجياً

```python
from apps.core.models import AppModule, Permission

# في Django shell أو management command
module = AppModule.objects.get(code='employees')

Permission.objects.create(
    code='employees.export',
    name='تصدير بيانات الموظفين',
    module=module,
    description='السماح بتصدير بيانات الموظفين إلى Excel',
    is_active=True
)
```

### 7️⃣ إضافة صلاحية إلى دور موجود

```python
from apps.core.models import Role, Permission

# في Django shell
role = Role.objects.get(name='الموارد البشرية')
perm = Permission.objects.get(code='employees.export')

role.permissions.add(perm)
print(f'تم إضافة الصلاحية {perm.name} إلى {role.name}')
```

### 8️⃣ عرض كل صلاحيات مستخدم معين

```python
from django.contrib.auth.models import User
from apps.core.decorators import get_user_permissions

user = User.objects.get(username='ahmad')
permissions = get_user_permissions(user)

print(f'صلاحيات {user.username}:')
for perm in permissions:
    print(f'  - {perm}')
```

### 9️⃣ إنشاء دور مخصص جديد

```python
from apps.core.models import Role, Permission

# إنشاء الدور
role = Role.objects.create(
    name='مدير مبيعات',
    role_type='manager',
    description='مسؤول عن إدارة فريق المبيعات',
    is_system_role=False,  # دور مخصص (يمكن حذفه)
    is_active=True
)

# إضافة الصلاحيات
permissions = Permission.objects.filter(
    code__in=[
        'employees.view',
        'reports.view',
        'attendance.view'
    ]
)
role.permissions.set(permissions)
```

### 🔟 middleware للتحقق التلقائي من الصلاحيات

```python
# في config/middleware.py
class PermissionCheckMiddleware:
    """
    Middleware للتحقق من الصلاحيات بناءً على URL
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
        # تعريف الصلاحيات المطلوبة لكل مسار
        self.url_permissions = {
            r'^/employees/add/': 'employees.add',
            r'^/employees/\d+/edit/': 'employees.edit',
            r'^/employees/\d+/delete/': 'employees.delete',
        }

    def __call__(self, request):
        import re
        from apps.core.decorators import has_permission
        
        # تخطي المسارات العامة
        if request.path in ['/login/', '/logout/', '/']:
            return self.get_response(request)
        
        # التحقق من الصلاحيات
        if request.user.is_authenticated:
            for pattern, permission in self.url_permissions.items():
                if re.match(pattern, request.path):
                    if not has_permission(request.user, permission):
                        from django.shortcuts import redirect
                        from django.contrib import messages
                        messages.error(request, 'ليس لديك صلاحية للوصول')
                        return redirect('dashboard')
        
        return self.get_response(request)
```

---

## أمثلة متقدمة 🎯

### API View مع صلاحيات

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from apps.core.decorators import has_permission

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def employees_api(request):
    # التحقق من الصلاحية
    if not has_permission(request.user, 'employees.view'):
        return Response(
            {'error': 'ليس لديك صلاحية لعرض الموظفين'},
            status=403
        )
    
    employees = Employee.objects.all()
    serializer = EmployeeSerializer(employees, many=True)
    return Response(serializer.data)
```

### Context Processor لإتاحة الصلاحيات في كل Template

```python
# في apps/core/context_processors.py
from apps.core.decorators import get_user_permissions

def user_permissions(request):
    """إضافة صلاحيات المستخدم إلى context كل template"""
    if request.user.is_authenticated:
        return {
            'user_permissions': get_user_permissions(request.user)
        }
    return {'user_permissions': []}

# في settings.py
TEMPLATES = [
    {
        'OPTIONS': {
            'context_processors': [
                # ...
                'apps.core.context_processors.user_permissions',
            ],
        },
    },
]

# الاستخدام في أي template:
{% if 'employees.edit' in user_permissions %}
    <button>تعديل</button>
{% endif %}
```

### فلترة QuerySet حسب صلاحيات المستخدم

```python
from apps.core.decorators import has_permission

@login_required
def list_employees(request):
    # كل المستخدمين يمكنهم رؤية الموظفين
    employees = Employee.objects.all()
    
    # لكن فقط من لديه صلاحية خاصة يرى الرواتب
    show_salaries = has_permission(request.user, 'employees.view_salary')
    
    # الموظف العادي يرى نفسه فقط
    if request.user.profile.role.role_type == 'employee':
        employees = employees.filter(user=request.user)
    
    return render(request, 'employees/list.html', {
        'employees': employees,
        'show_salaries': show_salaries,
    })
```

---

## نصائح وأفضل الممارسات 💡

### ✅ استخدم

- `@permission_required` للصفحات الكاملة
- `has_permission()` للتحقق اليدوي في Views
- `{% if request.user|has_permission:'code' %}` في Templates
- صلاحيات محددة ودقيقة (employees.view بدلاً من employees)

### ❌ تجنب

- Hard-coding أسماء الأدوار في الكود
- التحقق من `user.profile.role.name == 'الأدمن'`
- إنشاء صلاحيات كثيرة جداً بدون داعي
- نسيان التحقق من `is_superuser`

### 🔒 للأمان

- دائماً استخدم `@login_required` قبل `@permission_required`
- تحقق من الصلاحيات في Backend و Frontend
- لا تعتمد على JavaScript فقط لإخفاء الأزرار
- استخدم `raise_exception=True` في APIs للحصول على 403

---

## الأخطاء الشائعة وحلولها 🔧

### خطأ: AttributeError: 'User' object has no attribute 'profile'

**السبب:** المستخدم ليس لديه UserProfile

**الحل:**
```python
python manage.py setup_user_profiles
```

### خطأ: صلاحية غير موجودة في القاعدة

**السبب:** لم يتم إنشاء الصلاحية بعد

**الحل:**
```python
python manage.py sync_permissions --create-basic
```

### خطأ: الأدوار لا تحتوي على صلاحيات

**السبب:** لم يتم تشغيل setup_roles بعد المزامنة

**الحل:**
```python
python manage.py setup_roles
```

---

**📖 للمزيد: راجع [PERMISSIONS_SYSTEM.md](PERMISSIONS_SYSTEM.md)**
