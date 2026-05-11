"""
Django Template Views - واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.core.models import Branch
from apps.cost_centers.models import CostCenter
from apps.departments.models import Department


# =============================================================================
# Custom Decorators
# =============================================================================


from apps.core.web_views._helpers import (
    admin_required, _is_branch_manager, branch_manager_required,
    _user_accessible_branch_ids, employee_branch_access_required, _can_review_action,
)
from apps.core.decorators import permission_required


# ───────────────────────────────────────────────────────────────────────────
# Generic helpers - تبسيط CRUD المتكرر للـ lookups
# ───────────────────────────────────────────────────────────────────────────

def _redirect_with_tab(request):
    from django.urls import reverse
    tab = request.POST.get('tab') or request.GET.get('tab') or ''
    url = reverse('web:list_branches')
    if tab:
        url = f"{url}#{tab}"
    return redirect(url)


def _lookup_create(request, form_class, template, label, get_name):
    tab = request.GET.get('tab') or request.POST.get('tab') or ''
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'تم إضافة {label} "{get_name(obj)}" بنجاح')
            return _redirect_with_tab(request)
        for err in form.errors.values():
            messages.error(request, err[0])
    return render(request, template, {'tab': tab})


def _lookup_update(request, model, pk, form_class, template, label, get_name, ctx_key):
    obj = get_object_or_404(model, id=pk)
    tab = request.GET.get('tab') or request.POST.get('tab') or ''
    if request.method == 'POST':
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'تم تحديث {label} "{get_name(obj)}" بنجاح')
            return _redirect_with_tab(request)
        for err in form.errors.values():
            messages.error(request, err[0])
    return render(request, template, {ctx_key: obj, 'tab': tab})


def _lookup_delete(request, model, pk, label, get_name):
    obj = get_object_or_404(model, id=pk)
    if request.method == 'POST':
        name = get_name(obj)
        obj.delete()
        messages.success(request, f'تم حذف {label} "{name}" بنجاح')
    return _redirect_with_tab(request)


# ───────────────────────────────────────────────────────────────────────────
# Nationality
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_nationality(request):
    from apps.setup.forms import NationalityForm
    return _lookup_create(request, NationalityForm,
                          'pages/setup/nationality_form.html',
                          'الجنسية', lambda o: o.name)


@login_required
@permission_required('system_data.edit')
def edit_nationality(request, nationality_id):
    from apps.setup.models import Nationality
    from apps.setup.forms import NationalityForm
    return _lookup_update(request, Nationality, nationality_id, NationalityForm,
                          'pages/setup/nationality_form.html',
                          'الجنسية', lambda o: o.name, 'nationality')


@login_required
@permission_required('system_data.delete')
def delete_nationality(request, nationality_id):
    from apps.setup.models import Nationality
    return _lookup_delete(request, Nationality, nationality_id,
                          'الجنسية', lambda o: o.name)


# ───────────────────────────────────────────────────────────────────────────
# Profession
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_profession(request):
    from apps.setup.forms import ProfessionForm
    return _lookup_create(request, ProfessionForm,
                          'pages/setup/profession_form.html',
                          'المهنة', lambda o: o.name)


@login_required
@permission_required('system_data.edit')
def edit_profession(request, profession_id):
    from apps.setup.models import Profession
    from apps.setup.forms import ProfessionForm
    return _lookup_update(request, Profession, profession_id, ProfessionForm,
                          'pages/setup/profession_form.html',
                          'المهنة', lambda o: o.name, 'profession')


@login_required
@permission_required('system_data.delete')
def delete_profession(request, profession_id):
    from apps.setup.models import Profession
    return _lookup_delete(request, Profession, profession_id,
                          'المهنة', lambda o: o.name)


# ───────────────────────────────────────────────────────────────────────────
# Sponsorship
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_sponsorship(request):
    from apps.setup.forms import SponsorshipForm
    return _lookup_create(request, SponsorshipForm,
                          'pages/setup/sponsorship_form.html',
                          'الكفالة', lambda o: o.company_name)


@login_required
@permission_required('system_data.edit')
def edit_sponsorship(request, sponsorship_id):
    from apps.setup.models import Sponsorship
    from apps.setup.forms import SponsorshipForm
    return _lookup_update(request, Sponsorship, sponsorship_id, SponsorshipForm,
                          'pages/setup/sponsorship_form.html',
                          'الكفالة', lambda o: o.company_name, 'sponsorship')


@login_required
@permission_required('system_data.delete')
def delete_sponsorship(request, sponsorship_id):
    from apps.setup.models import Sponsorship
    return _lookup_delete(request, Sponsorship, sponsorship_id,
                          'الكفالة', lambda o: o.company_name)


# ───────────────────────────────────────────────────────────────────────────
# Insurance
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_insurance(request):
    from apps.setup.forms import InsuranceForm
    return _lookup_create(request, InsuranceForm,
                          'pages/setup/insurance_form.html',
                          'التأمين', lambda o: o.insurance_type)


@login_required
@permission_required('system_data.edit')
def edit_insurance(request, insurance_id):
    from apps.setup.models import Insurance
    from apps.setup.forms import InsuranceForm
    return _lookup_update(request, Insurance, insurance_id, InsuranceForm,
                          'pages/setup/insurance_form.html',
                          'التأمين', lambda o: o.insurance_type, 'insurance')


@login_required
@permission_required('system_data.delete')
def delete_insurance(request, insurance_id):
    from apps.setup.models import Insurance
    return _lookup_delete(request, Insurance, insurance_id,
                          'التأمين', lambda o: o.insurance_type)


# ───────────────────────────────────────────────────────────────────────────
# InsuranceClass
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_insurance_class(request):
    from apps.setup.forms import InsuranceClassForm
    return _lookup_create(request, InsuranceClassForm,
                          'pages/setup/insurance_class_form.html',
                          'فئة التأمين', lambda o: o.class_type)


@login_required
@permission_required('system_data.edit')
def edit_insurance_class(request, insurance_class_id):
    from apps.setup.models import InsuranceClass
    from apps.setup.forms import InsuranceClassForm
    return _lookup_update(request, InsuranceClass, insurance_class_id, InsuranceClassForm,
                          'pages/setup/insurance_class_form.html',
                          'فئة التأمين', lambda o: o.class_type, 'insurance_class')


@login_required
@permission_required('system_data.delete')
def delete_insurance_class(request, insurance_class_id):
    from apps.setup.models import InsuranceClass
    return _lookup_delete(request, InsuranceClass, insurance_class_id,
                          'فئة التأمين', lambda o: o.class_type)


# ───────────────────────────────────────────────────────────────────────────
# Building (السكن)
# ───────────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_building(request):
    from apps.setup.forms import BuildingForm
    return _lookup_create(request, BuildingForm,
                          'pages/setup/building_form.html',
                          'العمارة', lambda o: o.name)


@login_required
@permission_required('system_data.edit')
def edit_building(request, building_id):
    from apps.setup.models import Building
    from apps.setup.forms import BuildingForm
    return _lookup_update(request, Building, building_id, BuildingForm,
                          'pages/setup/building_form.html',
                          'العمارة', lambda o: o.name, 'building')


@login_required
@permission_required('system_data.delete')
def delete_building(request, building_id):
    from apps.setup.models import Building
    return _lookup_delete(request, Building, building_id,
                          'العمارة', lambda o: o.name)


# ──────────────────────────────────────────────────────────────────────
# Bank (البنوك)
# ──────────────────────────────────────────────────────────────────────

@login_required
@permission_required('system_data.add')
def add_bank(request):
    from apps.setup.forms import BankForm
    return _lookup_create(request, BankForm,
                          'pages/setup/bank_form.html',
                          'البنك', lambda o: o.name)


@login_required
@permission_required('system_data.edit')
def edit_bank(request, bank_id):
    from apps.setup.models import Bank
    from apps.setup.forms import BankForm
    return _lookup_update(request, Bank, bank_id, BankForm,
                          'pages/setup/bank_form.html',
                          'البنك', lambda o: o.name, 'bank')


@login_required
@permission_required('system_data.delete')
def delete_bank(request, bank_id):
    from apps.setup.models import Bank
    return _lookup_delete(request, Bank, bank_id,
                          'البنك', lambda o: o.name)



# =============================================================================
# Pending Actions Approval Workflow (Branch Manager)
# =============================================================================
