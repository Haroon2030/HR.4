"""نسخ احتياطي تلقائي قبل تطبيق migrations (جداول / تغييرات على البيانات)."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

logger = logging.getLogger(__name__)


def has_pending_migrations(database: str = 'default') -> bool:
    """هل توجد migrations لم تُطبَّق بعد؟"""
    connection = connections[database]
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    return bool(executor.migration_plan(targets))


def backup_log_table_exists() -> bool:
    from apps.core.models import DatabaseBackupLog

    table = DatabaseBackupLog._meta.db_table
    with connections['default'].cursor() as cursor:
        return table in connections['default'].introspection.table_names(cursor)


def run_pre_migration_backup_if_needed(stdout=None) -> bool:
    """
    ينفّذ backup_db ويرفع إلى R2 (إن USE_R2) قبل أي migrate معلّق.
    يُرجع True إذا تم تنفيذ النسخ، False إذا تخطّى (معطّل أو لا migrations).
    """
    if not getattr(settings, 'BACKUP_BEFORE_MIGRATE', True):
        return False
    if not has_pending_migrations():
        if stdout:
            stdout.write('لا توجد migrations معلّقة — تخطي النسخ قبل المهاجرات.')
        return False

    if stdout:
        stdout.write('توجد migrations معلّقة — نسخ احتياطي إلى R2 قبل التطبيق...')

    call_command(
        'backup_db',
        label='pre-migrate',
        trigger='migrate',
        verbosity=1,
    )
    return True
