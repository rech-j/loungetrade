import json
import random

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.economy.services import game_transfer
from apps.notifications.models import Notification

from .models import GameChallenge


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.challenge_id = self.scope['url_route']['kwargs']['challenge_id']
        self.room_group_name = f'game_{self.challenge_id}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        challenge = await self.get_challenge()
        if not challenge:
            await self.close()
            return

        if self.user.pk not in (challenge.challenger_id, challenge.opponent_id):
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_joined',
                'username': self.user.username,
            }
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'accept':
            await self.handle_accept()
        elif action == 'decline':
            await self.handle_decline()

    async def handle_accept(self):
        challenge = await self.get_challenge()
        if not challenge or challenge.status != 'pending':
            return
        if self.user.pk != challenge.opponent_id:
            return

        flip_result = random.choice(['heads', 'tails'])
        challenger_choice = challenge.challenger_choice
        winner_id = (
            challenge.challenger_id
            if flip_result == challenger_choice
            else challenge.opponent_id
        )
        loser_id = (
            challenge.opponent_id
            if winner_id == challenge.challenger_id
            else challenge.challenger_id
        )

        await self.resolve_game(challenge.pk, flip_result, winner_id)
        await self.do_game_transfer(winner_id, loser_id, challenge.stake)
        await self.create_game_notifications(challenge, winner_id, loser_id, flip_result)

        winner_username = await self.get_username(winner_id)
        loser_username = await self.get_username(loser_id)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_result',
                'flip_result': flip_result,
                'challenger_choice': challenger_choice,
                'winner': winner_username,
                'loser': loser_username,
                'stake': challenge.stake,
            }
        )

    async def handle_decline(self):
        challenge = await self.get_challenge()
        if not challenge or challenge.status != 'pending':
            return
        if self.user.pk != challenge.opponent_id:
            return

        await self.decline_game(challenge.pk)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_declined',
                'username': self.user.username,
            }
        )

    async def player_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_joined',
            'username': event['username'],
        }))

    async def game_result(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_result',
            'flip_result': event['flip_result'],
            'challenger_choice': event['challenger_choice'],
            'winner': event['winner'],
            'loser': event['loser'],
            'stake': event['stake'],
        }))

    async def game_declined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_declined',
            'username': event['username'],
        }))

    @database_sync_to_async
    def get_challenge(self):
        try:
            return GameChallenge.objects.get(pk=self.challenge_id)
        except GameChallenge.DoesNotExist:
            return None

    @database_sync_to_async
    def resolve_game(self, challenge_id, flip_result, winner_id):
        GameChallenge.objects.filter(pk=challenge_id).update(
            status='completed',
            flip_result=flip_result,
            winner_id=winner_id,
            resolved_at=timezone.now(),
        )

    @database_sync_to_async
    def decline_game(self, challenge_id):
        GameChallenge.objects.filter(pk=challenge_id).update(status='declined')

    @database_sync_to_async
    def do_game_transfer(self, winner_id, loser_id, stake):
        from django.contrib.auth.models import User
        winner = User.objects.get(pk=winner_id)
        loser = User.objects.get(pk=loser_id)
        game_transfer(winner, loser, stake)

    @database_sync_to_async
    def get_username(self, user_id):
        from django.contrib.auth.models import User
        return User.objects.get(pk=user_id).username

    @database_sync_to_async
    def create_game_notifications(self, challenge, winner_id, loser_id, flip_result):
        from django.contrib.auth.models import User
        winner = User.objects.get(pk=winner_id)
        loser = User.objects.get(pk=loser_id)
        Notification.objects.create(
            user=winner,
            notif_type='game_result',
            title='You Won!',
            message=f'You won {challenge.stake} coins against {loser.profile.get_display_name()}! The coin landed on {flip_result}.',
            link='/games/',
        )
        Notification.objects.create(
            user=loser,
            notif_type='game_result',
            title='You Lost',
            message=f'You lost {challenge.stake} coins to {winner.profile.get_display_name()}. The coin landed on {flip_result}.',
            link='/games/',
        )
