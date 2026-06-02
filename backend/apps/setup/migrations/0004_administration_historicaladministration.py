# Generated manually for Administration lookup
import simple_history.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('setup', '0003_bank_historicalbank'),
    ]

    operations = [
        migrations.CreateModel(
            name='Administration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='محذوف')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='رقم الإدارة')),
                ('name', models.CharField(max_length=150, verbose_name='اسم الإدارة')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
            ],
            options={
                'verbose_name': 'إدارة',
                'verbose_name_plural': 'الإدارات',
                'db_table': 'setup_administration',
                'ordering': ['code', 'name'],
            },
        ),
        migrations.CreateModel(
            name='HistoricalAdministration',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('created_at', models.DateTimeField(blank=True, editable=False, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(blank=True, editable=False, verbose_name='تاريخ التحديث')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='محذوف')),
                ('code', models.CharField(db_index=True, max_length=20, verbose_name='رقم الإدارة')),
                ('name', models.CharField(max_length=150, verbose_name='اسم الإدارة')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical إدارة',
                'verbose_name_plural': 'historical الإدارات',
                'db_table': 'setup_historicaladministration',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
