"""
Idempotent initial-data import for production deploys.

Strategy:
  1. Disconnect UserProfile auto-create signals (avoid PK conflicts on auth.User).
  2. Optionally flush (TRUNCATE — auto-commits, must be OUTSIDE any atomic block).
  3. PostgreSQL: ALTER every FK to DEFERRABLE INITIALLY DEFERRED (DDL, auto-commits).
     This is permanent but harmless — constraints are still enforced at COMMIT time.
  4. Run loaddata. Django's loaddata wraps the load in `constraint_checks_disabled()`
     which on PG issues `SET CONSTRAINTS ALL DEFERRED`. Now effective because FKs are
     deferrable, so cross-app references (employee → sponsorship) load in any order.
  5. Write marker file on success → automatic retry on next deploy if anything fails.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model

from apps.core import signals as core_signals


class Command(BaseCommand):
    help = "Load an initial-data fixture safely (signal-aware, FK-safe, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Absolute path to the fixture JSON file.")
        parser.add_argument("--flush", action="store_true",
                            help="Flush DB before loading (wipes rows, keeps schema).")
        parser.add_argument("--marker", default=None,
                            help="Marker file. If exists, skip. Written on success.")
        parser.add_argument("--force", action="store_true",
                            help="Ignore marker file.")

    def _make_fks_deferrable(self):
        """ALTER all non-deferrable FKs to DEFERRABLE INITIALLY DEFERRED."""
        if connection.vendor != "postgresql":
            return 0
        with connection.cursor() as cur:
            cur.execute("""
                SELECT n.nspname, c.relname, con.conname
                FROM pg_constraint con
                JOIN pg_class c     ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE con.contype = 'f'
                  AND NOT con.condeferrable
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            """)
            rows = cur.fetchall()
            for schema, table, conname in rows:
                cur.execute(
                    f'ALTER TABLE "{schema}"."{table}" '
                    f'ALTER CONSTRAINT "{conname}" DEFERRABLE INITIALLY DEFERRED'
                )
        return len(rows)

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
            # 1) Flush — TRUNCATE auto-commits in PG; must NOT be inside an atomic block.
            if opts["flush"]:
                self.stdout.write("==> Flushing database ...")
                call_command("flush", "--noinput", verbosity=0)

            # 2) Make all FKs deferrable (DDL, auto-commits).
            altered = self._make_fks_deferrable()
            self.stdout.write(f"  - made {altered} FK(s) deferrable (permanent)")

            # 3) loaddata handles its own transaction + constraint_checks_disabled().
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
            for fn, sig, sender in disconnected:
                sig.connect(fn, sender=sender)
                self.stdout.write(f"  - reconnected signal: {fn.__name__}")
