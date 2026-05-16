"""تسميات عربية لحقول جهاز ZKTeco."""

ZK_PUNCH_STATUS = {
    0: ('in', 'دخول'),
    1: ('out', 'خروج'),
    2: ('break_out', 'خروج استراحة'),
    3: ('break_in', 'عودة استراحة'),
    4: ('ot_in', 'إضافي دخول'),
    5: ('ot_out', 'إضافي خروج'),
}

VERIFY_MODE_LABELS = {
    0: 'كلمة مرور',
    1: 'بصمة',
    2: 'بطاقة',
    3: 'كلمة مرور + بصمة',
    4: 'كلمة مرور + بطاقة',
    5: 'بصمة + بطاقة',
    6: 'كلمة مرور + بصمة + بطاقة',
    8: 'وجه',
    9: 'بصمة + وجه',
    10: 'بطاقة + وجه',
    11: 'بصمة + بطاقة + وجه',
    15: 'وجه (uFace)',
}


def punch_type_for_status(status: int | None) -> tuple[str, str]:
    if status is None:
        return 'unknown', 'غير محدد'
    code, label = ZK_PUNCH_STATUS.get(status, ('unknown', 'غير محدد'))
    return code, label


def verify_mode_label(mode: int | None) -> str:
    if mode is None:
        return '—'
    return VERIFY_MODE_LABELS.get(mode, f'رمز {mode}')
