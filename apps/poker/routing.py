from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/poker/(?P<table_id>\d+)/$', consumers.PokerConsumer.as_asgi()),
]
