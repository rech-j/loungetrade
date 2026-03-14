"""
WebSocket consumer tests for the coinflip app.

Uses channels.testing.WebsocketCommunicator with TransactionTestCase so that
setUp data is visible to the database_sync_to_async thread pool.

IMPORTANT: Never make synchronous ORM calls inside the async `run()` function.
All DB assertions must happen *after* async_to_sync(run)() returns.
"""
from asgiref.sync import async_to_sync
from channels.layers import channel_layers
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings

from apps.coinflip.models import CoinFlipChallenge
from apps.coinflip.routing import websocket_urlpatterns

TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}


def _make_app():
    return URLRouter(websocket_urlpatterns)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class CoinFlipConsumerConnectionTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=100,
            challenger_choice='heads',
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/coinflip/{self.challenge.pk}/')
        comm.scope['user'] = user
        return comm

    def test_participants_can_connect(self):
        async def run():
            challenger_comm = self._comm(self.alice)
            opponent_comm = self._comm(self.bob)

            connected_c, _ = await challenger_comm.connect()
            self.assertTrue(connected_c)
            await challenger_comm.receive_json_from()  # player_joined(alice)

            connected_o, _ = await opponent_comm.connect()
            self.assertTrue(connected_o)
            await opponent_comm.receive_json_from()    # player_joined(bob)
            await challenger_comm.receive_json_from()  # player_joined(bob)

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

    def test_non_participant_connection_closed(self):
        eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')

        async def run():
            app = _make_app()
            comm = WebsocketCommunicator(app, f'/ws/coinflip/{self.challenge.pk}/')
            comm.scope['user'] = eve
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        async_to_sync(run)()


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class CoinFlipConsumerAcceptTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=100,
            challenger_choice='heads',
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/coinflip/{self.challenge.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_both(self):
        """Connect both players and drain connection messages."""
        challenger_comm = self._comm(self.alice)
        opponent_comm = self._comm(self.bob)

        await challenger_comm.connect()
        await challenger_comm.receive_json_from()  # player_joined(alice)

        await opponent_comm.connect()
        await opponent_comm.receive_json_from()    # player_joined(bob)
        await challenger_comm.receive_json_from()  # player_joined(bob)

        return challenger_comm, opponent_comm

    def test_opponent_accept_broadcasts_game_result(self):
        captured = []

        async def run():
            challenger_comm, opponent_comm = await self._connect_both()

            await opponent_comm.send_json_to({'action': 'accept'})

            captured.append(await challenger_comm.receive_json_from())
            captured.append(await opponent_comm.receive_json_from())

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'game_result')
        self.assertIn('flip_result', captured[0])
        self.assertIn(captured[0]['flip_result'], ('heads', 'tails'))
        self.assertIn('winner', captured[0])
        self.assertEqual(captured[0]['stake'], 100)
        self.assertEqual(captured[1]['type'], 'game_result')

    def test_accept_updates_balances(self):
        async def run():
            challenger_comm, opponent_comm = await self._connect_both()

            await opponent_comm.send_json_to({'action': 'accept'})
            await challenger_comm.receive_json_from()  # game_result (drain)
            await opponent_comm.receive_json_from()    # game_result (drain)

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        # Exactly one player wins 100 from the other; total must be 400
        total = self.alice.profile.balance + self.bob.profile.balance
        self.assertEqual(total, 400)
        self.assertIn(self.alice.profile.balance, (100, 300))
        self.assertIn(self.bob.profile.balance, (100, 300))

    def test_accept_sets_challenge_completed(self):
        async def run():
            challenger_comm, opponent_comm = await self._connect_both()

            await opponent_comm.send_json_to({'action': 'accept'})
            await challenger_comm.receive_json_from()  # game_result (drain)
            await opponent_comm.receive_json_from()    # game_result (drain)

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'completed')


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class CoinFlipConsumerDeclineTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=100,
            challenger_choice='heads',
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/coinflip/{self.challenge.pk}/')
        comm.scope['user'] = user
        return comm

    def test_opponent_decline_broadcasts_game_declined(self):
        captured = []

        async def run():
            challenger_comm = self._comm(self.alice)
            opponent_comm = self._comm(self.bob)

            await challenger_comm.connect()
            await challenger_comm.receive_json_from()  # player_joined(alice)
            await opponent_comm.connect()
            await opponent_comm.receive_json_from()    # player_joined(bob)
            await challenger_comm.receive_json_from()  # player_joined(bob)

            await opponent_comm.send_json_to({'action': 'decline'})

            captured.append(await challenger_comm.receive_json_from())
            captured.append(await opponent_comm.receive_json_from())

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'game_declined')
        self.assertEqual(captured[1]['type'], 'game_declined')

        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'declined')


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class CoinFlipConsumerSecurityTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.challenge = CoinFlipChallenge.objects.create(
            challenger=self.alice,
            opponent=self.bob,
            stake=100,
            challenger_choice='heads',
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/coinflip/{self.challenge.pk}/')
        comm.scope['user'] = user
        return comm

    def test_challenger_cannot_accept(self):
        """Only the opponent may accept. Challenger's accept is silently ignored."""
        async def run():
            challenger_comm = self._comm(self.alice)

            await challenger_comm.connect()
            await challenger_comm.receive_json_from()  # player_joined(alice)

            await challenger_comm.send_json_to({'action': 'accept'})

            # No game_result or game_error should be sent
            self.assertTrue(await challenger_comm.receive_nothing())

            await challenger_comm.disconnect()

        async_to_sync(run)()

        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'pending')

    def test_insufficient_funds_cancels_game(self):
        """If the loser cannot pay, the game is cancelled and game_error is broadcast."""
        # Drain both balances so game_transfer will always fail
        self.alice.profile.balance = 0
        self.alice.profile.save()
        self.bob.profile.balance = 0
        self.bob.profile.save()
        captured = []

        async def run():
            challenger_comm = self._comm(self.alice)
            opponent_comm = self._comm(self.bob)

            await challenger_comm.connect()
            await challenger_comm.receive_json_from()  # player_joined(alice)
            await opponent_comm.connect()
            await opponent_comm.receive_json_from()    # player_joined(bob)
            await challenger_comm.receive_json_from()  # player_joined(bob)

            await opponent_comm.send_json_to({'action': 'accept'})

            captured.append(await challenger_comm.receive_json_from())
            captured.append(await opponent_comm.receive_json_from())

            await challenger_comm.disconnect()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'game_error')
        self.assertEqual(captured[1]['type'], 'game_error')

        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, 'cancelled')
