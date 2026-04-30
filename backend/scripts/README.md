# 🛠️ مجلد السكربتات - Scripts

هذا المجلد يحتوي على سكربتات مساعدة لإعداد وإدارة النظام.

## 📑 محتويات المجلد

### سكربتات الإعداد:

- **setup_permissions_system.bat** - سكربت إعداد نظام الصلاحيات (Windows)
- **setup_permissions_system.sh** - سكربت إعداد نظام الصلاحيات (Linux/Mac)
- **system_overview.py** - عرض شامل لحالة النظام

## 🚀 الاستخدام

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

### عرض حالة النظام:

```bash
cd backend
python scripts/system_overview.py
```

## 📝 ملاحظات

- يجب تشغيل السكربتات من داخل مجلد `backend/` أو التأكد من المسار الصحيح
- سكربتات Linux/Mac تحتاج إلى صلاحيات التنفيذ (`chmod +x`)
- لإضافة سكربتات جديدة، تأكد من توثيقها هنا
