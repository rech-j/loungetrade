from django.conf import settings as django_settings


class ContentSecurityPolicyMiddleware:
    """
    Adds a Content-Security-Policy header to every response.

    Sources:
    - Scripts: 'self' only (all JS is self-hosted). 'unsafe-eval' is required
      because Alpine.js v3 uses new Function() internally to evaluate
      x-data / x-init expressions.
    - Styles: 'unsafe-inline' required for Tailwind's scoped inline styles and
      the chess board's <style> block.
    - WebSockets: controlled by CSP_WS_ORIGIN setting. Defaults to the broad
      'ws: wss:' for development; production.py sets this to the specific
      origin (e.g. 'wss://loungecoin.trade') to prevent cross-site WS abuse.
    - frame-ancestors: 'none' prevents the app from being embedded in iframes
      (replaces / reinforces X-Frame-Options: DENY from Django middleware).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        ws_origin = getattr(django_settings, 'CSP_WS_ORIGIN', 'ws: wss:')
        self._csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            f"connect-src 'self' {ws_origin}; "
            "font-src 'self'; "
            "frame-ancestors 'none';"
        )

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = self._csp
        return response
