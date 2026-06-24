from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0041_tighten_upload_extensions'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='leave_accrual_start_date',
            field=models.DateField(
                blank=True,
                help_text='يُستخدم بعد الترحيل — الافتراضي تاريخ الانتقال العام في الإعدادات.',
                null=True,
                verbose_name='تاريخ بدء احتساب الإجازة في النظام',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='opening_leave_days',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='المتبقي من النظام القديم عند تاريخ الانتقال.',
                max_digits=8,
                verbose_name='رصيد إجازة افتتاحي (أيام)',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='opening_eosb_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='المخصص المتراكم المستورد من النظام القديم عند الانتقال.',
                max_digits=12,
                verbose_name='مخصص نهاية خدمة افتتاحي (ر.س)',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='migration_locked',
            field=models.BooleanField(
                default=False,
                help_text='يمنع إعادة الاستيراد ويفعّل احتساب الإجازة من تاريخ الانتقال.',
                verbose_name='اعتماد أرصدة الترحيل',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='leave_accrual_start_date',
            field=models.DateField(
                blank=True,
                help_text='يُستخدم بعد الترحيل — الافتراضي تاريخ الانتقال العام في الإعدادات.',
                null=True,
                verbose_name='تاريخ بدء احتساب الإجازة في النظام',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='opening_leave_days',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='المتبقي من النظام القديم عند تاريخ الانتقال.',
                max_digits=8,
                verbose_name='رصيد إجازة افتتاحي (أيام)',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='opening_eosb_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='المخصص المتراكم المستورد من النظام القديم عند الانتقال.',
                max_digits=12,
                verbose_name='مخصص نهاية خدمة افتتاحي (ر.س)',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='migration_locked',
            field=models.BooleanField(
                default=False,
                help_text='يمنع إعادة الاستيراد ويفعّل احتساب الإجازة من تاريخ الانتقال.',
                verbose_name='اعتماد أرصدة الترحيل',
            ),
        ),
    ]
