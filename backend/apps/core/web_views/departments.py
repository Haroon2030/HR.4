"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from apps.core.models import Branch
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.decorators import permission_required

@login_required
@permission_required('departments.view')
def list_departments(request, branch_id=None):
    """عرض قائمة الأقسام"""
    branch = None
    if branch_id:
        branch = get_object_or_404(Branch, id=branch_id)
        departments = Department.objects.filter(
            branch=branch, is_deleted=False
        ).select_related('cost_center', 'manager').order_by('code')
    else:
        departments = Department.objects.filter(
            is_deleted=False
        ).select_related('branch', 'cost_center', 'manager').order_by('code')

    return render(request, 'pages/departments/list.html', {
        'branch': branch,
        'departments': departments
    })


@login_required
@permission_required('departments.view')
def view_department(request, department_id):
    """عرض تفاصيل قسم"""
    department = get_object_or_404(
        Department.objects.select_related('branch', 'cost_center', 'manager'),
        id=department_id
    )
    return render(request, 'pages/departments/detail.html', {'department': department})


@login_required
@permission_required('departments.add')
def add_department(request, branch_id=None):
    """إضافة قسم جديد"""
    from apps.core.forms import DepartmentForm
    branch = get_object_or_404(Branch, id=branch_id) if branch_id else None

    if request.method == 'POST':
        form = DepartmentForm(request.POST, branch=branch)
        if form.is_valid():
            department = form.save(commit=False)
            department.branch = branch
            department.is_active = True
            department.save()
            messages.success(request, f'تم إنشاء القسم "{department.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#departments')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/departments/form.html', {'branch': branch})


@login_required
@permission_required('departments.edit')
def edit_department(request, department_id):
    """تعديل قسم"""
    from apps.core.forms import DepartmentForm
    department = get_object_or_404(Department, id=department_id)

    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department, branch=department.branch)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'تم تحديث القسم "{department.name}" بنجاح')
            return redirect(reverse('web:list_branches') + '#departments')
        for err in form.errors.values():
            messages.error(request, err[0])

    return render(request, 'pages/departments/form.html', {
        'branch': department.branch,
        'department': department
    })


# =============================================================================
# Delete Views - حذف العناصر
# =============================================================================

@login_required
@permission_required('departments.delete')
def delete_department(request, department_id):
    """حذف قسم (soft delete)"""
    department = get_object_or_404(Department, id=department_id)
    if request.method == 'POST':
        name = department.name
        department.delete()
        messages.success(request, f'تم حذف القسم "{name}" بنجاح')
    return redirect('web:list_branches')


# =============================================================================
# Nationality, Profession, Sponsorship, Insurance, InsuranceClass - CRUD
# =============================================================================

# ───────────────────────────────────────────────────────────────────────────
# Nationality (الجنسية)
# ───────────────────────────────────────────────────────────────────────────

