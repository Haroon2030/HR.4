from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0033_recalc_absence_30_day_rule'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='account_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('bank_account', 'BANK ACCOUNT'),
                    ('salary_card', 'SALARY CARD'),
                    ('sarie', 'SARIE'),
                ],
                default='',
                max_length=20,
                verbose_name='طبيعة الحساب',
            ),
        ),
        migrations.AddField(
            model_name='employmentrequest',
            name='account_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('bank_account', 'BANK ACCOUNT'),
                    ('salary_card', 'SALARY CARD'),
                    ('sarie', 'SARIE'),
                ],
                default='',
                max_length=20,
                verbose_name='طبيعة الحساب',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='account_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('bank_account', 'BANK ACCOUNT'),
                    ('salary_card', 'SALARY CARD'),
                    ('sarie', 'SARIE'),
                ],
                default='',
                max_length=20,
                verbose_name='طبيعة الحساب',
            ),
        ),
        migrations.AddField(
            model_name='historicalemploymentrequest',
            name='account_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('bank_account', 'BANK ACCOUNT'),
                    ('salary_card', 'SALARY CARD'),
                    ('sarie', 'SARIE'),
                ],
                default='',
                max_length=20,
                verbose_name='طبيعة الحساب',
            ),
        ),
    ]
