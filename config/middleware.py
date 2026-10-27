from django.conf import settings

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        skip_csp = request.path.startswith("/admin/") or (
            settings.DEBUG and response.status_code >= 400
        )
        if not skip_csp:
            response.headers.setdefault(
                "Content-Security-Policy", CONTENT_SECURITY_POLICY
            )
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response