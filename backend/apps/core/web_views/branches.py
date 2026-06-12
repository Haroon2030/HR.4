"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from apps.core.models import Branch, Company


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.decorators import permission_required
from apps.core.services.org_structure import (
    ORG_STRUCTURE_TAB_KEYS,
    get_org_tab_context,
    resolve_org_tab,
)
from apps.core.services.access_control import get_accessible_branch_ids


@login_required
@permission_required('branches.view')
def list_branches(request):
    """شاشة الهيكل التنظيمي — الهيكل والتبويبات فقط؛ المحتوى يُحمَّل عند الطلب."""
    active_tab = resolve_org_tab(request.GET.get('tab'))
    return render(request, 'pages/branches/list.html', {
        'active_tab': active_tab,
        'org_tab_url': reverse('web:org_structure_tab'),
    })


@login_required
@permission_required('branches.view')
def org_structure_tab(request):
    """جزء HTML لتبويب واحد (HTMX)."""
    tab = resolve_org_tab(request.GET.get('tab'))
    ctx = get_org_tab_context(request.user, tab)
    return render(request, 'pages/branches/_org_structure_tab.html', ctx)

@login_required
@permission_required('branches.view')
def view_branch(request, branch_id):
    """عرض تفاصيل فرع معين"""
    branch = get_object_or_404(Branch.objects.select_related('company', 'manager'), id=branch_id)
    accessible = get_accessible_branch_ids(request.user)
    if accessible is not None and branch.id not in accessible:
        messages.error(request, 'لا تملك صلاحية عرض هذا الفرع.')
        return redirect('web:list_branches')
    employees = (
        branch.employee_records.filter(is_deleted=False)
        .select_related('department', 'cost_center', 'profession')
        .order_by('name')
    )
    branch_users = branch.employees.select_related('user', 'role').all()
    cost_centers = branch.cost_centers.filter(is_deleted=False).order_by('code')
    departments = branch.departments.filter(is_deleted=False).select_related('cost_center').order_by('code')

    return render(request, 'pages/branches/detail.html', {
        'branch': branch,
        'employees': employees,
        'branch_users': branch_users,
        'cost_centers': cost_centers,
        'departments': departments,
    })

@login_required
@permission_required('branches.edit')
def edit_branch(request, branch_id):
    """تعديل فرع"""
    from apps.core.forms import BranchForm
    branch = get_object_or_404(Branch, id=branch_id)
    
    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f'تم تحديث الفرع "{branch.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#branches')
        for err in form.errors.values():
            messages.error(request, err[0])

    from django.contrib.auth import get_user_model
    User = get_user_model()
    return render(request, 'pages/branches/form.html', {
        'branch': branch,
        'users': User.objects.filter(is_active=True).order_by('username'),
    })

@login_required
@permission_required('branches.add')
def add_branch(request):
    """إضافة فرع جديد"""
    from apps.core.forms import BranchForm
    # الحصول على الشركة الافتراضية أو إنشاؤها
    company = Company.objects.first()
    if not company:
        company = Company.objects.create(
            name='الشركة الافتراضية',
            tax_number='',
            commercial_record=''
        )
    
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            branch = form.save(commit=False)
            branch.company = company
            branch.save()
            messages.success(request, f'تم إنشاء الفرع "{branch.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#branches')
        for err in form.errors.values():
            messages.error(request, err[0])

    from django.contrib.auth import get_user_model
    User = get_user_model()
    return render(request, 'pages/branches/form.html', {
        'users': User.objects.filter(is_active=True).order_by('username'),
    })


# =============================================================================
# Users Management
# =============================================================================

@login_required
@permission_required('branches.delete')
def delete_branch(request, branch_id):
    """حذف فرع (soft delete)"""
    branch = get_object_or_404(Branch, id=branch_id)
    if request.method == 'POST':
        name = branch.name
        branch.delete()
        messages.success(request, f'تم حذف الفرع "{name}" بنجاح')
    return redirect('web:list_branches')


