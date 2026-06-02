from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0029_employmentrequest_administration'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='contract_type',
            field=models.CharField(
                blank=True,
                choices=[('fixed', 'محدد المدة'), ('unlimited', 'غير محدد المدة')],
                default='',
                help_text='محدد أو غير محدد المدة — يُحدَّث تلقائياً للسعودي بعد 3 سنوات.',
                max_length=20,
                verbose_name='نوع العقد',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='contract_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='تاريخ بداية العقد'),
        ),
        migrations.AddField(
            model_name='employee',
            name='contract_duration_months',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='للسعودي: حد أقصى 12 شهراً.',
                null=True,
                verbose_name='مدة العقد (أشهر)',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='contract_duration_text',
            field=models.CharField(
                blank=True,
                help_text='للأجنبي: مثال «سنتان» أو «24 شهر».',
                max_length=100,
                verbose_name='مدة العقد (نص)',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='contract_type',
            field=models.CharField(
                blank=True,
                choices=[('fixed', 'محدد المدة'), ('unlimited', 'غير محدد المدة')],
                default='',
                help_text='محدد أو غير محدد المدة — يُحدَّث تلقائياً للسعودي بعد 3 سنوات.',
                max_length=20,
                verbose_name='نوع العقد',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='contract_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='تاريخ بداية العقد'),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='contract_duration_months',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='للسعودي: حد أقصى 12 شهراً.',
                null=True,
                verbose_name='مدة العقد (أشهر)',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='contract_duration_text',
            field=models.CharField(
                blank=True,
                help_text='للأجنبي: مثال «سنتان» أو «24 شهر».',
                max_length=100,
                verbose_name='مدة العقد (نص)',
            ),
        ),
    ]
