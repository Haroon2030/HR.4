"""
Authenticated media file serving (local filesystem only).
"""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_http_methods


def _media_root() -> Path:
    return Path(settings.MEDIA_ROOT).resolve()


@login_required
@require_http_methods(['GET', 'HEAD'])
def serve_protected_media(request, path: str):
    """
    Serve files under MEDIA_ROOT only to authenticated users.
    R2/public CDN URLs are not routed here.
    """
    if getattr(settings, 'USE_R2', False):
        raise Http404('الملفات المخزّنة سحابياً لا تُخدم عبر هذا المسار.')

    root = _media_root()
    requested = (root / path).resolve()

    try:
        requested.relative_to(root)
    except ValueError:
        return HttpResponseForbidden('مسار غير مسموح.')

    if not requested.is_file():
        raise Http404()

    content_type, _ = mimetypes.guess_type(str(requested))
    response = FileResponse(
        requested.open('rb'),
        content_type=content_type or 'application/octet-stream',
    )
    if request.method == 'HEAD':
        response.close()
    return response
