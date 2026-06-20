"""Cash shortage registration — finance screen."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.decorators import has_permission, permission_required
from apps.core.forms import CashShortageForm
from apps.core.services.pending_actions import create_pending_action
from apps.core.web_views._helpers import filter_employees_queryset_for_user
from apps.employees.models import Employee, EmployeeCashShortage


@login_required
@permission_required('cash_shortages.view')
def list_cash_shortages(request):
    """List recent cashier shortages + registration form."""
    qs = (
        EmployeeCashShortage.objects.select_related(
            'employee', 'branch', 'created_by', 'applied_to_payroll',
        )
        .order_by('-shortage_date', '-created_at')
    )
    branch_ids = None
    from apps.core.services.access_control import get_accessible_branch_ids
    branch_ids = get_accessible_branch_ids(request.user)
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    form = CashShortageForm(user=request.user)
    return render(request, 'pages/cash_shortages/list.html', {
        'page_obj': page_obj,
        'shortages': page_obj.object_list,
        'form': form,
        'employee_search_url': reverse('web:employee_picker_search'),
        'can_add': has_permission(request.user, 'cash_shortages.add'),
    })


@login_required
@permission_required('cash_shortages.add')
def register_cash_shortage(request):
    """POST: create pending cash shortage for branch accountant approval."""
    if request.method != 'POST':
        return redirect('web:list_cash_shortages')

    employee_id = (request.POST.get('employee_id') or '').strip()
    if not employee_id:
        messages.error(request, 'يجب اختيار موظف.')
        return redirect('web:list_cash_shortages')

    employee_qs = filter_employees_queryset_for_user(request.user, Employee.objects.all())
    employee = get_object_or_404(employee_qs.select_related('branch'), pk=employee_id)
    if employee.status == Employee.Status.TERMINATED:
        messages.error(request, 'لا يمكن تسجيل عجز لموظف منتهي الخدمة.')
        return redirect('web:list_cash_shortages')

    form = CashShortageForm(request.POST, user=request.user, employee=employee)
    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err[0])
        return redirect('web:list_cash_shortages')

    cd = form.cleaned_data
    branch = cd['branch']
    amount = cd['amount']
    if amount <= Decimal('0'):
        messages.error(request, 'مبلغ العجز يجب أن يكون أكبر من صفر.')
        return redirect('web:list_cash_shortages')

    create_pending_action(
        action_type='cash_shortage',
        employee=employee,
        payload={
            'shortage_date': cd['shortage_date'].isoformat(),
            'amount': str(amount),
            'branch_id': branch.id,
            'notes': cd.get('notes', ''),
        },
        requested_by=request.user,
    )
    messages.success(
        request,
        f'تم إرسال طلب عجز الكاشير ({amount} ر.س) إلى محاسب الفرع للاعتماد.',
    )
    return redirect('web:list_cash_shortages')
