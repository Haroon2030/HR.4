# نظام إدارة الموارد البشرية (HR ERP)

نظام موارد بشرية متعدد الفروع مبني على **Django 5** مع واجهة ويب عربية (RTL) باستخدام **Tailwind CSS** و**Alpine.js**. مصمّم لشركة واحدة بعدة فروع، مع صلاحيات ديناميكية، دورة موافقات، ومسير رواتب شهري.

## ما هو جاهز في المشروع

| المجال | الوصف |
|--------|--------|
| **الموظفون** | ملف موظف كامل، مرفقات، إجازات، سلف، عهد، رحلات، غياب، كشوف، سجل إفادات، رصيد مخصصات (ledger) |
| **الموافقات** | دورة موافقات متعددة المراحل + طلبات توظيف + صندوق وارد |
| **الرواتب** | مسير شهري لكل فرع، قفل، إعادة بناء، تصدير Excel |
| **التقارير** | تقارير جاهزة (قوائم وإحصائيات) |
| **النماذج الرسمية** | نماذج قابلة للطباعة (إجازة، تسوية، إنذار، إلخ) |
| **المنظمة** | فروع، أقسام، مراكز تكلفة، جداول إعداد (جنسية، مهنة، بنك، …) |
| **المستخدمون والأدوار** | RBAC مع تزامن الصلاحيات من الـ decorators |
| **النسخ الاحتياطي** | `backup_db`، رفع R2، إشعارات بريد، سجل في لوحة الإدارة |
| **API** | JWT + مسارات أساسية (شركات، فروع، أدوار، مستخدمون، `/api/v1/me/`) — توثيق OpenAPI عبر `drf-spectacular`؛ Swagger لـ staff في الإنتاج |
| **النشر** | Docker + Gunicorn، إعدادات إنتاج (PostgreSQL، HTTPS اختياري) |

## التقنيات

- **Backend:** Django 5.2، Django REST Framework، SimpleJWT (مع token blacklist)، django-filter، simple-history، WhiteNoise، storages (R2).
- **Frontend (القوالب):** Tailwind (offline)، Alpine.js، Lucide.
- **قاعدة البيانات:** `DATABASE_URL` واحد (Neon PostgreSQL) للمحلي والإنتاج؛ راجع `docs/قاعدة-بيانات-موحدة.md`.

## هيكل المشروع (مختصر)

```
HR/
├── backend/                 # مشروع Django
│   ├── apps/
│   │   ├── core/           # نواة: صلاحيات، موافقات، إشعارات، واجهات ويب كثيرة
│   │   ├── employees/      # نماذج وبيانات الموظفين (الـ HTTP في core.web_views)
│   │   ├── payroll/        # مسير الرواتب
│   │   ├── departments/    # الأقسام (نماذج؛ الواجهة في core)
│   │   ├── cost_centers/   # مراكز التكلفة
│   │   └── setup/          # جداول الإعداد المرجعية
│   ├── config/             # إعدادات، urls، middleware
│   ├── templates/          # قوالب HTML
│   ├── static/
│   ├── manage.py
│   └── requirements.txt
├── docker/                  # entrypoint، cron نسخ احتياطي
├── docs/                    # توثيق إضافي
├── Dockerfile
├── .env.example
└── README.md
```

> **ملاحظة:** لا توجد تطبيقات منفصلة باسم `attendance/` أو `leaves/` — الحضور النصي ضمن ملف الموظف (`attendance_notes`)، والإجازات ضمن تطبيق الموظفين ودورة الموافقات. صلاحيات `leaves.*` قد تُستخدم كـ legacy مع سير العمل الفعلي عبر `employees.edit`.

## التشغيل المحلي

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env   # ثم عدّل القيم
python manage.py migrate
python manage.py runserver
```

- الموقع: `http://127.0.0.1:8000/`
- لوحة الإدارة: `http://127.0.0.1:8000/admin/`
- فحص الصحة (للبروكسي): `http://127.0.0.1:8000/health/`

## الإنتاج

- عيّن `DJANGO_ENV=production` واملأ `.env` حسب `.env.example` (SECRET_KEY، ALLOWED_HOSTS، HTTPS، قاعدة البيانات، R2 إن لزم).
- النشر عبر Docker: الهجرات وتجميع الملفات الثابتة تُنفَّذ في `docker/entrypoint.sh`.

## الاختبارات و CI

```bash
cd backend
python manage.py test
```

على GitHub: سير عمل **Django CI** يشغّل `check`، `migrate`، و`test` على كل push/PR لـ `main`.

## الوثائق

راجع مجلد [docs/](docs/) وخاصة:

- [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [PERMISSIONS_SYSTEM.md](docs/PERMISSIONS_SYSTEM.md)
- [ROADMAP.md](docs/ROADMAP.md) — مراحل التطوير القادمة
- [CHANGELOG.md](docs/CHANGELOG.md)

## الترخيص والمساهمة

المشروع مفتوح للتطوير الداخلي؛ لأي مساهمة استخدم branch منفصل ثم Pull Request.

---

**المطور:** هارون الأهدل
