"""
Custom Middleware
"""


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
