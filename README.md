# 👥 نظام إدارة الموارد البشرية (HR System)

نظام شامل ونظيف لإدارة الموارد البشرية مبني باستخدام Django مع واجهة عصرية ومتجاوبة.

## ✨ الميزات الرئيسية

### 📊 الجاهز للاستخدام:
- ✅ نظام مصادقة متكامل (تسجيل دخول/خروج)
- ✅ إدارة المستخدمين والصلاحيات (Roles & Permissions)
- ✅ لوحة تحكم تفاعلية
- ✅ واجهة متجاوبة بالكامل (Desktop, Tablet, Mobile)
- ✅ قوالب جاهزة وقابلة لإعادة الاستخدام
- ✅ دعم كامل للغة العربية

### 🔜 قيد التطوير:
- ⏳ إدارة الموظفين
- ⏳ إدارة الأقسام
- ⏳ نظام الحضور والغياب
- ⏳ إدارة الإجازات
- ⏳ نظام الرواتب

## 🛠️ التقنيات المستخدمة

### Backend:
- **Django 5.2.12** - إطار عمل Python قوي
- **Django REST Framework** - لبناء APIs
- **SQLite** - قاعدة بيانات (قابلة للتغيير بسهولة)
- **Python 3.14**

### Frontend:
- **Tailwind CSS** (Offline) - تصميم عصري
- **Alpine.js** - تفاعلية بسيطة
- **HTMX** (اختياري) - تحديثات ديناميكية
- **Lucide Icons** - أيقونات SVG جميلة
- **خط Cairo** - للغة العربية

## 📁 هيكل المشروع

```
HR/
├── backend/                    # المشروع الرئيسي
│   ├── apps/                  # تطبيقات Django
│   │   ├── core/             # التطبيق الأساسي (مصادقة، صلاحيات)
│   │   ├── employees/        # إدارة الموظفين (قيد التطوير)
│   │   ├── departments/      # إدارة الأقسام (قيد التطوير)
│   │   ├── attendance/       # الحضور والغياب (قيد التطوير)
│   │   ├── leaves/           # الإجازات (قيد التطوير)
│   │   └── payroll/          # الرواتب (قيد التطوير)
│   │
│   ├── config/               # إعدادات Django
│   │   ├── settings/        # إعدادات منفصلة (dev/prod)
│   │   ├── urls.py          # مسارات المشروع
│   │   └── middleware.py    # Middleware مخصص
│   │
│   ├── templates/            # قوالب HTML
│   │   ├── base.html        # القالب الرئيسي (responsive)
│   │   ├── pages/           # صفحات القوالب
│   │   ├── components/      # مكونات قابلة لإعادة الاستخدام
│   │   ├── TEMPLATES_GUIDE.md
│   │   ├── MOBILE_GUIDE.md
│   │   └── README.md
│   │
│   ├── static/              # ملفات ثابتة
│   │   ├── css/
│   │   └── js/
│   │
│   ├── manage.py            # أداة إدارة Django
│   └── requirements.txt     # المتطلبات
│
├── docs/                   # الوثائق والتوجيهات
│   ├── CHANGELOG.md
│   ├── PERMISSIONS_SYSTEM.md
│   ├── PROJECT_STRUCTURE.md
│   └── USAGE_GUIDE.md
│
├── .gitignore              # ملفات Git المستبعدة
└── README.md              # هذا الملف
```

## 🚀 التثبيت والتشغيل

### المتطلبات:
- Python 3.10 أو أحدث
- pip

### خطوات التثبيت:

```bash
# 1. استنساخ المشروع
git clone <repository-url>
cd HR

# 2. إنشاء بيئة افتراضية (اختياري لكن موصى به)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. تثبيت المتطلبات
cd backend
pip install -r requirements.txt

# 4. تطبيق الهجرات (Migrations)
python manage.py migrate

# 5. إنشاء مستخدم مدير (اختياري)
python manage.py createsuperuser

# 6. تشغيل السيرفر
python manage.py runserver
```

