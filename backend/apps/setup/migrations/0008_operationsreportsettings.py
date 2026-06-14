from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setup', '0007_sponsorship_commercial_registration'),
    ]

    operations = [
        migrations.CreateModel(
            name='OperationsReportSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_email', models.EmailField(blank=True, default='', max_length=254, verbose_name='البريد المستلم')),
                ('is_enabled', models.BooleanField(default=False, verbose_name='تفعيل الإرسال التلقائي')),
                ('send_hour', models.PositiveSmallIntegerField(default=12, help_text='يُرسل التقرير يومياً عند هذه الساعة (توقيت السيرفر).', verbose_name='ساعة الإرسال (24)')),
                ('include_pending', models.BooleanField(default=True, verbose_name='تضمين العمليات المعلّقة')),
                ('include_completed', models.BooleanField(default=True, verbose_name='تضمين العمليات المُنجزة (يوم التقرير)')),
                ('last_sent_at', models.DateTimeField(blank=True, null=True, verbose_name='آخر إرسال')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')),
            ],
            options={
                'verbose_name': 'إعدادات تقرير العمليات',
                'verbose_name_plural': 'إعدادات تقرير العمليات',
                'db_table': 'setup_operationsreportsettings',
            },
        ),
    ]
