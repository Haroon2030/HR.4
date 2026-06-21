"""
روابط واجهة الويب — Web URLs
============================
هذا الملف يحتوي على جميع روابط واجهة المستخدم (Django Templates).

الأقسام الرئيسية:
  1. المصادقة (تسجيل الدخول/الخروج)
  2. إدارة الموظفين (عرض/إضافة/تعديل/حذف + العمليات السريعة)
  3. طلبات التوظيف (دورة موافقات ثلاثية)
  4. الطلبات المعلّقة (دورة موافقات رباعية المراحل)
  5. الإشعارات
  6. الأدوار والصلاحيات
  7. الفروع ومراكز التكلفة والأقسام
  8. جداول الإعداد (جنسيات، مهن، كفالات، تأمين، بنوك)
  9. المستخدمون
  10. النماذج الرسمية والتقارير
  11. مسير الرواتب الشهري

كل رابط مرتبط بـ view function محمي بصلاحيات عبر decorators.
"""
from django.urls import path, include
from django.views.generic import RedirectView
from apps.core import web_views
from apps.payroll import views as payroll_views

# مساحة الأسماء — تُستخدم في القوالب: {% url 'web:list_employees' %}
app_name = 'web'

# ─────────────────────────────────────────────────────────────────────────────
# 1. المصادقة (تسجيل الدخول / الخروج)
# ─────────────────────────────────────────────────────────────────────────────
auth_patterns = [
    path('login/', web_views.login_view, name='login'),       # صفحة تسجيل الدخول
    path('logout/', web_views.logout_view, name='logout'),     # تسجيل الخروج
    path('password/change/', web_views.password_change_view, name='password_change'),
]