### الوصول للموقع:
- الموقع الرئيسي: http://127.0.0.1:8000/
- لوحة الإدارة: http://127.0.0.1:8000/admin/
- API: http://127.0.0.1:8000/api/

## 📱 التصميم المتجاوب

النظام محسّن بالكامل للأجهزة المختلفة:
- 📱 **الموبايل**: قائمة منزلقة، أزرار كبيرة، نصوص واضحة
- 📟 **التابلت**: تخطيط مرن ومتوازن
- 💻 **Desktop**: استغلال كامل للمساحة

راجع [MOBILE_GUIDE.md](backend/templates/MOBILE_GUIDE.md) للتفاصيل.

## 🎨 نظام القوالب

النظام يحتوي على قوالب جاهزة وبسيطة:
- `list_base.html` - لعرض القوائم والجداول
- `form_base.html` - لنماذج الإضافة والتعديل
- مكونات قابلة لإعادة الاستخدام (form_field, stat_card, إلخ)

راجع [TEMPLATES_GUIDE.md](backend/templates/TEMPLATES_GUIDE.md) للأمثلة.

## 🔧 الإعدادات

### إعدادات التطوير:
```bash
python manage.py runserver --settings=config.settings.development
```

### إعدادات الإنتاج:
```bash
python manage.py runserver --settings=config.settings.production
```

## 📦 إضافة وحدات جديدة

لإضافة وحدة جديدة (مثل: التدريب):

```bash
# 1. إنشاء التطبيق
cd backend
python manage.py startapp training apps/training

# 2. إضافته في INSTALLED_APPS
# في config/settings/base.py

# 3. إنشاء Models, Views, Templates
# راجع apps/core كمثال

# 4. إنشاء Migrations
python manage.py makemigrations
python manage.py migrate
```

## 🎯 الحالة الحالية

### ✅ جاهز:
- بنية المشروع الأساسية
- نظام المصادقة
- إدارة الصلاحيات
- قوالب متجاوبة
- لوحة التحكم
- نظام القوالب البسيط

### 🔄 قيد التطوير:
- تطبيقات HR الخمسة (employees, departments, attendance, leaves, payroll)
- APIs
- تقارير
- إشعارات

## 🤝 المساهمة

المشروع مفتوح للتطوير! اتبع هذه الخطوات:

1. Fork المشروع
2. أنشئ branch جديد (`git checkout -b feature/amazing-feature`)
3. Commit التغييرات (`git commit -m 'Add amazing feature'`)
4. Push للـ branch (`git push origin feature/amazing-feature`)
5. افتح Pull Request

## 📄 الترخيص

هذا المشروع مفتوح المصدر.

## 👨‍💻 المطور

**هارون الأهدل**
- 📱 0531847156

## � الوثائق الإضافية

للمزيد من التفاصيل، راجع الملفات التالية في مجلد [docs/](docs/):

- **[PERMISSIONS_SYSTEM.md](docs/PERMISSIONS_SYSTEM.md)** - شرح نظام الصلاحيات الديناميكي
- **[DYNAMIC_PERMISSIONS_COMPLETED.md](docs/DYNAMIC_PERMISSIONS_COMPLETED.md)** - تفاصيل إنجاز نظام الصلاحيات
- **[PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)** - هيكل المشروع المفصل
- **[CHANGELOG.md](docs/CHANGELOG.md)** - سجل التغييرات والتحديثات
- **[USAGE_GUIDE.md](docs/USAGE_GUIDE.md)** - دليل الاستخدام
- **[example_add_module.py](docs/example_add_module.py)** - مثال إضافة وحدة جديدة

## �📝 ملاحظات

- المشروع نظيف وقابل للتوسع بسهولة
- كل التطبيقات منفصلة ومستقلة
- القوالب بسيطة وموثقة
- مناسب للتطوير السريع

---

**⚠️ ملاحظة مهمة:** المشروع في مرحلة التطوير النشط. بعض الميزات قيد الإنشاء.

**✨ استمتع بالتطوير!**
