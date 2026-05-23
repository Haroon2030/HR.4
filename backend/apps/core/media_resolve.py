"""
Resolve Cloudflare R2 object keys for media files.

Legacy uploads used paths like:
    employees/statements/file.jpg

Current storage uses:
    HR/employees/statements/<year>/file_<uuid>.jpg
"""
from __future__ import annotations

import os
from datetime import datetime

from botocore.exceptions import ClientError

from apps.core.storages import PROJECT_PREFIX, HRMediaStorage

_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})


def iter_r2_key_candidates(path: str):
    """Yield likely R2 keys for a stored media path."""
    path = path.replace("\\", "/").lstrip("/")
    if not path:
        return

    yield path

    if not path.startswith(f"{PROJECT_PREFIX}/"):
        yield f"{PROJECT_PREFIX}/{path}"

    directory, basename = os.path.split(path)
    if directory and not path.startswith(f"{PROJECT_PREFIX}/"):
        current_year = datetime.now().year
        for year in range(current_year, current_year - 12, -1):
            yield f"{PROJECT_PREFIX}/{directory}/{year}/{basename}"


def _search_prefixes(path: str) -> set[str]:
    directory = os.path.dirname(path.replace("\\", "/").lstrip("/"))
    prefixes: set[str] = set()
    if not directory:
        return prefixes

    prefixes.add(f"{directory}/")
    prefixes.add(f"{PROJECT_PREFIX}/{directory}/")
    current_year = datetime.now().year
    for year in range(current_year, current_year - 12, -1):
        prefixes.add(f"{PROJECT_PREFIX}/{directory}/{year}/")
    return prefixes


def find_r2_object_key(storage: HRMediaStorage, path: str) -> str | None:
    """Find the actual R2 key for a media path (exact + legacy layouts)."""
    path = path.replace("\\", "/").lstrip("/")
    if not path:
        return None

    client = storage.connection.meta.client
    bucket = storage.bucket_name

    for key in iter_r2_key_candidates(path):
        try:
            client.head_object(Bucket=bucket, Key=key)
            return key
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in _NOT_FOUND:
                raise

    basename = os.path.basename(path)
    stem, ext = os.path.splitext(basename)
    if not stem:
        return None

    paginator = client.get_paginator("list_objects_v2")
    for prefix in sorted(_search_prefixes(path), key=len, reverse=True):
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                base = os.path.basename(key)
                if base == basename:
                    return key
                obj_stem, obj_ext = os.path.splitext(base)
                if obj_ext.lower() != ext.lower():
                    continue
                if obj_stem == stem or obj_stem.startswith(f"{stem}_"):
                    return key

    return None
