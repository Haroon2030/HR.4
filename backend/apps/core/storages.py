"""
Custom storage backend for Cloudflare R2.

Organizes media files as:
    HR/<operation>/<year>/<filename>

R2 compatibility notes:
- boto3 >= 1.36 sends new integrity checksum headers by default that
  Cloudflare R2 rejects (HeadObject / PutObject -> 400 Bad Request).
  We disable them via a botocore Config.
- We also override exists() to skip HeadObject probing; uniqueness is
  guaranteed by appending a short uuid to every filename in
  get_available_name().
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from botocore.config import Config
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


PROJECT_PREFIX = "HR"


def _r2_client_config() -> Config:
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": getattr(settings, "AWS_S3_ADDRESSING_STYLE", "path")},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 3, "mode": "standard"},
    )


class HRMediaStorage(S3Boto3Storage):
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
        kwargs.setdefault("client_config", _r2_client_config())
        super().__init__(*args, **kwargs)

    def _save(self, name, content):
        return super()._save(name, content)

    def get_available_name(self, name, max_length=None):
        """Build a unique key WITHOUT calling HeadObject on R2."""
        name = self._build_key(name)
        directory, filename = os.path.split(name)
        stem, ext = os.path.splitext(filename)
        suffix = uuid.uuid4().hex[:8]
        unique = f"{stem}_{suffix}{ext}"
        new_name = f"{directory}/{unique}" if directory else unique
        if max_length is not None and len(new_name) > max_length:
            keep = max_length - len(suffix) - len(ext) - 1 - (len(directory) + 1 if directory else 0)
            stem = stem[: max(1, keep)]
            unique = f"{stem}_{suffix}{ext}"
            new_name = f"{directory}/{unique}" if directory else unique
        return new_name

    def exists(self, name):
        # Skip HeadObject probes; uniqueness is handled above.
        return False

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
