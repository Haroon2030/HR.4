"""لوحة وثائق تنتهي قريباً — نفس منطق خدمة document_expiry مع عزل الفروع."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import permission_required
from apps.employees.models import Employee
from apps.employees.services.document_expiry import collect_expiring_documents
from apps.core.web_views._helpers import filter_employees_queryset_for_user


@login_required
@permission_required('employees.view')
def document_expiry_dashboard(request):
    """جدول للموظفين الذين تنتهي وثائقهم (جواز / كرت صحي) خلال N يوماً."""
    try:
        horizon = int(request.GET.get('days') or '30')
    except (TypeError, ValueError):
        horizon = 30
    horizon = max(1, min(horizon, 365))

    ref = timezone.localdate()
    rows = collect_expiring_documents(reference_date=ref, horizon_days=horizon)
    if not rows:
        filtered = []
    else:
        ids = {r.employee_id for r in rows}
        allowed = filter_employees_queryset_for_user(
            request.user, Employee.objects.filter(pk__in=ids)
        ).values_list('pk', flat=True)
        allowed_set = set(allowed)
        filtered = [r for r in rows if r.employee_id in allowed_set]

    return render(
        request,
        'pages/employees/document_expiry.html',
        {
            'rows': filtered,
            'horizon': horizon,
            'reference_date': ref,
        },
    )
