from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0006_administration_manager'),
        ('core', '0030_systemauditlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='pendingaction',
            name='administration',
            field=models.ForeignKey(
                blank=True,
                help_text='يُستخدم لتوجيه الطلب لمدير الإدارة المسؤول (مع fallback للفرع).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pending_actions',
                to='setup.administration',
                verbose_name='الإدارة',
            ),
        ),
        migrations.AddField(
            model_name='historicalpendingaction',
            name='administration',
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text='يُستخدم لتوجيه الطلب لمدير الإدارة المسؤول (مع fallback للفرع).',
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+',
                to='setup.administration',
                verbose_name='الإدارة',
            ),
        ),
        migrations.AddIndex(
            model_name='pendingaction',
            index=models.Index(fields=['administration', 'status'], name='core_pendin_adminis_d3e0f8_idx'),
        ),
    ]
