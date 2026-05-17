"""تحقق من مدخلات أجهزة البصمة."""
from __future__ import annotations

import ipaddress


def validate_device_ipv4(value: str) -> str:
    """يرجع IP صالحاً أو يرفع ValueError برسالة عربية."""
    raw = (value or '').strip()
    if not raw:
        raise ValueError('عنوان IP مطلوب.')
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        raise ValueError(
            f'عنوان IP غير صالح: «{raw}». '
            'أدخل عنواناً كاملاً مثل 192.168.24.59'
        ) from None
    if addr.version != 4:
        raise ValueError('يُقبل IPv4 فقط لأجهزة ZKTeco.')
    return str(addr)


def is_private_lan_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address((value or '').strip()).is_private
    except ValueError:
        return False


def cloud_pull_blocked_message(device, *, force_mock: bool | None = None) -> str | None:
    """رسالة فورية إن كان السحب من السيرفر السحابي مستحيلاً (شبكة LAN)."""
    if force_mock is True:
        return None
    from django.conf import settings

    if force_mock is None and getattr(settings, 'BIOMETRIC_MOCK_MODE', False):
        return None
    if not is_private_lan_ip(str(device.ip_address)):
        return None
    return (
        f'الجهاز «{device.name}» على شبكة محلية ({device.ip_address}) — '
        'السيرفر السحابي لا يصل إليه (لن ينتظر دقائق). '
        f'من PC الفرع: python agent.py --once --device {device.pk}'
    )
