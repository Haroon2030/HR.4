from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0006_administration_manager'),
        ('employees', '0028_employee_administration'),
    ]

    operations = [
        migrations.AddField(
            model_name='employmentrequest',
            name='administration',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='employment_requests',
                to='setup.administration',
                verbose_name='الإدارة',
            ),
        ),
        migrations.AddField(
            model_name='historicalemploymentrequest',
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
