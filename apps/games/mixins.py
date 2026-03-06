"""Shared base consumer for all stake-based games.

Provides common WebSocket patterns: authentication, channel-layer group
management, coin transfers, username lookups, and error broadcasting.
Individual game consumers inherit from ``BaseGameConsumer`` and add their
own game-specific logic.
"""

import json
import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.economy.services import game_transfer

logger = logging.getLogger(__name__)


class BaseGameConsumer(AsyncWebsocketConsumer):
    """Abstract base for all game WebSocket consumers.

    Subclasses must set ``game_type`` (e.g. ``'coinflip'``, ``'chess'``)
    and implement ``connect``, ``disconnect``, and ``receive``.

    Provides shared helpers:
    * ``do_game_transfer`` - atomic coin transfer between winner/loser
    * ``get_username`` - look up a username by PK
    * ``broadcast_error`` - send an error to the room group
    * ``is_throttled`` - per-connection message rate limiting
    """

    game_type: str = ''
    db_async = staticmethod(database_sync_to_async)
    MESSAGE_COOLDOWN = 0.15  # minimum seconds between messages

    def is_throttled(self):
        """Return True if the message should be dropped (too frequent)."""
        now = time.monotonic()
        last = getattr(self, '_last_msg_time', 0)
        if now - last < self.MESSAGE_COOLDOWN:
            return True
        self._last_msg_time = now
        return False

    # ── Shared database helpers ──────────────────────────────────────────

    @database_sync_to_async
    def do_game_transfer(self, winner_id, loser_id, stake, note='Game'):
        from django.contrib.auth.models import User
        winner = User.objects.get(pk=winner_id)
        loser = User.objects.get(pk=loser_id)
        game_transfer(winner, loser, stake, note=note)

    @database_sync_to_async
    def get_username(self, user_id):
        from django.contrib.auth.models import User
        return User.objects.get(pk=user_id).username

    # ── Shared broadcast helpers ─────────────────────────────────────────

    async def broadcast_error(self, message):
        """Send an error event to the room group."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_error',
                'message': message,
            }
        )
