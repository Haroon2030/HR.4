from django.core.management.base import BaseCommand

from apps.employees.services.ledger_recalculate import recalculate_all_employee_ledgers


class Command(BaseCommand):
    help = 'إعادة حساب سجل المخصصات على قاعدة الشهر = 30 يوماً (1.75 يوم/شهر).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employee-id',
            type=int,
            action='append',
            dest='employee_ids',
            help='معرّف موظف محدد (يمكن تكراره)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض النتائج دون حفظ التغييرات',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        results = recalculate_all_employee_ledgers(
            employee_ids=options.get('employee_ids'),
            dry_run=dry_run,
        )

        if not results:
            self.stdout.write(self.style.WARNING('لا يوجد موظفون بسجل مخصصات.'))
            return

        updated = sum(r.entries_updated for r in results)
        removed = sum(r.entries_removed for r in results)
        prefix = '[تجريبي] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}تمت معالجة {len(results)} موظفاً — '
                f'قُيّد {updated} سطراً، أُزيل {removed} رصيداً افتتاحياً مكرراً.'
            ),
        )

        for result in results:
            if result.entries_updated or result.entries_removed:
                self.stdout.write(
                    f'  موظف #{result.employee_id}: '
                    f'محدّث {result.entries_updated}، محذوف {result.entries_removed}، '
                    f'رصيد إجازات نهائي {result.final_leave_days} يوم '
                    f'({result.final_leave_amount} ر.س)',
                )
