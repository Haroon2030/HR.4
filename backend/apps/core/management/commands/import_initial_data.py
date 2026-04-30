"""
Idempotent initial-data import for production deploys.

Handles the UserProfile signal conflict by temporarily disconnecting
the post_save receivers on auth.User during loaddata, so the dump's
UserProfile rows aren't shadowed by auto-created blanks.

Usage:
    python manage.py import_initial_data /app/data_dump.json
    python manage.py import_initial_data /app/data_dump.json --flush
"""
from __future__ import annotations

import os
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model

from apps.core import signals as core_signals


class Command(BaseCommand):
    help = "Load an initial-data fixture safely (signal-aware, idempotent via marker file)."

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Absolute path to the fixture JSON file.")
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Flush the database before loading (wipes existing rows, keeps schema).",
        )
        parser.add_argument(
            "--marker",
            default=None,
            help="Marker file path. If it exists, import is skipped. Written on success.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignore marker file and import anyway.",
        )

    def handle(self, *args, **opts):
        fixture = Path(opts["fixture"])
        marker = Path(opts["marker"]) if opts["marker"] else None

        if not fixture.exists():
            self.stdout.write(self.style.WARNING(f"Fixture not found: {fixture} — skipping."))
            return

        if marker and marker.exists() and not opts["force"]:
            self.stdout.write(self.style.NOTICE(f"Marker {marker} present — skipping import."))
            return

        User = get_user_model()

        # Disconnect UserProfile auto-create signals so loaddata can insert them verbatim.
        receivers = [
            (core_signals.create_user_profile, post_save, User),
            (core_signals.save_user_profile, post_save, User),
        ]
        disconnected = []
        for fn, sig, sender in receivers:
            if sig.disconnect(receiver=fn, sender=sender):
                disconnected.append((fn, sig, sender))
                self.stdout.write(f"  - disconnected signal: {fn.__name__}")

        try:
            with transaction.atomic():
                if opts["flush"]:
                    self.stdout.write("==> Flushing database ...")
                    call_command("flush", "--noinput", verbosity=0)

                # Defer FK checks to the end of the transaction so rows can be
                # inserted in any order (e.g. employee → sponsorship). Django does
                # NOT create FKs as DEFERRABLE by default, so we first alter every
                # non-deferrable FK to DEFERRABLE INITIALLY DEFERRED, then defer.
                # This is a permanent schema change but is semantically harmless —
                # constraints are still enforced, just at COMMIT time.
                if connection.vendor == "postgresql":
                    with connection.cursor() as cur:
                        cur.execute(
                            "SELECT conname, conrelid::regclass::text "
                            "FROM pg_constraint "
                            "WHERE contype = 'f' AND NOT condeferrable"
                        )
                        rows = cur.fetchall()
                        for conname, tbl in rows:
                            cur.execute(
                                f'ALTER TABLE {tbl} ALTER CONSTRAINT "{conname}" '
                                f'DEFERRABLE INITIALLY DEFERRED'
                            )
                        cur.execute("SET CONSTRAINTS ALL DEFERRED")
                    self.stdout.write(
                        f"  - made {len(rows)} FK(s) deferrable; constraints deferred until commit"
                    )

                self.stdout.write(f"==> Loading fixture: {fixture}")
                call_command("loaddata", str(fixture), verbosity=1)

            if marker:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
                self.stdout.write(self.style.SUCCESS(f"==> Marker written: {marker}"))

            self.stdout.write(self.style.SUCCESS("==> Initial data imported successfully."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"!! Import failed: {exc}"))
            raise CommandError(str(exc))
        finally:
            # Always reconnect signals.
            for fn, sig, sender in disconnected:
                sig.connect(fn, sender=sender)
                self.stdout.write(f"  - reconnected signal: {fn.__name__}")
