"""فحص عدد استعلامات صفحة مسير الرواتب — كشف التكرار."""
import os
import sys
from pathlib import Path

import django

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

User = get_user_model()

THRESHOLDS = {
    "list_payroll_ready": 45,
    "view_payroll_run": 25,
    "export_list_excel_head": 20,
}


def _login_admin(client: Client):
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.create_superuser("query_audit", "audit@test.local", "pass")
    client.force_login(user)
    return user


def _count_queries(fn):
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries), ctx.captured_queries


def main() -> int:
    client = Client()
    _login_admin(client)
    errors = []

    list_url = reverse("web:list_payroll_runs")
    n_list, queries = _count_queries(
        lambda: client.get(f"{list_url}?year=2026&month=6&salary_mode=transfer"),
    )
    print(f"GET قائمة المسير (جاهزة): {n_list} استعلام")
    if n_list > THRESHOLDS["list_payroll_ready"]:
        errors.append(
            f"قائمة المسير: {n_list} استعلام (الحد {THRESHOLDS['list_payroll_ready']})",
        )

    dup_sql = {}
    for q in queries:
        sql = " ".join(q["sql"].split())
        dup_sql[sql] = dup_sql.get(sql, 0) + 1
    repeated = [(sql, c) for sql, c in dup_sql.items() if c > 2]
    if repeated:
        print(f"تحذير: {len(repeated)} استعلام SQL مكرر أكثر من مرتين")
        for sql, c in sorted(repeated, key=lambda x: -x[1])[:5]:
            print(f"  ×{c}: {sql[:120]}...")

    from apps.payroll.models import PayrollRun

    run = PayrollRun.objects.order_by("-id").first()
    if run:
        n_view, _ = _count_queries(
            lambda: client.get(reverse("web:view_payroll_run", args=[run.id])),
        )
        print(f"GET عرض مسير #{run.id}: {n_view} استعلام")
        if n_view > THRESHOLDS["view_payroll_run"]:
            errors.append(
                f"عرض المسير: {n_view} استعلام (الحد {THRESHOLDS['view_payroll_run']})",
            )

    print("\n=== ملخص الفحص ===")
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1
    print("OK: عدد الاستعلامات ضمن الحدود المتوقعة")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
