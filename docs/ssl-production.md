# SSL / HTTPS على Dokploy — دليل الإنتاج
# =====================================

## النطاق: https://hr.alrsheed.net

**دليل كامل مع Environment وتعليمات:** [`نشر-SSL-hr.alrsheed.net.md`](نشر-SSL-hr.alrsheed.net.md)

**ملف Environment:** [`env-production-hr.alrsheed.net.example`](env-production-hr.alrsheed.net.example)

```bash
curl -s "https://hr.alrsheed.net/health/?proxy=1"
```

---

## التشخيص السريع

بعد تفعيل الشهادة، تحقق من وصول ترويسة البروكسي:

```bash
curl -s "https://YOUR_DOMAIN/health/?proxy=1"
```

يجب أن ترى:

```json
{
  "proxy": {
    "x_forwarded_proto": "https",
    "is_secure": true,
    "use_https_setting": true
  }
}
```

إن كان `x_forwarded_proto` **فارغاً** و `is_secure` **false** → البروكسي (Traefik/Nginx) لا يمرّر الترويسة — هذا سبب فشل SSL/تسجيل الدخول.

---

## 1) Environment في Dokploy (HTTPS)

```env
USE_HTTPS=true
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true

ALLOWED_HOSTS=hr.example.com,72.61.107.230
CSRF_TRUSTED_ORIGINS=https://hr.example.com

CORS_ALLOWED_ORIGINS=https://hr.example.com
```

**لا تخلط** `http://` و `https://` في `CSRF_TRUSTED_ORIGINS`.

---

## 2) Nginx (إن كان أمام التطبيق)

```nginx
location / {
    proxy_pass http://127.0.0.1:8082;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
}
```

بدون `X-Forwarded-Proto` Django يعتقد أن الطلب HTTP حتى لو المستخدم على HTTPS.

---

## 3) Dokploy / Traefik

- فعّل TLS من واجهة Dokploy (Let's Encrypt) على **النطاق** وليس IP:8082 فقط.
- Traefik يمرّر `X-Forwarded-Proto` تلقائياً عند TLS termination.
- إن كان لديك **Nginx خارجي** + Dokploy، Nginx يجب أن يمرّر التروises للحاوية.

---

## 4) وكيل البصمة (biometric bridge)

حدّث `config.env` في الفرع:

```env
SERVER_URL=https://hr.example.com
```

(بدون `:8082` إن كان HTTPS على 443)

---

## 5) أعراض المشكلة

| العرض | السبب |
|-------|--------|
| حلقة إعادة توجيه | `USE_HTTPS=true` بدون `X-Forwarded-Proto` |
| CSRF / فشل تسجيل الدخول | `CSRF_TRUSTED_ORIGINS` لا يطابق URL أو كوكي Secure على HTTP |
| Mixed content | روابط `http://` في الإعدادات |

---

## 6) فحص من داخل الحاوية

```bash
docker exec -it <container> check-production
python manage.py check_ssl_proxy
```
