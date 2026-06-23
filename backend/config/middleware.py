"""
Custom Middleware
"""
import re


class ProxyForwardedHeadersMiddleware:
    """
    يُطبَّق قبل SecurityMiddleware — يضمن وجود X-Forwarded-Proto للبروكسي (Traefik/Nginx/Dokploy).

    Django يعتمد على SECURE_PROXY_SSL_HEADER لاكتشاف HTTPS خلف reverse proxy.
    إن لم يرسل البروكسي X-Forwarded-Proto يفشل تسجيل الدخول وSSL redirect.
    """

    _FORWARDED_PROTO_RE = re.compile(r'proto=([^;,\s]+)', re.IGNORECASE)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        meta = request.META
        if not (meta.get('HTTP_X_FORWARDED_PROTO') or '').strip():
            forwarded = (meta.get('HTTP_FORWARDED') or '').strip()
            if forwarded:
                match = self._FORWARDED_PROTO_RE.search(forwarded)
                if match:
                    meta['HTTP_X_FORWARDED_PROTO'] = match.group(1).lower()
        return self.get_response(request)


class DisableCOOPMiddleware:
    """
    Middleware لإزالة Cross-Origin-Opener-Policy header
    لأنه يسبب تحذيرات في المتصفح عند استخدام HTTP
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # إزالة COOP header إذا كان موجوداً
        if 'Cross-Origin-Opener-Policy' in response:
            del response['Cross-Origin-Opener-Policy']
        # إزالة COOP بطريقة أخرى في حال كان موجوداً بحروف مختلفة
        response_headers_lower = {k.lower(): k for k in response.headers.keys()}
        if 'cross-origin-opener-policy' in response_headers_lower:
            del response[response_headers_lower['cross-origin-opener-policy']]
        return response
