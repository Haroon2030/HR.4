"""إضافة بدل التغذية لملف الموظف وطلب التوظيف."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0026_remove_passport_residency_expiry_dates'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='meal_allowance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.',
                max_digits=12,
                verbose_name='بدل التغذية',
            ),
        ),
        migrations.AddField(
            model_name='employmentrequest',
            name='meal_allowance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.',
                max_digits=12,
                verbose_name='بدل التغذية',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='meal_allowance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.',
                max_digits=12,
                verbose_name='بدل التغذية',
            ),
        ),
        migrations.AddField(
            model_name='historicalemploymentrequest',
            name='meal_allowance',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='يُضاف لإجمالي الراتب والمسير، ولا يُحتسب ضمن مكافأة نهاية الخدمة.',
                max_digits=12,
                verbose_name='بدل التغذية',
            ),
        ),
    ]
