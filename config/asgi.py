import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

django_asgi_app = get_asgi_application()

from apps.coinflip.routing import websocket_urlpatterns as coinflip_ws_patterns  # noqa: E402
from apps.chess.routing import websocket_urlpatterns as chess_ws_patterns  # noqa: E402

all_websocket_patterns = coinflip_ws_patterns + chess_ws_patterns

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(all_websocket_patterns)
    ),
})
