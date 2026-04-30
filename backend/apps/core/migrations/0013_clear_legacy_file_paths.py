"""One-time data migration: clear all FileField/ImageField path strings.

After switching media storage from local disk to Cloudflare R2, the old
local paths stored in the DB point to nothing. This migration wipes
those path strings (it does NOT touch any actual files) so users can
re-upload fresh.

Recorded in `django_migrations` → guaranteed to run exactly once,
permanently, regardless of container rebuilds.
"""
from django.db import migrations, models
from django.db.models import Q


def clear_file_paths(apps, schema_editor):
    """Clear every FileField/ImageField value across all app models."""
    for model in apps.get_models():
        # Skip historical mirrors (django-simple-history)
        if model.__name__.startswith('Historical'):
            continue

        file_fields = [
            f.name for f in model._meta.get_fields()
            if isinstance(f, (models.FileField, models.ImageField))
        ]
        if not file_fields:
            continue

        q = Q()
        for fname in file_fields:
            q |= ~Q(**{fname: ''}) & ~Q(**{f'{fname}__isnull': True})

        update_kwargs = {f: '' for f in file_fields}
        # .update() bypasses save()/signals/validators — exactly what we want.
        model._default_manager.filter(q).update(**update_kwargs)


def noop_reverse(apps, schema_editor):
    """Cannot un-clear paths (data was already gone). Allow rollback as no-op."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_remove_historicalinsurance_history_user_and_more'),
    ]

    operations = [
        migrations.RunPython(clear_file_paths, noop_reverse),
    ]
