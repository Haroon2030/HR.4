"""مساعدات مشتركة لقوائم وعمليات CRUD المقيّدة بالفرع."""
from __future__ import annotations

from typing import Callable

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect

from apps.core.models import Branch
from apps.core.services.access_control import (
    filter_queryset_by_accessible_branch,
    user_may_access_branch_id,
)


def deny_branch_resource(
    request: HttpRequest,
    *,
    resource_label: str,
    action: str,
) -> HttpResponse:
    messages.error(request, f'لا تملك صلاحية {action} {resource_label} في هذا الفرع.')
    return redirect('web:list_branches')


def branch_for_scoped_view(
    request: HttpRequest,
    branch_id: int | None,
    *,
    resource_label: str,
    action: str,
) -> tuple[Branch | None, HttpResponse | None]:
    """جلب فرع للعرض/الإضافة مع فحص الصلاحية."""
    if not branch_id:
        return None, None
    branch = get_object_or_404(Branch, id=branch_id)
    if not user_may_access_branch_id(request.user, branch.id):
        return None, deny_branch_resource(request, resource_label=resource_label, action=action)
    return branch, None


def list_branch_scoped_queryset(
    request: HttpRequest,
    branch_id: int | None,
    *,
    resource_label: str,
    all_queryset,
    branch_filter: Callable,
):
    """
    قائمة عناصر فرع واحد أو كل الفروع المتاحة.
    branch_filter(branch) → queryset مرتب.
    """
    branch, denied = branch_for_scoped_view(
        request,
        branch_id,
        resource_label=resource_label,
        action='عرض',
    )
    if denied:
        return None, None, denied
    if branch:
        return branch, branch_filter(branch), None
    qs = filter_queryset_by_accessible_branch(request.user, all_queryset)
    return None, qs, None


def require_branch_access(
    request: HttpRequest,
    branch_id: int,
    *,
    resource_label: str,
    action: str,
) -> HttpResponse | None:
    if not user_may_access_branch_id(request.user, branch_id):
        return deny_branch_resource(request, resource_label=resource_label, action=action)
    return None
