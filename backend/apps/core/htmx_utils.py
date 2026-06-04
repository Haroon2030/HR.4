"""مساعدات HTMX — استجابة جزئية أو صفحة كاملة."""
from __future__ import annotations

from django.shortcuts import render
from django.template.response import TemplateResponse


def htmx_target(request) -> str:
    return (request.headers.get('HX-Target') or '').strip()


def wants_partial(request, panel_id: str) -> bool:
    target = htmx_target(request)
    return target == panel_id or (request.GET.get('partial') or '').strip() == panel_id


def render_page_or_panel(
    request,
    *,
    full_template: str,
    panel_template: str,
    panel_id: str,
    context: dict,
) -> TemplateResponse:
    """يُرجع القالب الكامل أو جزء اللوحة عند طلب HTMX."""
    if wants_partial(request, panel_id):
        return render(request, panel_template, context)
    return render(request, full_template, context)
