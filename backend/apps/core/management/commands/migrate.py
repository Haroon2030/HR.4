"""
migrate مع نسخ احتياطي تلقائي إلى R2 قبل تطبيق أي migrations معلّقة.
"""
from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.migrate import Command as DjangoMigrateCommand

from apps.core.services.backup_migrate import run_pre_migration_backup_if_needed


class Command(DjangoMigrateCommand):
    help = (
        'تطبيق migrations مع نسخ احتياطي تلقائي لقاعدة البيانات إلى R2 '
        'عند وجود migrations معلّقة (BACKUP_BEFORE_MIGRATE).'
    )

    def handle(self, *args, **options):
        try:
            run_pre_migration_backup_if_needed(self.stdout)
        except Exception as exc:
            if getattr(settings, 'BACKUP_BEFORE_MIGRATE_REQUIRED', False):
                raise CommandError(
                    f'فشل النسخ الاحتياطي قبل المهاجرات (BACKUP_BEFORE_MIGRATE_REQUIRED): {exc}'
                ) from exc
            self.stdout.write(self.style.WARNING(
                f'!! فشل النسخ قبل المهاجرات (متابعة migrate): {exc}'
            ))
        return super().handle(*args, **options)
