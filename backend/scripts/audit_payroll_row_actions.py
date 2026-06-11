"""فحص أزرار صف المسير: عرض · تعديل · حذف — بدون إضافة."""
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
from apps.payroll.models import PayrollRun
from apps.setup.models import Sponsorship

User = get_user_model()


def _login_admin(client: Client):
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.create_superuser("audit_admin", "audit@test.local", "pass")
    client.force_login(user)
    return user


def _assert_buttons(html: str, *, draft: bool, label: str) -> list[str]:
    errors = []
    view_count = len(re.findall(r'class="hr-act hr-act--view"', html))
    edit_count = len(re.findall(r'class="hr-act hr-act--edit"', html))
    delete_count = len(re.findall(r'class="hr-act hr-act--delete"', html))
    add_count = len(re.findall(r'hr-act--add|data-lucide="plus"|title="إضافة"', html))

    if view_count < 1:
        errors.append(f"{label}: زر العرض (فحص) مفقود")
    if draft and edit_count < 1:
        errors.append(f"{label}: زر التعديل مفقود للمسودة")
    if not draft and edit_count > 0:
        errors.append(f"{label}: زر التعديل يظهر لمسير غير مسودة")
    if draft and delete_count < 1:
        errors.append(f"{label}: زر الحذف (مسح) مفقود للمسودة")
    if not draft and delete_count > 0:
        errors.append(f"{label}: زر الحذف يظهر لمسير غير مسودة")
    if add_count > 0:
        errors.append(f"{label}: يوجد زر إضافة في صف الإجراءات (غير مطلوب)")
    return errors


def main() -> int:
    client = Client()
    _login_admin(client)

    company, _ = Company.objects.get_or_create(name="Audit Co")
    branch, _ = Branch.objects.get_or_create(name="Audit Branch", code="AUD01", company=company)
    sponsorship, _ = Sponsorship.objects.get_or_create(code="AUDSP", defaults={"company_name": "كفالة تدقيق"})

    draft = PayrollRun.objects.filter(
        status=PayrollRun.Status.DRAFT,
    ).exclude(run_kind=PayrollRun.RunKind.DETAILED).first()
    if not draft:
        draft = PayrollRun.objects.create(
            branch=branch,
            company=company,
            period_year=2026,
            period_month=6,
            salary_mode=PayrollRun.SalaryMode.TRANSFER,
            run_kind=PayrollRun.RunKind.STANDARD,
            sponsorship=sponsorship,
            status=PayrollRun.Status.DRAFT,
            employees_count=1,
            total_net=100,
        )

    locked = PayrollRun.objects.filter(status=PayrollRun.Status.LOCKED).first()

    errors: list[str] = []

    list_url = reverse("web:list_payroll_runs")
    resp = client.get(f"{list_url}?year=2026&month=6&salary_mode=transfer")
    if resp.status_code != 200:
        errors.append(f"قائمة المسير: HTTP {resp.status_code}")
    else:
        html = resp.content.decode("utf-8", errors="replace")
        if "hr-act--view" not in html:
            errors.append("قائمة المسير: لا توجد أزرار عرض موحّدة")
        if "hr-act--add" in html or 'title="إضافة"' in html:
            errors.append("قائمة المسير: يوجد زر إضافة في الجدول")

    view_resp = client.get(reverse("web:view_payroll_run", args=[draft.id]))
    if view_resp.status_code != 200:
        errors.append(f"عرض مسودة #{draft.id}: HTTP {view_resp.status_code}")
    else:
        vhtml = view_resp.content.decode("utf-8", errors="replace")
        if draft.run_kind != PayrollRun.RunKind.DETAILED:
            if "إعادة بناء" not in vhtml:
                errors.append("صفحة المسودة: زر إعادة البناء (تعديل) مفقود")
        if "hr-act--view" not in html and "hr-act--edit" not in html:
            pass  # checked on list page below

    list_html = resp.content.decode("utf-8", errors="replace") if resp.status_code == 200 else ""
    if list_html:
        if draft.status == PayrollRun.Status.DRAFT:
            errors.extend(_assert_buttons(list_html, draft=True, label="قائمة المسير (مسودة)"))

    del_url = reverse("web:delete_payroll_draft_run", args=[draft.id])
    bad_del = client.get(del_url)
    if bad_del.status_code not in (404, 405):
        errors.append(f"حذف المسودة: GET يجب أن يُرفض (حصل {bad_del.status_code})")

    if locked:
        locked_html = client.get(reverse("web:view_payroll_run", args=[locked.id])).content.decode(
            "utf-8", errors="replace"
        )
        if reverse("web:delete_payroll_draft_run", args=[locked.id]) in locked_html:
            errors.append("مسير مُغلق: رابط حذف ظاهر في الصفحة")

    partial = (BACKEND_ROOT / "templates/pages/payroll/_payroll_run_row_actions.html").read_text(
        encoding="utf-8"
    )
    if "table_act_add" in partial or "plus" in partial:
        errors.append("قالب الإجراءات: يحتوي زر إضافة")
    for required in ("table_act_view", "table_act_edit", "table_act_delete"):
        if required not in partial and "table_actions.html" not in partial:
            errors.append(f"قالب الإجراءات: {required} مفقود")

    print("=== فحص أزرار المسير (عرض · تعديل · حذف · بدون إضافة) ===")
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print("OK: عرض وفحص الأزرار — عرض/تعديل/حذف للمسودة، بدون إضافة في الصف")
    print(f"    مسودة #{draft.id} | قائمة HTTP {resp.status_code} | عرض HTTP {view_resp.status_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
