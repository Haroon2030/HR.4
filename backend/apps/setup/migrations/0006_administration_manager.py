from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('setup', '0005_administration_deleted_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='administration',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='managed_administrations',
                to=settings.AUTH_USER_MODEL,
                verbose_name='مدير الإدارة',
            ),
        ),
        migrations.AddField(
            model_name='historicaladministration',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
                verbose_name='مدير الإدارة',
            ),
        ),
    ]
