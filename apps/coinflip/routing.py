from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/coinflip/(?P<challenge_id>\d+)/$', consumers.CoinFlipConsumer.as_asgi()),
]
