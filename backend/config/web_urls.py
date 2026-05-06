"""
Web URLs - روابط واجهة الويب
نظام إدارة الموارد البشرية
"""
from django.urls import path, include
from django.views.generic import RedirectView
from apps.core import web_views

app_name = 'web'

# Authentication URLs
auth_patterns = [
    path('login/', web_views.login_view, name='login'),
    path('logout/', web_views.logout_view, name='logout'),
]

# Main URL patterns
urlpatterns = [
    # Dashboard
    path('', web_views.dashboard_view, name='dashboard'),
    
    # Employees (Tabs / Management)
    path('employees/', web_views.list_employees, name='list_employees'),
    path('employees/add/', web_views.add_employee, name='add_employee'),
    path('employees/create/', web_views.create_employee_full, name='create_employee_full'),
    path('employees/<int:employee_id>/', web_views.view_employee, name='view_employee'),
    path('employees/<int:employee_id>/edit/', web_views.edit_employee, name='edit_employee'),
    path('employees/<int:employee_id>/delete/', web_views.delete_employee, name='delete_employee'),
    path('employees/<int:employee_id>/statements/add/', web_views.add_employee_statement, name='add_employee_statement'),
    path('employees/statements/<int:statement_id>/delete/', web_views.delete_employee_statement, name='delete_employee_statement'),
    path('employees/<int:employee_id>/leaves/add/', web_views.add_employee_leave, name='add_employee_leave'),
    path('employees/<int:employee_id>/terminate/', web_views.terminate_employee, name='terminate_employee'),
    path('employees/<int:employee_id>/reactivate/', web_views.reactivate_employee, name='reactivate_employee'),
    path('employees/<int:employee_id>/salary-adjust/', web_views.adjust_employee_salary, name='adjust_employee_salary'),
    path('employees/<int:employee_id>/transfer/', web_views.transfer_employee, name='transfer_employee'),
    path('employees/<int:employee_id>/schedule/', web_views.set_work_schedule, name='set_work_schedule'),
    path('employees/<int:employee_id>/salary/export/', web_views.export_employee_salary_excel, name='export_employee_salary_excel'),

    # Employment Requests (دورة ثلاثية: مدير فرع → مدير الموارد → أخصائي)
    path('employment-requests/', web_views.list_employment_requests, name='list_employment_requests'),
    path('employment-requests/<int:request_id>/approve/', web_views.approve_employment_request, name='approve_employment_request'),
    path('employment-requests/<int:request_id>/gm-approve/', web_views.gm_approve_employment_request, name='gm_approve_employment_request'),
    path('employment-requests/<int:request_id>/officer-approve/', web_views.officer_approve_employment_request, name='officer_approve_employment_request'),
    path('employment-requests/<int:request_id>/edit/', web_views.edit_employment_request, name='edit_employment_request'),
    path('employment-requests/<int:request_id>/reject/', web_views.reject_employment_request, name='reject_employment_request'),

    # Pending Actions (دورة موافقات متعدّدة المراحل)
    path('pending-actions/', web_views.list_pending_actions, name='list_pending_actions'),
    path('pending-actions/<int:action_id>/', web_views.pending_action_detail, name='pending_action_detail'),
    path('pending-actions/<int:action_id>/branch-approve/', web_views.branch_approve_action, name='branch_approve_action'),
    path('pending-actions/<int:action_id>/gm-approve/', web_views.gm_approve_action, name='gm_approve_action'),
    path('pending-actions/<int:action_id>/officer-approve/', web_views.officer_approve_action, name='officer_approve_action'),
    path('pending-actions/<int:action_id>/return/', web_views.return_pending_action, name='return_pending_action'),
    path('pending-actions/<int:action_id>/resubmit/', web_views.resubmit_pending_action, name='resubmit_pending_action'),
    # توافق خلفي
    path('pending-actions/<int:action_id>/approve/', web_views.approve_pending_action, name='approve_pending_action'),
    path('pending-actions/<int:action_id>/reject/', web_views.reject_pending_action, name='reject_pending_action'),

    # Notifications (الإشعارات)
    path('notifications/', web_views.list_notifications, name='list_notifications'),
    path('notifications/dropdown/', web_views.notifications_dropdown, name='notifications_dropdown'),
    path('notifications/<int:notif_id>/read/', web_views.read_notification, name='read_notification'),
    path('notifications/<int:notif_id>/delete/', web_views.delete_notification, name='delete_notification'),
    path('notifications/read-all/', web_views.read_all_notifications, name='read_all_notifications'),
    path('notifications/delete-all/', web_views.delete_all_notifications, name='delete_all_notifications'),

    # Roles & Permissions
    path('roles/', web_views.list_roles, name='list_roles'),
    path('roles/add/', web_views.add_role, name='add_role'),
    path('roles/<int:role_id>/', web_views.view_role, name='view_role'),
    path('roles/<int:role_id>/edit/', web_views.edit_role, name='edit_role'),
    
    # Branches
    path('branches/', web_views.list_branches, name='list_branches'),
    path('branches/add/', web_views.add_branch, name='add_branch'),
    path('branches/<int:branch_id>/', web_views.view_branch, name='view_branch'),
    path('branches/<int:branch_id>/edit/', web_views.edit_branch, name='edit_branch'),
    path('branches/<int:branch_id>/delete/', web_views.delete_branch, name='delete_branch'),
    
    # Cost Centers (global + within branches)
    path('cost-centers/', web_views.list_cost_centers, name='list_all_cost_centers'),
    path('cost-centers/add/', web_views.add_cost_center, name='add_cost_center_global'),
    path('branches/<int:branch_id>/cost-centers/', web_views.list_cost_centers, name='list_cost_centers'),
    path('branches/<int:branch_id>/cost-centers/add/', web_views.add_cost_center, name='add_cost_center'),
    path('cost-centers/<int:cost_center_id>/edit/', web_views.edit_cost_center, name='edit_cost_center'),
    path('cost-centers/<int:cost_center_id>/delete/', web_views.delete_cost_center, name='delete_cost_center'),
    
    # Departments (global + within branches)
    path('departments/', web_views.list_departments, name='list_all_departments'),
    path('departments/add/', web_views.add_department, name='add_department_global'),
    path('branches/<int:branch_id>/departments/', web_views.list_departments, name='list_departments'),
    path('branches/<int:branch_id>/departments/add/', web_views.add_department, name='add_department'),
    path('departments/<int:department_id>/edit/', web_views.edit_department, name='edit_department'),
    path('departments/<int:department_id>/delete/', web_views.delete_department, name='delete_department'),
    
    # Setup Tables: Nationality, Profession, Sponsorship, Insurance, InsuranceClass
    path('setup/nationality/add/', web_views.add_nationality, name='add_nationality'),
    path('setup/nationality/<int:nationality_id>/edit/', web_views.edit_nationality, name='edit_nationality'),
    path('setup/nationality/<int:nationality_id>/delete/', web_views.delete_nationality, name='delete_nationality'),
    
    path('setup/profession/add/', web_views.add_profession, name='add_profession'),
    path('setup/profession/<int:profession_id>/edit/', web_views.edit_profession, name='edit_profession'),
    path('setup/profession/<int:profession_id>/delete/', web_views.delete_profession, name='delete_profession'),
    
    path('setup/sponsorship/add/', web_views.add_sponsorship, name='add_sponsorship'),
    path('setup/sponsorship/<int:sponsorship_id>/edit/', web_views.edit_sponsorship, name='edit_sponsorship'),
    path('setup/sponsorship/<int:sponsorship_id>/delete/', web_views.delete_sponsorship, name='delete_sponsorship'),
    
    path('setup/insurance/add/', web_views.add_insurance, name='add_insurance'),
    path('setup/insurance/<int:insurance_id>/edit/', web_views.edit_insurance, name='edit_insurance'),
    path('setup/insurance/<int:insurance_id>/delete/', web_views.delete_insurance, name='delete_insurance'),
    
    path('setup/insurance-class/add/', web_views.add_insurance_class, name='add_insurance_class'),
    path('setup/insurance-class/<int:insurance_class_id>/edit/', web_views.edit_insurance_class, name='edit_insurance_class'),
    path('setup/insurance-class/<int:insurance_class_id>/delete/', web_views.delete_insurance_class, name='delete_insurance_class'),
    
    # Users
    path('users/', web_views.list_users, name='list_users'),
    path('users/add/', web_views.add_user, name='add_user'),
    path('users/<int:user_id>/', web_views.view_user, name='view_user'),
    path('users/<int:user_id>/edit/', web_views.edit_user, name='edit_user'),
    path('users/<int:user_id>/delete/', web_views.delete_user, name='delete_user'),
    
    # Auth
    path('auth/', include((auth_patterns, 'auth'))),
    
    # Redirect /login/ to /auth/login/
    path('login/', RedirectView.as_view(pattern_name='web:auth:login', permanent=True)),
]
