class ContentSecurityPolicyMiddleware:
    """
    Adds a Content-Security-Policy header to every response.

    Sources:
    - Scripts: self + cdn.jsdelivr.net (chess.js only). Alpine.js and HTMX
      are served from local static files.  'unsafe-eval' is required because
      Alpine.js v3 uses new Function() internally to evaluate x-data / x-init
      expressions.
    - Styles: 'unsafe-inline' required for Tailwind's scoped inline styles and
      the chess board's <style> block.
    - WebSockets: wss: and ws: for Django Channels (chess + coin flip games).
    - frame-ancestors: 'none' prevents the app from being embedded in iframes
      (replaces / reinforces X-Frame-Options: DENY from Django middleware).
    """

    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' wss: ws:; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = self.CSP
        return response
