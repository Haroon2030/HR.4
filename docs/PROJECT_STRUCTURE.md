# 📁 هيكل المشروع النظيف

## 🌲 هيكل الجذر (Root)

```
HR/
├── .github/                   # GitHub Actions (Django CI)
├── .git/                      # Git repository
├── .gitattributes             # Git attributes
├── .gitignore                 # Git ignore (محدّث)
├── .vscode/                   # VS Code settings (اختياري)
├── backend/                   # 🎯 المشروع الرئيسي
└── README.md                  # التوثيق الرئيسي (محدّث)
```

### ✅ ما تم الاحتفاظ به:
- `.git/` - تاريخ Git
- `.gitignore` - محدّث ونظيف
- `.vscode/` - إعدادات المحرر (اختياري)
- `backend/` - المشروع بالكامل
- `README.md` - توثيق شامل ومحدّث

### ❌ ما تم حذفه (تاريخي):
- `design-template/` - قوالب تصميم قديمة
- CI قديم لـ frontend غير المستخدم — يُستبدل بـ `.github/workflows/django-ci.yml`

---

## 🎯 هيكل Backend

```
backend/
├── apps/                      # Django Applications
│   ├── core/                 # النواة: نماذج الشركة/الفرع، RBAC، موافقات، إشعارات، معظم web_views
│   ├── employees/            # نماذج الموظفين والهجرات (واجهات HTTP في apps.core.web_views)
│   ├── payroll/              # مسير الرواتب (نماذج + views ويب)
│   ├── departments/          # نموذج القسم (واجهة CRUD في core.web_views)
│   ├── cost_centers/         # مراكز التكلفة
│   └── setup/                 # جداول مرجعية (جنسية، مهنة، بنك، …)
│
├── config/                    # Django Configuration
│   ├── settings/             # base / development / production
│   ├── urls.py               # المسارات الرئيسية + /health/
│   ├── api_urls.py
│   ├── web_urls.py
│   ├── health.py             # فحص صحة خفيف
│   ├── jwt_views.py          # JWT مع throttling
│   └── middleware.py
│
├── templates/                 # HTML Templates
│   ├── base.html             # ✅ القالب الرئيسي (responsive)
│   ├── pages/                # صفحات القوالب
│   │   ├── dashboard.html   # لوحة التحكم
│   │   ├── list_base.html   # قالب القوائم
│   │   └── form_base.html   # قالب النماذج
│   ├── components/           # مكونات قابلة لإعادة الاستخدام
│   │   ├── nav_item.html
│   │   ├── form_field.html
│   │   ├── stat_card.html
│   │   ├── table_actions.html
│   │   ├── status_badge.html
│   │   ├── card.html
│   │   └── empty_state.html
│   ├── auth/                 # صفحات المصادقة
│   │   └── login.html
│   ├── TEMPLATES_GUIDE.md    # دليل القوالب
│   ├── MOBILE_GUIDE.md       # دليل الموبايل
│   ├── IMPROVEMENTS.md       # التحسينات
│   └── README.md            # نظرة عامة
│
├── static/                   # Static Files
│   ├── css/
│   │   └── tailwind.min.css # Tailwind CSS (offline)
│   └── js/
│       ├── alpine.min.js    # Alpine.js
│       ├── htmx.min.js      # HTMX
│       └── lucide.min.js    # Lucide Icons
│
├── media/                    # User Uploads (فارغ)
├── staticfiles/              # Collected Static Files
│
├── manage.py                 # Django Management
├── requirements.txt          # Python Dependencies
├── db.sqlite3               # SQLite Database
└── .env                     # Environment Variables (لا يُرفع على Git)
```

### ✅ ما تم الاحتفاظ به:
- `apps/` - جميع التطبيقات
- `config/` - الإعدادات
- `templates/` - القوالب المحسّنة
- `static/` - الملفات الثابتة
- `manage.py` - أداة Django
- `requirements.txt` - المتطلبات
- `db.sqlite3` - قاعدة البيانات

### ❌ ما تم حذفه من backend (تاريخي):
- نسخ قديمة من Dockerfile داخل backend — الـ Dockerfile الحالي في جذر المشروع
- سكربتات مزامنة قديمة

---

## 🎯 مبادئ الهيكل النظيف

### 1. الفصل الواضح:
- كل تطبيق في مجلد منفصل
- إعدادات منفصلة (dev/prod)
- قوالب منظمة حسب النوع

### 2. قابلية التوسع:
- سهولة إضافة تطبيقات جديدة
- مكونات قابلة لإعادة الاستخدام
- بنية واضحة ومفهومة

### 3. التوثيق:
- README شامل
- دليل القوالب
- دليل الموبايل
- ملفات توضيحية في كل مجلد

### 4. النظافة:
- لا ملفات غير مستخدمة
- .gitignore محدّث
- بنية منطقية

---

## 🚀 إضافة تطبيق جديد

```bash
# 1. إنشاء التطبيق
cd backend
python manage.py startapp <app_name> apps/<app_name>

# 2. إضافته في INSTALLED_APPS
# config/settings/base.py

# 3. إنشاء Models
# apps/<app_name>/models.py

# 4. إنشاء Migrations
python manage.py makemigrations
python manage.py migrate

# 5. إنشاء Views & URLs
# apps/<app_name>/views.py
# apps/<app_name>/urls.py

# 6. إنشاء Templates
# templates/pages/<app_name>/
```

---

## 📦 إضافة مكتبة جديدة

```bash
# 1. تثبيت المكتبة
pip install <library_name>

# 2. تحديث requirements.txt
pip freeze > requirements.txt

# 3. إضافتها في INSTALLED_APPS (إذا لزم)
# config/settings/base.py
```

---

## 🧹 الحفاظ على النظافة

### ✅ افعل:
- استخدم .gitignore بشكل صحيح
- احذف الملفات غير المستخدمة
- وثّق التغييرات في README
- اتبع هيكل المشروع

### ❌ لا تفعل:
- رفع ملفات البيئة الافتراضية (venv/)
- رفع ملفات .env
- رفع قاعدة البيانات (db.sqlite3)
- إضافة ملفات غير ضرورية

---

**✨ المشروع الآن نظيف وجاهز للتوسع!**

**📝 آخر تحديث:** 2026-04-25
