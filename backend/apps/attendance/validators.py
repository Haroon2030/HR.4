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
