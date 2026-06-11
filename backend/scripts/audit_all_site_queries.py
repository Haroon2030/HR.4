"""
فحص عميق لاستعلامات الموقع بالكامل — كل مسار GET قابل للوصول.
يُخرج تقريراً مرتباً حسب عدد الاستعلامات مع كشف SQL المكرر.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import django

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import URLPattern, URLResolver, get_resolver, reverse

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

User = get_user_model()

# حدود التصنيف
WARN_QUERIES = 30
CRIT_QUERIES = 60
DUP_WARN = 3  # نفس SQL يتكرر أكثر من هذا العدد

SKIP_NAME_PARTS = {
    "delete", "logout", "reject", "approve", "lock", "unlock", "rebuild",
    "pull", "sync", "ingest", "save", "read", "agent-key", "export",
    "password", "token", "schema", "redoc", "admin", "media", "favicon",
}
SKIP_SUFFIX_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class RouteResult:
    name: str
    path: str
    status: int
    queries: int = 0
    duplicates: list[tuple[int, str]] = field(default_factory=list)
    skipped: str = ""
    error: str = ""
    time_ms: int = 0


def _pk(model) -> int | None:
    if model is None:
        return None
    return model.objects.order_by("pk").values_list("pk", flat=True).first()


def _build_sample_context() -> dict[str, Any]:
    from django.apps import apps

    from apps.attendance.models import BiometricDevice
    from apps.core.models import Branch, Company, Notification, PendingAction, Role
    from apps.core.web_views.hr_forms import HR_FORMS
    from apps.core.web_views.reports import REPORTS
    from apps.cost_centers.models import CostCenter
    from apps.departments.models import Department
    from apps.employees.models import Employee, EmployeeStatement, EmploymentRequest
    from apps.payroll.models import PayrollRun
    from apps.setup.models import (
        Administration, Bank, Building, Insurance, InsuranceClass,
        Nationality, Profession, Sponsorship,
    )

    ctx: dict[str, Any] = {}
    optional_models = {
        "backup_id": "core.DatabaseBackupLog",
        "device_id": BiometricDevice,
        "request_id": EmploymentRequest,
        "action_id": PendingAction,
        "notif_id": Notification,
    }
    mappings = {
        "employee_id": Employee,
        "branch_id": Branch,
        "user_id": User,
        "run_id": PayrollRun,
        "company_id": Company,
        "nationality_id": Nationality,
        "profession_id": Profession,
        "sponsorship_id": Sponsorship,
        "insurance_id": Insurance,
        "insurance_class_id": InsuranceClass,
        "building_id": Building,
        "bank_id": Bank,
        "administration_id": Administration,
        "cost_center_id": CostCenter,
        "department_id": Department,
        "role_id": Role,
        "statement_id": EmployeeStatement,
    }
    for key, model in mappings.items():
        pk = _pk(model)
        if pk:
            ctx[key] = pk
    for key, model in optional_models.items():
        if isinstance(model, str):
            try:
                model = apps.get_model(model)
            except LookupError:
                continue
        pk = _pk(model)
        if pk:
            ctx[key] = pk

    if HR_FORMS:
        ctx["form_type"] = HR_FORMS[0]["key"]
    if REPORTS:
        ctx["report_type"] = REPORTS[0]["key"]
    ctx["new_report"] = REPORTS[0]["key"] if REPORTS else "headcount_summary"
    return ctx


def _collect_named_routes(urlpatterns=None, namespace: str = "") -> list[tuple[str, URLPattern]]:
    if urlpatterns is None:
        urlpatterns = get_resolver().url_patterns
    found: list[tuple[str, URLPattern]] = []
    for pattern in urlpatterns:
        if isinstance(pattern, URLResolver):
            ns = pattern.namespace or ""
            full_ns = f"{namespace}:{ns}" if namespace and ns else (ns or namespace)
            found.extend(_collect_named_routes(pattern.url_patterns, full_ns))
        elif isinstance(pattern, URLPattern) and pattern.name:
            full_name = f"{namespace}:{pattern.name}" if namespace else pattern.name
            found.append((full_name, pattern))
    return found


def _kwargs_for_pattern(pattern: URLPattern, ctx: dict[str, Any]) -> dict[str, Any] | None:
    converters = getattr(pattern.pattern, "converters", {}) or {}
    if not converters:
        return {}
    kwargs = {}
    for key in converters:
        if key not in ctx:
            return None
        kwargs[key] = ctx[key]
    return kwargs


def _should_skip(name: str, pattern: URLPattern) -> str | None:
    low = name.lower()
    for part in SKIP_NAME_PARTS:
        if part in low:
            return f"skip:{part}"
    view = pattern.callback
    if hasattr(view, "cls"):
        view = view.cls
    methods = getattr(view, "http_method_names", None)
    if methods and "get" not in [m.lower() for m in methods]:
        return "non-get-view"
    return None


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())[:200]


def _probe_route(client: Client, name: str, pattern: URLPattern, ctx: dict) -> RouteResult:
    skip = _should_skip(name, pattern)
    if skip:
        return RouteResult(name=name, path="", skipped=skip, status=0)

    kwargs = _kwargs_for_pattern(pattern, ctx)
    if kwargs is None:
        return RouteResult(name=name, path="", skipped="missing-sample-id", status=0)

    try:
        path = reverse(name, kwargs=kwargs if kwargs else None)
    except Exception as exc:
        return RouteResult(name=name, path="", skipped="reverse-failed", error=str(exc)[:120], status=0)

    import time
    t0 = time.perf_counter()
    with CaptureQueriesContext(connection) as ctx_q:
        try:
            resp = client.get(path, follow=False)
            status = resp.status_code
        except Exception as exc:
            return RouteResult(
                name=name, path=path, status=0, error=str(exc)[:120],
                time_ms=int((time.perf_counter() - t0) * 1000),
            )
    elapsed = int((time.perf_counter() - t0) * 1000)
    queries = ctx_q.captured_queries

    sql_counts = Counter(_normalize_sql(q["sql"]) for q in queries)
    dups = [(c, sql) for sql, c in sql_counts.items() if c >= DUP_WARN]
    dups.sort(reverse=True)

    return RouteResult(
        name=name,
        path=path,
        status=status,
        queries=len(queries),
        duplicates=dups[:5],
        time_ms=elapsed,
    )


def _scan_static_n_plus_one() -> list[str]:
    """مسح سريع لأنماط N+1 المحتملة في views."""
    hits = []
    apps_dir = BACKEND_ROOT / "apps"
    loop_re = re.compile(
        r"for\s+\w+\s+in\s+.+:\s*\n\s+.*\.objects\.(filter|get|all)\(",
        re.MULTILINE,
    )
    for py in apps_dir.rglob("*.py"):
        if "migrations" in str(py) or "tests" in str(py):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in loop_re.finditer(text):
            line = text[:m.start()].count("\n") + 1
            hits.append(f"{py.relative_to(BACKEND_ROOT)}:{line}")
    return hits[:40]


def main() -> int:
    client = Client()
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.create_superuser("site_audit", "audit@site.local", "pass")
    client.force_login(user)

    sample_ctx = _build_sample_context()
    routes = _collect_named_routes()
    seen_names = set()
    results: list[RouteResult] = []

    # مسارات إضافية بمعاملات query شائعة
    extra_gets = [
        ("/payroll/?year=2026&month=6&salary_mode=transfer", "payroll:list:transfer"),
        ("/payroll/?year=2026&month=6&salary_mode=transfer&payroll_view=detailed", "payroll:list:detailed"),
        ("/employees/picker/search/?q=a", "employees:picker:search"),
        ("/hr-forms/employees/search/?q=a", "hr-forms:search"),
        ("/notifications/dropdown/", "notifications:dropdown"),
        ("/api/v1/me/", "api:me"),
        ("/api/v1/companies/", "api:companies"),
        ("/api/v1/branches/", "api:branches"),
        ("/api/v1/users/", "api:users"),
        ("/api/v1/roles/", "api:roles"),
        ("/attendance/report/?year=2026&month=6", "attendance:report"),
    ]

    for name, pattern in sorted(routes, key=lambda x: x[0]):
        if name in seen_names:
            continue
        seen_names.add(name)
        results.append(_probe_route(client, name, pattern, sample_ctx))

    for path, label in extra_gets:
        import time
        t0 = time.perf_counter()
        with CaptureQueriesContext(connection) as ctx_q:
            resp = client.get(path, follow=False)
        sql_counts = Counter(_normalize_sql(q["sql"]) for q in ctx_q.captured_queries)
        dups = [(c, sql) for sql, c in sql_counts.items() if c >= DUP_WARN]
        dups.sort(reverse=True)
        results.append(RouteResult(
            name=label, path=path, status=resp.status_code,
            queries=len(ctx_q.captured_queries), duplicates=dups[:5],
            time_ms=int((time.perf_counter() - t0) * 1000),
        ))

    tested = [r for r in results if not r.skipped and r.status in (200, 301, 302)]
    failed = [r for r in results if r.error or (not r.skipped and r.status >= 400)]
    skipped = [r for r in results if r.skipped]
    critical = [r for r in tested if r.queries >= CRIT_QUERIES]
    warning = [r for r in tested if WARN_QUERIES <= r.queries < CRIT_QUERIES]
    dup_heavy = [r for r in tested if r.duplicates]

    tested.sort(key=lambda r: -r.queries)
    static_hits = _scan_static_n_plus_one()

    report_dir = BACKEND_ROOT / "scripts" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "site_query_audit.json"

    payload = {
        "summary": {
            "total_routes": len(results),
            "tested_ok": len(tested),
            "skipped": len(skipped),
            "failed": len(failed),
            "warning": len(warning),
            "critical": len(critical),
            "dup_heavy": len(dup_heavy),
        },
        "top_queries": [
            {"name": r.name, "path": r.path, "queries": r.queries, "status": r.status, "ms": r.time_ms}
            for r in tested[:25]
        ],
        "critical": [
            {"name": r.name, "path": r.path, "queries": r.queries, "dups": r.duplicates}
            for r in critical
        ],
        "warning": [
            {"name": r.name, "path": r.path, "queries": r.queries, "dups": r.duplicates}
            for r in warning
        ],
        "dup_heavy": [
            {"name": r.name, "path": r.path, "queries": r.queries, "dups": r.duplicates}
            for r in dup_heavy[:20]
        ],
        "failed": [
            {"name": r.name, "path": r.path, "status": r.status, "error": r.error, "skip": r.skipped}
            for r in failed[:30]
        ],
        "static_n_plus_one": static_hits,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print("فحص استعلامات الموقع — تقرير شامل")
    print("=" * 60)
    print(f"إجمالي المسارات المكتشفة: {len(results)}")
    print(f"تم فحصها بنجاح (200/redirect): {len(tested)}")
    print(f"تخطّى (POST/حذف/تصدير): {len(skipped)}")
    print(f"فشل أو 4xx: {len(failed)}")
    print(f"تحذير ({WARN_QUERIES}+ استعلام): {len(warning)}")
    print(f"حرج ({CRIT_QUERIES}+ استعلام): {len(critical)}")
    print(f"تكرار SQL ({DUP_WARN}+): {len(dup_heavy)}")
    print()
    print("أعلى 15 صفحة استعلاماً:")
    for r in tested[:15]:
        flag = "!!!" if r.queries >= CRIT_QUERIES else ("!" if r.queries >= WARN_QUERIES else " ")
        dup = f" | تكرار×{r.duplicates[0][0]}" if r.duplicates else ""
        print(f"  {flag} {r.queries:3d}q  {r.status}  {r.name}{dup}")
        print(f"       {r.path}")
    print()
    print(f"التقرير الكامل: {report_path}")
    if static_hits:
        print(f"أنماط N+1 محتملة في الكود: {len(static_hits)} موقع")

    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
