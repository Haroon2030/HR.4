"""
Authenticated media file serving (local filesystem or Cloudflare R2).
"""
import logging
import mimetypes
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _media_root() -> Path:
    return Path(settings.MEDIA_ROOT).resolve()


def _normalize_media_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid path")
    return normalized


@login_required
@require_http_methods(["GET", "HEAD"])
def serve_protected_media(request, path: str):
    """
    Serve uploaded files only to authenticated users.
    With R2 + R2_PROXY_MEDIA, streams from the private bucket via the app.
    """
    try:
        safe_path = _normalize_media_path(path)
    except ValueError:
        return HttpResponseForbidden("مسار غير مسموح.")

    if getattr(settings, "USE_R2", False):
        return _serve_r2_media(request, safe_path)

    return _serve_local_media(request, safe_path)


def _serve_local_media(request, path: str):
    root = _media_root()
    requested = (root / path).resolve()

    try:
        requested.relative_to(root)
    except ValueError:
        return HttpResponseForbidden("مسار غير مسموح.")

    if not requested.is_file():
        raise Http404()

    content_type, _ = mimetypes.guess_type(str(requested))
    response = FileResponse(
        requested.open("rb"),
        content_type=content_type or "application/octet-stream",
    )
    if request.method == "HEAD":
        response.close()
    return response


def _serve_r2_media(request, path: str):
    from apps.core.storages import HRMediaStorage

    storage = HRMediaStorage()
    try:
        file_obj = storage.open(path, "rb")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            raise Http404() from exc
        logger.exception("R2 media read failed for %s", path)
        raise Http404() from exc
    except FileNotFoundError as exc:
        raise Http404() from exc
    except Exception as exc:
        logger.exception("Unexpected media read error for %s", path)
        raise Http404() from exc

    content_type, _ = mimetypes.guess_type(path)
    response = FileResponse(
        file_obj,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = "inline"
    if request.method == "HEAD":
        response.close()
    return response
