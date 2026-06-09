"""فحص شامل: نماذج HR + أزرار الإجراءات + المدخلات بعد تحويل JS."""
import os
import re
import sys
from pathlib import Path

import django

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

from apps.core.models import Branch, Company
from apps.core.web_views.hr_forms import HR_FORMS
from apps.employees.models import Employee

User = get_user_model()
DATE_HINTS = ["تاريخ", "بتاريخ", "بدء", "انتهاء", "إلى:", "من:"]


def simulate_js_transform(html: str) -> dict:
    """محاكاة تحويل _print_base.html للمدخلات."""
    spans = len(re.findall(r'<span class="blank"', html))
    blocks = len(re.findall(r'<div class="blank-block"', html))
    boxes = len(re.findall(r'<span class="box"', html))
    selects = len(re.findall(r"<select\b", html))
    existing_inputs = len(re.findall(r"<input\b", html))
    existing_ta = len(re.findall(r"<textarea\b", html))

    date_blanks = 0
    for m in re.finditer(
        r'<div class="field"[^>]*>\s*<span class="label">([^<]*)</span>\s*<span class="blank"',
        html,
    ):
        label = m.group(1)
        if any(h in label for h in DATE_HINTS):
            date_blanks += 1

    return {
        "spans_to_input": spans,
        "blocks_to_ta": blocks,
        "boxes_to_cb": boxes,
        "selects": selects,
        "existing_inputs": existing_inputs,
        "existing_ta": existing_ta,
        "date_fields": date_blanks + 1,  # +1 doc date picker
        "total_inputs_after_js": existing_inputs + spans + boxes,
        "total_ta_after_js": existing_ta + blocks,
    }


def main() -> int:
    company, _ = Company.objects.get_or_create(name="Test Co")
    branch, _ = Branch.objects.get_or_create(
        name="Test Branch", code="TB1", company=company
    )
    emp, _ = Employee.objects.get_or_create(
        name="Test Employee",
        branch=branch,
        defaults={"status": Employee.Status.ACTIVE},
    )
    user, created = User.objects.get_or_create(
        username="test_hr_forms",
        defaults={"is_superuser": True, "is_staff": True},
    )
    if created:
        user.set_password("test123")
        user.save()

    c = Client()
    assert c.login(username="test_hr_forms", password="test123")
    errors = []

    print("=" * 60)
    print("1) صفحة الفهرس وأزرار الإجراءات")
    print("=" * 60)
    r = c.get(reverse("web:hr_forms_index"))
    html = r.content.decode("utf-8", errors="replace")
    checks = {
        "HTTP 200": r.status_code == 200,
        "hr-employee-smart-search.js": "hr-employee-smart-search" in html,
        "registerHrFormsApp": "registerHrFormsApp" in html,
        "no 500-employee seed": "employeesSeed" not in html,
        "openForm()": "openForm(" in html or "registerHrFormsApp" in html,
        "auto_print param": "auto_print=1" in html,
        "زر فتح النموذج": "فتح النموذج" in html,
        "زر الطباعة": "hr-btn-print" in html,
        "employee search URL": "hr-forms-search-url" in html,
    }
    for name, ok in checks.items():
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {name}")
        if not ok:
            errors.append(f"index:{name}")

    form_keys_in_index = re.findall(r"openForm\('([^']+)'", html)
    missing_in_index = [f["key"] for f in HR_FORMS if f["key"] not in form_keys_in_index]
    if missing_in_index:
        print(f"  [FAIL] نماذج ناقصة في الفهرس: {missing_in_index}")
        errors.append("index:missing_forms")
    else:
        print(f"  [OK] كل {len(HR_FORMS)} نموذج له زر فتح + طباعة")

    print()
    print("=" * 60)
    print("2) API بحث الموظفين")
    print("=" * 60)
    for q in ["Test", "موظف", ""]:
        r = c.get(reverse("web:hr_forms_employee_search"), {"q": q})
        data = r.json() if r.status_code == 200 else {}
        print(f"  q='{q}' → HTTP {r.status_code} total={data.get('total', 'N/A')}")
        if r.status_code != 200:
            errors.append(f"search:{q}")

    print()
    print("=" * 60)
    print("3) كل النماذج — عرض + مدخلات + أزرار شريط الأدوات")
    print("=" * 60)
    for form in HR_FORMS:
        key = form["key"]
        url = reverse("web:hr_form_print", kwargs={"form_type": key, "employee_id": emp.id})
        r = c.get(url)
        html = r.content.decode("utf-8", errors="replace")
        t = simulate_js_transform(html)

        toolbar = {
            "print_btn": "window.print()" in html,
            "back_link": reverse("web:hr_forms_index") in html or "hr_forms_index" in html,
            "auto_print_script": "auto_print" in html,
            "transform_script": "querySelectorAll('span.blank')" in html,
            "form_serial": "serial-no" in html,
            "date_picker": 'type="date"' in html and "date-picker" in html,
        }

        ok = r.status_code == 200 and all(toolbar.values())
        mark = "OK" if ok else "FAIL"
        print(
            f"  [{mark}] {key}: HTTP {r.status_code} | "
            f"inputs≈{t['total_inputs_after_js']} ta≈{t['total_ta_after_js']} "
            f"sel={t['selects']} cb≈{t['boxes_to_cb']}"
        )
        if not ok:
            failed_parts = [k for k, v in toolbar.items() if not v]
            if r.status_code != 200:
                failed_parts.insert(0, f"HTTP {r.status_code}")
            print(f"         missing: {failed_parts}")
            errors.append(f"form:{key}")

        # auto_print variant
        r2 = c.get(url + "?auto_print=1")
        if r2.status_code != 200:
            print(f"         [FAIL] auto_print=1 → HTTP {r2.status_code}")
            errors.append(f"form:{key}:auto_print")

    print()
    print("=" * 60)
    print("4) حالات خاصة")
    print("=" * 60)
    r = c.get(reverse("web:hr_form_print", kwargs={"form_type": "nonexistent", "employee_id": emp.id}))
    print(f"  [{'OK' if r.status_code == 404 else 'FAIL'}] نموذج غير موجود → HTTP {r.status_code}")

    r = c.get(reverse("web:hr_form_print", kwargs={"form_type": "custody_clearance", "employee_id": emp.id}))
    html = r.content.decode("utf-8", errors="replace")
    custody_script = "custody-receiving-admin" in html and "syncReceivingSigRole" in html
    print(f"  [{'OK' if custody_script else 'FAIL'}] سكربت مزامنة توقيع العهدة")

    r = c.get(reverse("web:hr_form_print", kwargs={"form_type": "warning_notice", "employee_id": emp.id}))
    html = r.content.decode("utf-8", errors="replace")
    warning_ok = "warning_serial" in html and 'type="text"' in html
    print(f"  [{'OK' if warning_ok else 'FAIL'}] نموذج الإنذار — رقم سريال + حقل إفادة")

    r = c.get(reverse("web:hr_form_print", kwargs={"form_type": "final_settlement", "employee_id": emp.id}))
    html = r.content.decode("utf-8", errors="replace")
    fs_ok = "total_entitlement" in html or "التسوية المالية" in html
    print(f"  [{'OK' if fs_ok else 'FAIL'}] نموذج التصفية — جدول مالي")

    print()
    print("=" * 60)
    if errors:
        print(f"النتيجة: فشل {len(errors)} فحص(ات)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("النتيجة: كل الفحوصات نجحت ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
