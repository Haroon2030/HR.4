# نشر HTTPS — https://hr.alrsheed.net

دليل خطوة بخطوة لتفعيل SSL على نظام HR Pro في Dokploy.

**ملف Environment (placeholders):** [`env-production-hr.alrsheed.net.example`](env-production-hr.alrsheed.net.example)

---

## Environment — نسخ لمرة واحدة (Dokploy)

1. افتح [`env-production-hr.alrsheed.net.dokploy.txt`](env-production-hr.alrsheed.net.dokploy.txt) (أو `.example`)
2. استبدل `YOUR_*` بقيمك
3. **Ctrl+A** → انسخ الكل → Dokploy → Environment → الصق → **Deploy**

### قواعد الفواصل (قوائم متعددة القيم)

| المتغير | الصيغة — **بدون مسافات** بعد الفاصلة |
|---------|--------------------------------------|
| `ALLOWED_HOSTS` | `hr.alrsheed.net,72.61.107.230,localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | `https://hr.alrsheed.net` |
| `CORS_ALLOWED_ORIGINS` | `https://hr.alrsheed.net` |

> **لا تخلط** `http://` و `https://` في `CSRF_TRUSTED_ORIGINS`.

---

## قبل البدء

| البند | المطلوب |
|-------|---------|
| DNS | سجل `A` لـ `hr.alrsheed.net` → `72.61.107.230` |
| Dokploy | التطبيق يعمل على المنفذ الداخلي `8082` |
| الشهادة | Let's Encrypt من Dokploy أو Nginx |
| البروكسي | **يجب** تمرير `X-Forwarded-Proto: https` |

---

## الخطوة 1 — DNS

في لوحة النطاق (Hostinger / Cloudflare):

```
hr.alrsheed.net  →  A  →  72.61.107.230
```

انتظر انتشار DNS (5–30 دقيقة)، ثم:

```bash
nslookup hr.alrsheed.net
```

---

## الخطوة 2 — شهادة SSL في Dokploy

1. افتح **Dokploy** → تطبيق HR
2. **Domains** → Add Domain → `hr.alrsheed.net`
3. فعّل **HTTPS / Let's Encrypt**
4. احفظ — Traefik يتولى TLS على المنفذ 443

