"""ربط الإدارات بتقارير المدراء."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0010_operationsreportsettings_recipient_emails'),
    ]

    operations = [
        migrations.AddField(
            model_name='administration',
            name='report_recipient_role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', '— لا يربط بتقرير مدير'),
                    ('operations_manager', 'مدير العمليات'),
                    ('finance_manager', 'مدير الحسابات'),
                    ('data_manager', 'مدير البيانات'),
                    ('procurement_manager', 'مدير المشتريات'),
                ],
                default='',
                help_text='يربط موظفي هذه الإدارة بتقرير المدير المحدد في إعدادات التقرير.',
                max_length=32,
                verbose_name='تقرير العمليات اليومي',
            ),
        ),
    ]
