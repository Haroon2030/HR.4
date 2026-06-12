"""بيانات «عن النظام» للشريط العلوي — شركة، مطوّر، دعم، وصف."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

_CACHE_KEY = 'hr:app_info:v3'
_CACHE_TTL = 300


def get_app_info() -> dict[str, str]:
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    from apps.core.models import Company

    company = Company.objects.filter(is_deleted=False).order_by('id').only(
        'name', 'contact_phone', 'contact_email', 'logo',
    ).first()

    company_phone = (company.contact_phone if company else '') or ''
    support_phone = (getattr(settings, 'HR_SUPPORT_PHONE', '') or '').strip()

    info = {
        'company_name': (company.name if company else '') or '',
        'company_phone': company_phone,
        'company_email': (company.contact_email if company else '') or '',
        'company_logo_url': company.logo.url if company and company.logo else '',
        'developer': (getattr(settings, 'HR_APP_DEVELOPER', '') or '').strip(),
        'support_phone': support_phone,
        'description': (getattr(settings, 'HR_APP_DESCRIPTION', '') or '').strip(),
    }
    cache.set(_CACHE_KEY, info, _CACHE_TTL)
    return info
