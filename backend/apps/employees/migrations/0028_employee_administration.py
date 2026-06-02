from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0004_administration_historicaladministration'),
        ('employees', '0027_employee_meal_allowance'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='administration',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='employees',
                to='setup.administration',
                verbose_name='الإدارة',
            ),
        ),
        migrations.AddField(
            model_name='historicalemployee',
            name='administration',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='setup.administration',
                verbose_name='الإدارة',
            ),
        ),
    ]
