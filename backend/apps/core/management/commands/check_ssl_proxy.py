"""التحقق من إعداد SSL والبروكسي في الإنتاج."""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'فحص USE_HTTPS و CSRF_TRUSTED_ORIGINS ومتطلبات X-Forwarded-Proto'

    def handle(self, *args, **options):
        use_https = getattr(settings, 'USE_HTTPS', False)
        csrf = list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) or [])
        allowed = list(getattr(settings, 'ALLOWED_HOSTS', []) or [])

        self.stdout.write('=== SSL / Proxy ===\n')
        self.stdout.write(f'USE_HTTPS={use_https}')
        self.stdout.write(f'SECURE_SSL_REDIRECT={getattr(settings, "SECURE_SSL_REDIRECT", False)}')
        self.stdout.write(f'SECURE_PROXY_SSL_HEADER={getattr(settings, "SECURE_PROXY_SSL_HEADER", None)}')
        self.stdout.write(f'CSRF_TRUSTED_ORIGINS={csrf}')
        self.stdout.write(f'ALLOWED_HOSTS={allowed}\n')

        if use_https:
            https_csrf = [o for o in csrf if o.startswith('https://')]
            if not https_csrf:
                self.stdout.write(
                    self.style.ERROR(
                        'USE_HTTPS=true لكن لا يوجد https:// في CSRF_TRUSTED_ORIGINS — '
                        'أضف https://your-domain.com'
                    )
                )
            self.stdout.write(
                'تحقق خارجياً: curl -s "https://YOUR_DOMAIN/health/?proxy=1"\n'
                '  x_forwarded_proto يجب أن يكون "https" و is_secure=true\n'
            )
            if not getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
                self.stdout.write(
                    self.style.WARNING('SECURE_PROXY_SSL_HEADER غير مضبوط — Django لن يكتشف HTTPS.')
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'USE_HTTPS=false — HTTP mode. للـ SSL: USE_HTTPS=true + CSRF https:// + '
                    'ترويسة X-Forwarded-Proto من البروكسي.'
                )
            )

        self.stdout.write(
            '\nNginx: proxy_set_header X-Forwarded-Proto $scheme;\n'
            'راجع docs/ssl-production.md'
        )
