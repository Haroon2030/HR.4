"""محققات كلمة المرور برسائل عربية."""
from __future__ import annotations

from django.core.exceptions import ValidationError


class ArabicMinimumLengthValidator:
    """الحد الأدنى لطول كلمة المرور (أحرف أو أرقام)."""

    def __init__(self, min_length: int = 6):
        self.min_length = min_length

    def validate(self, password: str, user=None) -> None:
        if len(password) < self.min_length:
            raise ValidationError(
                f'كلمة المرور قصيرة جداً. يجب ألا تقل عن {self.min_length} أحرف أو أرقام.',
                code='password_too_short',
            )

    def get_help_text(self) -> str:
        return (
            f'يجب ألا تقل كلمة المرور عن {self.min_length} أحرف أو أرقام. '
            'يمكن أن تكون أرقاماً فقط (مثل 123456).'
        )
