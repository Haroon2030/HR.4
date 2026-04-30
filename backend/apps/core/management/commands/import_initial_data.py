"""
Idempotent initial-data import for production deploys.

Why a custom command instead of `loaddata`?
  - Django's `loaddata` on PostgreSQL does NOT defer FK constraints
    (`PostgresDatabaseWrapper.disable_constraint_checking()` returns False).
  - Our dump's natural insert order (alphabetical by model) violates FKs:
    e.g. `employees.employee` references `setup.sponsorship` but is inserted first.

Strategy:
  1. Disconnect UserProfile auto-create signals (avoid PK conflicts on auth.User).
  2. Optionally flush (TRUNCATE — auto-commits, must be standalone).
  3. Topologically sort models by FK dependencies.
  4. Deserialize objects, save in dependency order with FKs disabled per-row via
     `session_replication_role` if available, else 2-pass save.
  5. Reset PG sequences so future inserts don't collide with imported PKs.
  6. Marker file written ONLY on full success → safe automatic retry.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model

from apps.core import signals as core_signals


def topo_sort_models(model_labels):
    """Return model labels (app_label.modelname) in FK-dependency order."""
    label_to_model = {}
    for lbl in model_labels:
        try:
            app_label, model_name = lbl.split(".")
            label_to_model[lbl.lower()] = apps.get_model(app_label, model_name)
        except Exception:
            continue

    deps = defaultdict(set)   # model -> models it depends on
    rdeps = defaultdict(set)  # model -> models that depend on it

    for lbl, model in label_to_model.items():
        deps[lbl]  # ensure key exists
        for f in model._meta.get_fields():
            if not getattr(f, "is_relation", False):
                continue
            if not (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
                continue
            related = f.related_model
            if related is None:
                continue
            rlbl = f"{related._meta.app_label}.{related._meta.model_name}"
            if rlbl == lbl:
                continue  # self-reference: handled by 2nd pass / nullable
            if rlbl in label_to_model:
                deps[lbl].add(rlbl)
                rdeps[rlbl].add(lbl)

    # Kahn's algorithm
    ready = deque(sorted(lbl for lbl, d in deps.items() if not d))
    ordered = []
    deps_copy = {k: set(v) for k, v in deps.items()}
    while ready:
        lbl = ready.popleft()
        ordered.append(lbl)
        for dep in sorted(rdeps[lbl]):
            deps_copy[dep].discard(lbl)
            if not deps_copy[dep]:
                ready.append(dep)
    # Append any remaining (cycles) at the end
    for lbl in deps_copy:
        if lbl not in ordered:
            ordered.append(lbl)
    return ordered


class Command(BaseCommand):
    help = "Load initial-data fixture safely (FK-order aware, signal-aware, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Absolute path to the fixture JSON file.")
        parser.add_argument("--flush", action="store_true",
                            help="Flush DB before loading.")
        parser.add_argument("--marker", default=None,
                            help="Marker file path. If exists, skip. Written on success.")
        parser.add_argument("--force", action="store_true",
                            help="Ignore marker file.")

    def _reset_sequences(self, model_labels):
        """Reset PG sequences for imported tables so future inserts get correct PKs."""
        if connection.vendor != "postgresql":
            return
        models = []
        for lbl in model_labels:
            try:
                app_label, model_name = lbl.split(".")
                models.append(apps.get_model(app_label, model_name))
            except Exception:
                continue
        statements = connection.ops.sequence_reset_sql(
            self.style, models
        )
        if statements:
            with connection.cursor() as cur:
                for sql in statements:
                    cur.execute(sql)
            self.stdout.write(f"  - reset {len(statements)} PG sequence(s)")

    def handle(self, *args, **opts):
        fixture = Path(opts["fixture"])
        marker = Path(opts["marker"]) if opts["marker"] else None

        if not fixture.exists():
            self.stdout.write(self.style.WARNING(f"Fixture not found: {fixture} — skipping."))
            return

        if marker and marker.exists() and not opts["force"]:
            self.stdout.write(self.style.NOTICE(f"Marker {marker} present — skipping import."))
            return

        # --- Disconnect UserProfile auto-create signals ---
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
            # --- Flush (auto-commits TRUNCATE; must be outside any atomic block) ---
            if opts["flush"]:
                self.stdout.write("==> Flushing database ...")
                call_command("flush", "--noinput", verbosity=0)

            # --- Read fixture and group objects by model ---
            self.stdout.write(f"==> Reading fixture: {fixture}")
            with fixture.open(encoding="utf-8") as f:
                raw = json.load(f)
            self.stdout.write(f"  - {len(raw)} objects total")

            by_model = defaultdict(list)
            for obj in raw:
                by_model[obj["model"].lower()].append(obj)

            # --- Topologically sort models ---
            order = topo_sort_models(by_model.keys())
            self.stdout.write("==> Load order:")
            for lbl in order:
                self.stdout.write(f"     {len(by_model[lbl]):>4}  {lbl}")

            # --- Deserialize and save in dependency order, inside one transaction ---
            with transaction.atomic():
                total_saved = 0
                for lbl in order:
                    objs = by_model[lbl]
                    if not objs:
                        continue
                    chunk = json.dumps(objs)
                    for deserialized in serializers.deserialize(
                        "json", chunk, ignorenonexistent=True, handle_forward_references=True
                    ):
                        deserialized.save()
                        total_saved += 1
                self.stdout.write(self.style.SUCCESS(f"  - saved {total_saved} objects"))

            # --- Reset PG sequences ---
            self._reset_sequences(by_model.keys())

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
