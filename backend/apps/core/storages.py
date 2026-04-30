"""
Custom storage backend for Cloudflare R2.

Organizes media files as:
    HR/<operation>/<year>/<filename>

Examples:
    HR/employees/id/2026/passport_123.pdf
    HR/company/logos/2026/logo.png
    HR/pending_actions/2026/note.pdf
"""
from __future__ import annotations

import os
from datetime import datetime

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


PROJECT_PREFIX = "HR"


class HRMediaStorage(S3Boto3Storage):
    """R2 storage that prefixes every key with HR/<operation>/<year>/."""

    file_overwrite = False
    default_acl = None
    querystring_auth = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("bucket_name", getattr(settings, "AWS_STORAGE_BUCKET_NAME", None))
        kwargs.setdefault("endpoint_url", getattr(settings, "AWS_S3_ENDPOINT_URL", None))
        kwargs.setdefault("access_key", getattr(settings, "AWS_ACCESS_KEY_ID", None))
        kwargs.setdefault("secret_key", getattr(settings, "AWS_SECRET_ACCESS_KEY", None))
        kwargs.setdefault("region_name", getattr(settings, "AWS_S3_REGION_NAME", "auto"))
        kwargs.setdefault("addressing_style", getattr(settings, "AWS_S3_ADDRESSING_STYLE", "path"))
        kwargs.setdefault("signature_version", "s3v4")
        super().__init__(*args, **kwargs)

    def _save(self, name, content):
        name = self._build_key(name)
        return super()._save(name, content)

    def get_available_name(self, name, max_length=None):
        name = self._build_key(name)
        return super().get_available_name(name, max_length=max_length)

    @staticmethod
    def _build_key(name: str) -> str:
        if name.startswith(f"{PROJECT_PREFIX}/"):
            return name
        directory, filename = os.path.split(name)
        year = str(datetime.now().year)
        parts = [PROJECT_PREFIX]
        if directory:
            parts.append(directory.strip("/"))
        parts.append(year)
        parts.append(filename)
        return "/".join(parts)
