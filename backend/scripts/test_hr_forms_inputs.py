"""فحص سريع: كل نماذج HR تُعرض والمدخلات موجودة."""
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

    r = c.get(reverse("web:hr_forms_index"))
    html_index = r.content.decode("utf-8", errors="replace")
    print(f"INDEX: HTTP {r.status_code}")
    print(f"  smart-search script: {'hr-employee-smart-search' in html_index}")
    print(f"  hrFormsApp: {'hrFormsApp' in html_index}")

    r = c.get(reverse("web:hr_forms_employee_search"), {"q": "Test"})
    print(f"SEARCH API: HTTP {r.status_code} total={r.json().get('total')}")

    print("\n=== ALL FORMS ===")
    failed = []
    for form in HR_FORMS:
        key = form["key"]
        url = reverse(
            "web:hr_form_print",
            kwargs={"form_type": key, "employee_id": emp.id},
        )
        r = c.get(url)
        html = r.content.decode("utf-8", errors="replace")
        status = r.status_code
        inputs = len(re.findall(r"<input\b", html))
        textareas = len(re.findall(r"<textarea\b", html))
        selects = len(re.findall(r"<select\b", html))
        checkboxes = len(re.findall(r'type="checkbox"', html))
        dates = len(re.findall(r'type="date"', html))
        has_transform_script = "querySelectorAll('span.blank')" in html
        mark = "OK" if status == 200 else "FAIL"
        print(
            f"{mark} {key}: HTTP {status} | "
            f"in={inputs} ta={textareas} sel={selects} cb={checkboxes} date={dates} "
            f"script={has_transform_script}"
        )
        if status != 200:
            failed.append((key, status))

    r = c.get(
        reverse(
            "web:hr_form_print",
            kwargs={"form_type": "nonexistent", "employee_id": emp.id},
        )
    )
    print(f"\nUNKNOWN FORM: HTTP {r.status_code} (expect 404)")

    print(f"\nFailed: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
