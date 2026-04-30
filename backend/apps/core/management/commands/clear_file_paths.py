"""Clear all FileField/ImageField values across the project.

This wipes the path strings stored in the DB (it does NOT delete any
actual files on disk or on R2). Use it once after switching storage
backends so users can re-upload their documents fresh.

Usage:
    python manage.py clear_file_paths            # dry-run (shows counts only)
    python manage.py clear_file_paths --apply    # actually clear
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models, transaction


class Command(BaseCommand):
    help = "Clear all FileField/ImageField values in the DB (paths only, no file deletion)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually perform the update. Without this flag, only counts are reported.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        targets = []

        for model in apps.get_models():
            # Skip historical models from django-simple-history
            if model._meta.app_label == 'admin':
                continue
            if model.__name__.startswith('Historical'):
                continue

            file_fields = [
                f.name for f in model._meta.get_fields()
                if isinstance(f, (models.FileField, models.ImageField))
            ]
            if not file_fields:
                continue

            # Build OR condition: any field non-empty
            from django.db.models import Q
            q = Q()
            for fname in file_fields:
                q |= ~Q(**{fname: ''}) & ~Q(**{f'{fname}__isnull': True})

            qs = model._default_manager.filter(q)
            count = qs.count()
            if count:
                targets.append((model, file_fields, qs, count))

        if not targets:
            self.stdout.write(self.style.SUCCESS("No file paths found in any model."))
            return

        total = 0
        for model, fields, qs, count in targets:
            label = f"{model._meta.app_label}.{model.__name__}"
            self.stdout.write(
                f"  {label:50s}  rows={count:5d}  fields={','.join(fields)}"
            )
            total += count

        self.stdout.write("")
        self.stdout.write(f"Total rows with file paths: {total}")

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\nDry-run only. Re-run with --apply to actually clear the paths."
            ))
            return

        with transaction.atomic():
            cleared = 0
            for model, fields, qs, _count in targets:
                update_kwargs = {f: '' for f in fields}
                # Use update() to bypass save() / signals / validators
                n = qs.update(**update_kwargs)
                cleared += n
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  cleared {n:5d} rows in {model._meta.app_label}.{model.__name__}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. Cleared file paths in {cleared} rows. Users can now re-upload."
        ))