> إن استخدمت **Nginx خارجي** أمام Dokploy، راجع [الخطوة 5](#الخطوة-5--nginx-إن-وُجد).

---

## الخطوة 3 — Environment (Dokploy)

1. Dokploy → التطبيق → **Environment**
2. استبدل قيم HTTP القديمة بالنسخة HTTPS أدناه
3. **لا ترفع** هذا الملف إلى Git — الأسرار في Dokploy فقط

### ما يتغيّر عن HTTP (IP:8082)

| المتغير | HTTP (قديم) | HTTPS (جديد) |
|---------|-------------|--------------|
| `ALLOWED_HOSTS` | `72.61.107.230,...` | `hr.alrsheed.net,72.61.107.230,...` |
| `CSRF_TRUSTED_ORIGINS` | `http://72.61.107.230:8082` | `https://hr.alrsheed.net` |
| `USE_HTTPS` | `false` | `true` |
| `SECURE_SSL_REDIRECT` | `false` | `true` |
| `SESSION_COOKIE_SECURE` | `false` | `true` |
| `CSRF_COOKIE_SECURE` | `false` | `true` |
| `CORS_ALLOWED_ORIGINS` | `http://...` | `https://hr.alrsheed.net` |

### Environment كامل (انسخ وعدّل الأسرار)

```env
# ═══════════════════════════════════════════════════════════════════════════════
# HR Pro — إنتاج HTTPS: https://hr.alrsheed.net
# Dokploy → Environment — لا ترفع إلى Git
# ═══════════════════════════════════════════════════════════════════════════════

DJANGO_ENV=production
DJANGO_SETTINGS_MODULE=config.settings
TIME_ZONE=Asia/Riyadh
DEBUG=False
PORT=8082

SECRET_KEY=ضع-مفتاحك-السري-هنا

DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-morning-rice-ab19c977-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require
DB_SSLMODE=require
CONN_MAX_AGE=600
MIGRATE_MAX_RETRIES=5
MIGRATE_RETRY_SECS=5

# ─── HTTPS ────────────────────────────────────────────────────────────────────
ALLOWED_HOSTS=hr.alrsheed.net,72.61.107.230,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://hr.alrsheed.net

USE_HTTPS=true
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_EXPIRE_AT_BROWSER_CLOSE=true
SESSION_COOKIE_AGE=28800

CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://hr.alrsheed.net

GUNICORN_WORKERS=3
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=ضع-كلمة-مرور-قوية
DJANGO_SUPERUSER_EMAIL=admin@alrsheed.net

USE_R2=True
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_BUCKET_NAME=erphr
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_REGION=auto
R2_PUBLIC_DOMAIN=
R2_SIGNED_URLS=true
R2_SIGNED_URL_EXPIRE=3600
R2_PROXY_MEDIA=true

EMAIL_HOST=smtp.hostinger.com
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_USE_TLS=False
EMAIL_HOST_USER=your-mailbox@alrsheed.net
EMAIL_HOST_PASSWORD=your-email-password
DEFAULT_FROM_EMAIL=HR Pro <your-mailbox@alrsheed.net>
HR_NOTIFICATION_EMAIL=admin@alrsheed.net
EMAIL_TIMEOUT=30

BIOMETRIC_MOCK_MODE=false
BIOMETRIC_ZK_TIMEOUT=20
BIOMETRIC_ZK_OMIT_PING=true

ATTENDANCE_AGENT_API_KEY=your-agent-api-key
ATTENDANCE_REQUIRE_INGEST_SIGNATURE=true
AGENT_GLOBAL_KEY_LIST_DEVICES=false
AGENT_GLOBAL_KEY_ALLOW_INGEST=true
DRF_ATTENDANCE_AGENT_THROTTLE=120/hour

BACKUP_STORAGE_DIR=/app/backups
BACKUP_ENABLED=true
BACKUP_BEFORE_MIGRATE=true
BACKUP_NOTIFY_ON_SUCCESS=true
BACKUP_NOTIFY_ON_FAILURE=true
BACKUP_NOTIFY_EMAIL=admin@alrsheed.net
BACKUP_SCHEDULE=0 3 * * *

OPERATIONS_REPORT_CRON=true
OPERATIONS_REPORT_CRON_SCHEDULE=* * * * *

WHATSAPP_ENABLED=true
EVOLUTION_API_URL=http://72.61.107.230:8081
EVOLUTION_API_KEY=your-evolution-global-api-key
EVOLUTION_INSTANCE=hr
EVOLUTION_API_TIMEOUT=20
WHATSAPP_DEFAULT_COUNTRY=966
```

**ملاحظات:**

- `EVOLUTION_API_URL` يبقى `http://72.61.107.230:8081` — اتصال **داخلي** من الحاوية إلى Evolution على نفس السيرفر.
- **لا تخلط** `http://` و `https://` في `CSRF_TRUSTED_ORIGINS`.

---

## الخطوة 4 — Redeploy

1. Dokploy → **Deploy / Redeploy**
2. راقب السجلات — يجب أن ينجح `migrate` بدون `ImproperlyConfigured`

### Gunicorn — مهم للحاوية Docker

في **Dockerfile** الافتراضي:

```text
gunicorn config.wsgi:application --bind 0.0.0.0:8082
```

| العنوان | متى |
|---------|-----|
| `0.0.0.0:8082` | ✅ داخل Docker — Traefik/Nginx يصل للحاوية |
| `127.0.0.1:8082` | ❌ يعمل داخل الحاوية فقط — الموقع لا يفتح من الخارج |

إن غيّرت **Start Command** في Dokploy يدوياً، تأكد أنه `0.0.0.0` وليس `127.0.0.1`.

اختياري في Environment:

```env
GUNICORN_BIND=0.0.0.0:8082
```

---

## الخطوة 5 — Nginx (إن وُجد)

إن كان Nginx أمام التطبيق (وليس Traefik فقط)، **هذا سبب المشكلة الشائعة** — البروكسي لا يرسل header:

```nginx
server {
    listen 443 ssl;
    server_name hr.alrsheed.net;

    # ssl_certificate ... (Let's Encrypt)

    location / {
        proxy_pass http://127.0.0.1:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

بدون `X-Forwarded-Proto` → Django يظن الطلب HTTP → فشل تسجيل الدخول أو حلقة redirect.

---

## الخطوة 6 — التحقق

### 6.1 ترويسة البروكسي (الأهم)

```bash
curl -s "https://hr.alrsheed.net/health/?proxy=1"
```

**النتيجة المطلوبة:**

```json
{
  "status": "ok",
  "database": "ok",
  "proxy": {
    "x_forwarded_proto": "https",
    "is_secure": true,
    "use_https_setting": true
  }
}
```

| `x_forwarded_proto` | `is_secure` | المعنى |
|---------------------|-------------|--------|
| `https` | `true` | ✅ SSL يعمل |
| فارغ | `false` | ❌ أصلح Nginx/Traefik headers |

### 6.2 من داخل الحاوية

```bash
docker exec -it <container_name> python manage.py check_ssl_proxy
```

### 6.3 المتصفح

1. افتح `https://hr.alrsheed.net`
2. قفل أخضر في شريط العنوان
3. سجّل الدخول — يجب أن يعمل بدون CSRF error

---

## الخطوة 7 — وكيل البصمة (الفروع)

في `backend/scripts/biometric_bridge/config.env` على PC الفرع:

```env
SERVER_URL=https://hr.alrsheed.net
AGENT_API_KEY=مفتاح-الجهاز-من-HR
```

ثم أعد تشغيل الوكيل:

```bat
run_agent.bat
```

---

## استكشاف الأخطاء

| العرض | السبب | الحل |
|-------|--------|------|
| حلقة redirect لا نهائية | `USE_HTTPS=true` بدون `X-Forwarded-Proto` | أصلح Nginx (الخطوة 5) |
| CSRF verification failed | `CSRF_TRUSTED_ORIGINS` لا يطابق URL | `https://hr.alrsheed.net` فقط |
| تسجيل الدخول يفشل بعد SSL | كوكي Secure على HTTP داخلي | تأكد من header البروكسي |
| `DisallowedHost` | النطاق غير في `ALLOWED_HOSTS` | أضف `hr.alrsheed.net` |
| وكيل البصمة 403 | `SERVER_URL` لا يزال `http://IP:8082` | غيّر إلى `https://hr.alrsheed.net` |
| migrate يفشل عند الإقلاع | `EVOLUTION_API_KEY` قصير (قديم) | حدّث الكود أو استخدم مفتاحاً أطول |

---

## قائمة تحقق سريعة

- [ ] DNS `hr.alrsheed.net` → `72.61.107.230`
- [ ] Let's Encrypt مفعّل في Dokploy
- [ ] Environment HTTPS (الخطوة 3)
- [ ] Redeploy ناجح
- [ ] `curl .../health/?proxy=1` → `x_forwarded_proto=https`
- [ ] تسجيل الدخول يعمل
- [ ] `SERVER_URL=https://hr.alrsheed.net` في وكيل البصمة

---

## مراجع

- [`env-production-hr.alrsheed.net.example`](env-production-hr.alrsheed.net.example) — Environment كامل
- [`ssl-production.md`](ssl-production.md) — تفاصيل تقنية SSL/Proxy
