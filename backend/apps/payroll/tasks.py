"""مهام Celery لبناء مسير الرواتب."""
from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def build_payroll_runs_task(self, user_id: int, filters: dict) -> dict:
    """بناء مسير رواتب قياسي في الخلفية."""
    from apps.payroll.views import _build_payroll_runs, _payroll_branch_scope

    user = get_user_model().objects.filter(pk=user_id).first()
    if not user:
        return {'ok': False, 'error': 'user_not_found'}

    scope = _payroll_branch_scope(user)
    runs_built, errors = _build_payroll_runs(user, filters, scope)
    if errors:
        logger.warning('payroll build task errors user=%s: %s', user_id, errors)
        return {'ok': False, 'errors': errors, 'runs_built': len(runs_built)}

    total_emp = sum(r.employees_count for r in runs_built)
    return {'ok': True, 'runs_built': len(runs_built), 'employees': total_emp}


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def build_detailed_payroll_runs_task(self, user_id: int, filters: dict) -> dict:
    """بناء مسير تفصيلي في الخلفية."""
    from apps.payroll.views import _build_detailed_payroll_runs, _payroll_branch_scope

    user = get_user_model().objects.filter(pk=user_id).first()
    if not user:
        return {'ok': False, 'error': 'user_not_found'}

    scope = _payroll_branch_scope(user)
    runs_built, errors, _had_draft = _build_detailed_payroll_runs(user, filters, scope)
    if errors:
        logger.warning('detailed payroll build task errors user=%s: %s', user_id, errors)
        return {'ok': False, 'errors': errors, 'runs_built': len(runs_built)}

    total_emp = sum(r.employees_count for r in runs_built)
    return {'ok': True, 'runs_built': len(runs_built), 'employees': total_emp}