# ─────────────────────────────────────────────────────────────────────────────
# الروابط الرئيسية
# ─────────────────────────────────────────────────────────────────────────────
urlpatterns = [

    # ── لوحة التحكم الرئيسية ────────────────────────────────────
    path('', web_views.dashboard_view, name='dashboard'),
    path(
        'backups/<int:backup_id>/download/',
        web_views.download_database_backup,
        name='download_database_backup',
    ),
    path('audit/history/', web_views.audit_history_dashboard, name='audit_history'),
    
    # ══════════════════════════════════════════════════════════════
    # 2. إدارة الموظفين — CRUD + العمليات السريعة (Quick Actions)
    # كل عملية سريعة تنشئ PendingAction ينتظر دورة الموافقات
    # ══════════════════════════════════════════════════════════════
    path('employees/', web_views.list_employees, name='list_employees'),                                     # قائمة الموظفين
    path('employees/picker/search/', web_views.employee_picker_search, name='employee_picker_search'),       # بحث اختيار موظف
    path('employees/add/', web_views.add_employee, name='add_employee'),                                     # إضافة موظف (نموذج مختصر)
    path('employees/create/', web_views.create_employee_full, name='create_employee_full'),                   # إنشاء موظف (نموذج كامل)
    path('employees/<int:employee_id>/', web_views.view_employee, name='view_employee'),                      # عرض ملف الموظف
    path('employees/<int:employee_id>/biometric-settings/', web_views.save_employee_biometric_settings, name='save_employee_biometric_settings'),
    path('employees/<int:employee_id>/edit/', web_views.edit_employee, name='edit_employee'),                  # تعديل بيانات الموظف
    path('employees/<int:employee_id>/delete/', web_views.delete_employee, name='delete_employee'),            # حذف الموظف (حذف ناعم)
    path('employees/<int:employee_id>/statements/add/', web_views.add_employee_statement, name='add_employee_statement'),  # إضافة إفادة
    path('employees/statements/<int:statement_id>/delete/', web_views.delete_employee_statement, name='delete_employee_statement'),  # حذف إفادة
    path('employees/<int:employee_id>/leaves/add/', web_views.add_employee_leave, name='add_employee_leave'),                  # تسجيل إجازة
    path('employees/<int:employee_id>/terminate/', web_views.terminate_employee, name='terminate_employee'),                    # طلب تصفية
    path('employees/<int:employee_id>/reactivate/', web_views.reactivate_employee, name='reactivate_employee'),                # إعادة تفعيل
    path('employees/<int:employee_id>/salary-adjust/', web_views.adjust_employee_salary, name='adjust_employee_salary'),        # تعديل راتب
    path('employees/<int:employee_id>/transfer/', web_views.transfer_employee, name='transfer_employee'),                       # نقل موظف
    path('employees/<int:employee_id>/schedule/', web_views.set_work_schedule, name='set_work_schedule'),                       # جدول الدوام
    path('employees/<int:employee_id>/salary/export/', web_views.export_employee_salary_excel, name='export_employee_salary_excel'),  # تصدير Excel
    path('employees/<int:employee_id>/custody/receive/', web_views.receive_employee_custody, name='receive_employee_custody'),  # استلام عهدة
    path('employees/<int:employee_id>/custody/clear/', web_views.clear_employee_custody, name='clear_employee_custody'),        # تصفية عهدة
    path('employees/<int:employee_id>/loan/add/', web_views.add_employee_loan, name='add_employee_loan'),                      # سلفة
    path('employees/<int:employee_id>/absence/add/', web_views.add_employee_absence, name='add_employee_absence'),              # تسجيل غياب
    path('employees/<int:employee_id>/cash-shortage/add/', web_views.add_employee_cash_shortage, name='add_employee_cash_shortage'),
    path('employees/<int:employee_id>/end-of-service/', web_views.end_of_service_employee, name='end_of_service_employee'), # تصفية نهاية خدمة أو استقالة
    path('employees/<int:employee_id>/ledger-init/', web_views.run_ledger_init, name='run_ledger_init'),        # تهيئة أرصدة الموظف

    # ══════════════════════════════════════════════════════════════
    # 3. طلبات التوظيف — دورة: أخصائي → مدير فرع → مدير الموارد → أخصائي ينفّذ
    # ══════════════════════════════════════════════════════════════
    path('employment-requests/', web_views.list_employment_requests, name='list_employment_requests'),                                    # قائمة الطلبات
    path('employment-requests/<int:request_id>/approve/', web_views.approve_employment_request, name='approve_employment_request'),        # موافقة مدير الفرع
    path('employment-requests/<int:request_id>/gm-approve/', web_views.gm_approve_employment_request, name='gm_approve_employment_request'),  # موافقة المدير العام
    path('employment-requests/<int:request_id>/officer-approve/', web_views.officer_approve_employment_request, name='officer_approve_employment_request'),  # تنفيذ الأخصائي
    path('employment-requests/<int:request_id>/edit/', web_views.edit_employment_request, name='edit_employment_request'),                  # تعديل الطلب
    path('employment-requests/<int:request_id>/reject/', web_views.reject_employment_request, name='reject_employment_request'),            # رفض الطلب
    path('employment-requests/<int:request_id>/delete/', web_views.delete_employment_request, name='delete_employment_request'),            # حذف الطلب

    # ══════════════════════════════════════════════════════════════
    # 4. الطلبات المعلّقة — دورة موافقات 4 مراحل
    #    أخصائي → مدير فرع → مدير عام → موظف موارد (ينفّذ)
    # ══════════════════════════════════════════════════════════════
    path('pending-actions/', web_views.list_pending_actions, name='list_pending_actions'),                            # قائمة + صندوق الوارد
    path('pending-actions/<int:action_id>/', web_views.pending_action_detail, name='pending_action_detail'),          # تفاصيل الطلب
    path('pending-actions/<int:action_id>/branch-approve/', web_views.branch_approve_action, name='branch_approve_action'),  # موافقة مدير الفرع
    path('pending-actions/<int:action_id>/gm-approve/', web_views.gm_approve_action, name='gm_approve_action'),              # موافقة المدير العام
    path('pending-actions/<int:action_id>/officer-approve/', web_views.officer_approve_action, name='officer_approve_action'),  # تنفيذ موظف الموارد
    path('pending-actions/<int:action_id>/return/', web_views.return_pending_action, name='return_pending_action'),            # إرجاع للتعديل
    path('pending-actions/<int:action_id>/resubmit/', web_views.resubmit_pending_action, name='resubmit_pending_action'),      # إعادة إرسال

    # روابط التوافق الخلفي (الأسماء القديمة — تُعيد التوجيه)
    path('pending-actions/<int:action_id>/approve/', web_views.approve_pending_action, name='approve_pending_action'),
    path('pending-actions/<int:action_id>/reject/', web_views.reject_pending_action, name='reject_pending_action'),
    path('pending-actions/<int:action_id>/delete/', web_views.delete_pending_action, name='delete_pending_action'),

    # ══════════════════════════════════════════════════════════════
    # 5. الإشعارات
    # ══════════════════════════════════════════════════════════════
    path('notifications/', web_views.list_notifications, name='list_notifications'),                     # كل الإشعارات
    path('notifications/dropdown/', web_views.notifications_dropdown, name='notifications_dropdown'),     # القائمة المنسدلة (AJAX)
    path('notifications/<int:notif_id>/read/', web_views.read_notification, name='read_notification'),    # تعليم كمقروء
    path('notifications/<int:notif_id>/delete/', web_views.delete_notification, name='delete_notification'),  # حذف
    path('notifications/read-all/', web_views.read_all_notifications, name='read_all_notifications'),     # تعليم الكل مقروء
    path('notifications/delete-all/', web_views.delete_all_notifications, name='delete_all_notifications'),  # حذف الكل

    # ══════════════════════════════════════════════════════════════
    # 6. الأدوار والصلاحيات
    # ══════════════════════════════════════════════════════════════
    path('roles/', web_views.list_roles, name='list_roles'),
    path('roles/add/', web_views.add_role, name='add_role'),
    path('roles/<int:role_id>/', web_views.view_role, name='view_role'),
    path('roles/<int:role_id>/edit/', web_views.edit_role, name='edit_role'),
    path('roles/<int:role_id>/delete/', web_views.delete_role, name='delete_role'),
    path('roles/<int:role_id>/permissions/', web_views.manage_role_permissions, name='manage_role_permissions'),  # إدارة صلاحيات الدور
    
    # ══════════════════════════════════════════════════════════════
    # 7. الفروع
    # ══════════════════════════════════════════════════════════════
    path('branches/', web_views.list_branches, name='list_branches'),
    path('branches/tab/', web_views.org_structure_tab, name='org_structure_tab'),
    path('branches/add/', web_views.add_branch, name='add_branch'),
    path('branches/<int:branch_id>/', web_views.view_branch, name='view_branch'),
    path('branches/<int:branch_id>/edit/', web_views.edit_branch, name='edit_branch'),
    path('branches/<int:branch_id>/delete/', web_views.delete_branch, name='delete_branch'),
    
    # مراكز التكلفة (عام + داخل الفروع)
    path('cost-centers/', web_views.list_cost_centers, name='list_all_cost_centers'),
    path('cost-centers/add/', web_views.add_cost_center, name='add_cost_center_global'),
    path('branches/<int:branch_id>/cost-centers/', web_views.list_cost_centers, name='list_cost_centers'),
    path('branches/<int:branch_id>/cost-centers/add/', web_views.add_cost_center, name='add_cost_center'),
    path('cost-centers/<int:cost_center_id>/', web_views.view_cost_center, name='view_cost_center'),
    path('cost-centers/<int:cost_center_id>/edit/', web_views.edit_cost_center, name='edit_cost_center'),
    path('cost-centers/<int:cost_center_id>/delete/', web_views.delete_cost_center, name='delete_cost_center'),
    
    # الأقسام (عام + داخل الفروع)
    path('departments/', web_views.list_departments, name='list_all_departments'),
    path('departments/add/', web_views.add_department, name='add_department_global'),
    path('branches/<int:branch_id>/departments/', web_views.list_departments, name='list_departments'),
    path('branches/<int:branch_id>/departments/add/', web_views.add_department, name='add_department'),
    path('departments/<int:department_id>/', web_views.view_department, name='view_department'),
    path('departments/<int:department_id>/edit/', web_views.edit_department, name='edit_department'),
    path('departments/<int:department_id>/delete/', web_views.delete_department, name='delete_department'),
    
    # ══════════════════════════════════════════════════════════════
    # 8. جداول الإعداد — البيانات المرجعية للنظام
    # ══════════════════════════════════════════════════════════════

    # الجنسيات
    path('setup/nationality/add/', web_views.add_nationality, name='add_nationality'),
    path('setup/nationality/<int:nationality_id>/edit/', web_views.edit_nationality, name='edit_nationality'),
    path('setup/nationality/<int:nationality_id>/delete/', web_views.delete_nationality, name='delete_nationality'),
    
    # المهن
    path('setup/profession/add/', web_views.add_profession, name='add_profession'),
    path('setup/profession/<int:profession_id>/edit/', web_views.edit_profession, name='edit_profession'),
    path('setup/profession/<int:profession_id>/delete/', web_views.delete_profession, name='delete_profession'),
    
    # الكفالات
    path('setup/sponsorship/add/', web_views.add_sponsorship, name='add_sponsorship'),
    path('setup/sponsorship/<int:sponsorship_id>/edit/', web_views.edit_sponsorship, name='edit_sponsorship'),
    path('setup/sponsorship/<int:sponsorship_id>/delete/', web_views.delete_sponsorship, name='delete_sponsorship'),
    
    # شركات التأمين
    path('setup/insurance/add/', web_views.add_insurance, name='add_insurance'),
    path('setup/insurance/<int:insurance_id>/edit/', web_views.edit_insurance, name='edit_insurance'),
    path('setup/insurance/<int:insurance_id>/delete/', web_views.delete_insurance, name='delete_insurance'),
    
    # فئات التأمين
    path('setup/insurance-class/add/', web_views.add_insurance_class, name='add_insurance_class'),
    path('setup/insurance-class/<int:insurance_class_id>/edit/', web_views.edit_insurance_class, name='edit_insurance_class'),
    path('setup/insurance-class/<int:insurance_class_id>/delete/', web_views.delete_insurance_class, name='delete_insurance_class'),

    # المباني / السكن
    path('setup/building/add/', web_views.add_building, name='add_building'),
    path('setup/building/<int:building_id>/edit/', web_views.edit_building, name='edit_building'),
    path('setup/building/<int:building_id>/delete/', web_views.delete_building, name='delete_building'),

    # البنوك
    path('setup/bank/add/', web_views.add_bank, name='add_bank'),
    path('setup/bank/<int:bank_id>/edit/', web_views.edit_bank, name='edit_bank'),
    path('setup/bank/<int:bank_id>/delete/', web_views.delete_bank, name='delete_bank'),

    # الإدارات
    path('setup/administration/add/', web_views.add_administration, name='add_administration'),
    path('setup/administration/<int:administration_id>/edit/', web_views.edit_administration, name='edit_administration'),
    path('setup/administration/<int:administration_id>/delete/', web_views.delete_administration, name='delete_administration'),

    # ── إعدادات تقرير العمليات المجدول ──
    path('setup/operations-report/', web_views.operations_report_settings, name='operations_report_settings'),
    
    # ══════════════════════════════════════════════════════════════
    # 9. إدارة المستخدمين
    # ══════════════════════════════════════════════════════════════
    path('users/', web_views.list_users, name='list_users'),
    path('users/add/', web_views.add_user, name='add_user'),
    path('users/<int:user_id>/', web_views.view_user, name='view_user'),
    path('users/<int:user_id>/edit/', web_views.edit_user, name='edit_user'),
    path('users/<int:user_id>/permissions/', web_views.manage_user_permissions, name='manage_user_permissions'),  # صلاحيات خاصة بالمستخدم
    path('users/<int:user_id>/delete/', web_views.delete_user, name='delete_user'),

    # ══════════════════════════════════════════════════════════════
    # 10. النماذج الرسمية والتقارير
    # ══════════════════════════════════════════════════════════════
    path('hr-forms/', web_views.hr_forms_index, name='hr_forms_index'),                                # فهرس النماذج
    path('hr-forms/employees/search/', web_views.hr_forms_employee_search, name='hr_forms_employee_search'),
    path('hr-forms/<str:form_type>/<int:employee_id>/', web_views.hr_form_print, name='hr_form_print'), # طباعة نموذج

    path('reports/', web_views.reports_index, name='reports_index'),                    # فهرس التقارير
    path('reports/multi/', web_views.multi_report_detail, name='multi_report_detail'),  # عرض تقارير متعددة مجمعة
    path('reports/<str:report_type>/export/', web_views.report_export_excel, name='report_export_excel'),
    path('reports/<str:report_type>/', web_views.report_detail, name='report_detail'),  # عرض تقرير محدد

    # ══════════════════════════════════════════════════════════════
    # 12. أجهزة البصمة والحضور
    # ══════════════════════════════════════════════════════════════
    path('attendance/devices/', web_views.biometric_devices_dashboard, name='biometric_devices'),
    path('attendance/devices/save/', web_views.biometric_device_save, name='biometric_device_save'),
    path('attendance/devices/<int:device_id>/delete/', web_views.biometric_device_delete, name='biometric_device_delete'),
    path('attendance/devices/<int:device_id>/test/', web_views.biometric_device_test, name='biometric_device_test'),
    path('attendance/devices/<int:device_id>/sync/', web_views.biometric_device_sync, name='biometric_device_sync'),
    path('attendance/devices/<int:device_id>/sync-users/', web_views.biometric_device_sync_users, name='biometric_device_sync_users'),
    path(
        'attendance/devices/<int:device_id>/agent-key/',
        web_views.biometric_device_generate_agent_key,
        name='biometric_device_generate_agent_key',
    ),
    path('attendance/enrollments/save/', web_views.biometric_enrollment_save, name='biometric_enrollment_save'),
    path('attendance/records/', web_views.attendance_records_list, name='attendance_records'),
    path('attendance/records/pull/', web_views.attendance_records_pull, name='attendance_records_pull'),
    path('attendance/records/reclassify/', web_views.attendance_records_reclassify, name='attendance_records_reclassify'),
    path('attendance/records/export/', web_views.attendance_records_export, name='attendance_records_export'),
    path('attendance/report/', web_views.attendance_report, name='attendance_report'),
    path('attendance/report/export/', web_views.attendance_report_export, name='attendance_report_export'),

    # ══════════════════════════════════════════════════════════════
    # 11. مسير الرواتب الشهري
    # ══════════════════════════════════════════════════════════════
    path('cash-shortages/', web_views.list_cash_shortages, name='list_cash_shortages'),
    path('cash-shortages/register/', web_views.register_cash_shortage, name='register_cash_shortage'),

    path('payroll/', payroll_views.list_payroll_runs, name='list_payroll_runs'),                            # قائمة المسيرات
    path('payroll/export/', payroll_views.export_payroll_list_excel, name='export_payroll_list_excel'),    # تصدير المسير الموحّد
    path('payroll/create/', payroll_views.create_payroll_run, name='create_payroll_run'),                    # إنشاء/بناء مسير
    path('payroll/<int:run_id>/', payroll_views.view_payroll_run, name='view_payroll_run'),                  # عرض تفاصيل المسير
    path('payroll/<int:run_id>/delete/', payroll_views.delete_payroll_draft_run, name='delete_payroll_draft_run'),  # حذف مسودة
    path('payroll/<int:run_id>/rebuild/', payroll_views.rebuild_payroll_run, name='rebuild_payroll_run'),     # إعادة بناء
    path('payroll/<int:run_id>/lock/', payroll_views.lock_payroll_run_view, name='lock_payroll_run'),         # ترحيل (قفل)
    path('payroll/<int:run_id>/unlock/', payroll_views.unlock_payroll_run_view, name='unlock_payroll_run'),   # إلغاء ترحيل (سوبر يوزر فقط)
    path('payroll/<int:run_id>/export/', payroll_views.export_payroll_run_excel, name='export_payroll_run_excel'),  # تصدير Excel

    # ── المصادقة ────────────────────────────────────────────────
    path('auth/', include((auth_patterns, 'auth'))),
    
    # إعادة توجيه الرابط القديم /login/ إلى /auth/login/
    path('login/', RedirectView.as_view(pattern_name='web:auth:login', permanent=True)),
]
