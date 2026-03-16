"""
WebSocket consumer tests for the chess app.

Uses channels.testing.WebsocketCommunicator with Django's TransactionTestCase
(not TestCase) so that database state created in setUp is visible to the
database_sync_to_async thread pool that the consumer uses.

IMPORTANT: Never make synchronous ORM calls (refresh_from_db, queryset access)
inside the async `run()` function. All DB assertions must happen *after*
async_to_sync(run)() returns, from the regular test method body.
"""
from asgiref.sync import async_to_sync
from channels.layers import channel_layers
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.chess.models import ChessGame
from apps.chess.routing import websocket_urlpatterns

TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# FEN after 1.e4 — it is black's turn, meaning white just moved.
# Used in tests that need a game state where white can report game-over.
FEN_AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


def _make_app():
    return URLRouter(websocket_urlpatterns)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerConnectionTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.game = ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
        comm.scope['user'] = user
        return comm

    def test_creator_connects_receives_game_state(self):
        received = []

        async def run():
            comm = self._comm(self.alice)
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            received.append(await comm.receive_json_from())
            await comm.disconnect()

        async_to_sync(run)()
        self.assertEqual(received[0]['type'], 'game_state')
        self.assertEqual(received[0]['status'], 'pending')

    def test_opponent_connect_activates_game(self):
        creator_msgs = []
        opponent_msgs = []

        async def run():
            creator_comm = self._comm(self.alice)
            opponent_comm = self._comm(self.bob)

            # Creator connects to pending game — receives game_state(pending)
            connected, _ = await creator_comm.connect()
            self.assertTrue(connected)
            creator_msgs.append(await creator_comm.receive_json_from())

            # Opponent connects — triggers activation via group_send(game_activated)
            # Both creator and opponent receive game_state(active)
            connected, _ = await opponent_comm.connect()
            self.assertTrue(connected)

            creator_msgs.append(await creator_comm.receive_json_from())
            opponent_msgs.append(await opponent_comm.receive_json_from())

            await creator_comm.disconnect()
            # Drain player_disconnected that arrives for opponent
            await opponent_comm.receive_json_from()
            await opponent_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(creator_msgs[0]['status'], 'pending')
        self.assertEqual(creator_msgs[1]['type'], 'game_state')
        self.assertEqual(creator_msgs[1]['status'], 'active')
        self.assertEqual(opponent_msgs[0]['type'], 'game_state')
        self.assertEqual(opponent_msgs[0]['status'], 'active')

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'active')

    def test_non_participant_connection_closed(self):
        eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')

        async def run():
            app = _make_app()
            comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
            comm.scope['user'] = eve
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        async_to_sync(run)()


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerMoveTest(TransactionTestCase):
    """Tests for handle_move — requires an already-active game."""

    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        # Active game: alice = white, bob = black
        self.game = ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
            status='active',
            white_player=self.alice,
            black_player=self.bob,
            started_at=timezone.now(),
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_active(self, comm):
        """Connect to an active game and drain the game_state + player_connected messages."""
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # game_state (direct send)
        await comm.receive_json_from()  # player_connected (group send, self included)

    def test_valid_move_broadcasts_to_both(self):
        move_msgs = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            # White also receives player_connected(bob) when black joins
            await white_comm.receive_json_from()

            await white_comm.send_json_to({'action': 'move', 'move': 'e2e4'})

            move_msgs.append(await white_comm.receive_json_from())
            move_msgs.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(move_msgs[0]['type'], 'chess_move')
        self.assertEqual(move_msgs[0]['move'], 'e2e4')
        self.assertIn('fen', move_msgs[0])
        self.assertEqual(move_msgs[1]['type'], 'chess_move')
        self.assertEqual(move_msgs[1]['move'], 'e2e4')

    def test_illegal_move_produces_no_response(self):
        async def run():
            white_comm = self._comm(self.alice)
            await self._connect_active(white_comm)

            # e2e5 is parseable UCI but not a legal pawn move
            await white_comm.send_json_to({'action': 'move', 'move': 'e2e5'})
            self.assertTrue(await white_comm.receive_nothing())

            await white_comm.disconnect()

        async_to_sync(run)()

    def test_wrong_turn_produces_no_response(self):
        async def run():
            black_comm = self._comm(self.bob)
            await self._connect_active(black_comm)

            # Black tries to move on white's turn
            await black_comm.send_json_to({'action': 'move', 'move': 'e7e5'})
            self.assertTrue(await black_comm.receive_nothing())

            await black_comm.disconnect()

        async_to_sync(run)()

    def test_valid_move_updates_db_fen(self):
        async def run():
            white_comm = self._comm(self.alice)
            await self._connect_active(white_comm)

            await white_comm.send_json_to({'action': 'move', 'move': 'e2e4'})
            await white_comm.receive_json_from()  # chess_move (drain)

            await white_comm.disconnect()

        async_to_sync(run)()

        self.game.refresh_from_db()
        self.assertIn('e2e4', self.game.moves_uci)
        self.assertNotEqual(self.game.fen, STARTING_FEN)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerResignTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.game = ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
            status='active',
            white_player=self.alice,
            black_player=self.bob,
            started_at=timezone.now(),
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_active(self, comm):
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # game_state
        await comm.receive_json_from()  # player_connected (self)

    def test_resign_broadcasts_game_over_and_transfers_coins(self):
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            await white_comm.send_json_to({'action': 'resign'})

            captured.append(await white_comm.receive_json_from())  # chess_game_over
            captured.append(await black_comm.receive_json_from())  # chess_game_over

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        white_msg = captured[0]
        self.assertEqual(white_msg['type'], 'chess_game_over')
        self.assertEqual(white_msg['reason'], 'resign')
        self.assertEqual(white_msg['winner'], 'bob')
        self.assertEqual(captured[1]['type'], 'chess_game_over')

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'completed')
        self.assertEqual(self.game.end_reason, 'resign')
        self.assertEqual(self.game.winner_id, self.bob.pk)

        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 100)   # paid 100 stake
        self.assertEqual(self.bob.profile.balance, 300)    # received 100 stake


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerTimeoutTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        self.game = ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
            status='active',
            white_player=self.alice,
            black_player=self.bob,
            started_at=timezone.now(),
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_active(self, comm):
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # game_state
        await comm.receive_json_from()  # player_connected (self)

    def test_self_reported_timeout_ends_game(self):
        """White reports their own timeout — white loses, black wins."""
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            await white_comm.send_json_to({'action': 'timeout'})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'chess_game_over')
        self.assertEqual(captured[0]['reason'], 'timeout')
        self.assertEqual(captured[0]['winner'], 'bob')
        self.assertEqual(captured[1]['type'], 'chess_game_over')

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'completed')
        self.assertEqual(self.game.winner_id, self.bob.pk)

    def test_reporting_player_is_always_the_loser(self):
        """
        The server ignores any 'player' field in the timeout message and
        always treats the *reporter* as the timed-out player.
        Black reports timeout → black loses, white wins.
        """
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            # Black reports timeout — server derives black as the loser
            await black_comm.send_json_to({'action': 'timeout'})

            captured.append(await black_comm.receive_json_from())
            captured.append(await white_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'chess_game_over')
        self.assertEqual(captured[0]['reason'], 'timeout')
        self.assertEqual(captured[0]['winner'], 'alice')
        self.assertEqual(captured[1]['winner'], 'alice')

        self.game.refresh_from_db()
        self.assertEqual(self.game.winner_id, self.alice.pk)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerGameOverTest(TransactionTestCase):
    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()

    def _make_active_game(self, fen=STARTING_FEN):
        return ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
            status='active',
            white_player=self.alice,
            black_player=self.bob,
            fen=fen,
            started_at=timezone.now(),
        )

    def _comm(self, user, game):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{game.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_active(self, comm):
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # game_state
        await comm.receive_json_from()  # player_connected (self)

    def test_checkmate_reported_by_moving_player(self):
        """
        FEN_AFTER_E4 has black to move, so white just moved.
        White is allowed to report game_over → white wins.
        """
        game = self._make_active_game(fen=FEN_AFTER_E4)
        captured = []

        async def run():
            white_comm = self._comm(self.alice, game)
            black_comm = self._comm(self.bob, game)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            await white_comm.send_json_to({'action': 'game_over', 'reason': 'checkmate'})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'chess_game_over')
        self.assertEqual(captured[0]['reason'], 'checkmate')
        self.assertEqual(captured[0]['winner'], 'alice')
        self.assertEqual(captured[1]['winner'], 'alice')

        game.refresh_from_db()
        self.assertEqual(game.status, 'completed')
        self.assertEqual(game.winner_id, self.alice.pk)

    def test_game_over_rejected_for_wrong_player(self):
        """
        FEN_AFTER_E4 has black to move (white just moved).
        Black tries to report checkmate → rejected (only the mover may report).
        """
        game = self._make_active_game(fen=FEN_AFTER_E4)

        async def run():
            black_comm = self._comm(self.bob, game)
            await self._connect_active(black_comm)

            await black_comm.send_json_to({'action': 'game_over', 'reason': 'checkmate'})

            self.assertTrue(await black_comm.receive_nothing())

            await black_comm.disconnect()

        async_to_sync(run)()

        game.refresh_from_db()
        self.assertEqual(game.status, 'active')

    def test_stalemate_ends_game_with_no_coin_transfer(self):
        """Stalemate: game ends, no winner, balances unchanged."""
        game = self._make_active_game(fen=FEN_AFTER_E4)
        captured = []

        async def run():
            white_comm = self._comm(self.alice, game)
            black_comm = self._comm(self.bob, game)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            await white_comm.send_json_to({'action': 'game_over', 'reason': 'stalemate'})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'chess_game_over')
        self.assertEqual(captured[0]['reason'], 'stalemate')
        self.assertIsNone(captured[0]['winner'])
        self.assertIsNone(captured[1]['winner'])

        game.refresh_from_db()
        self.assertEqual(game.status, 'completed')
        self.assertIsNone(game.winner)

        # Balances must be unchanged — no coin transfer for draws
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 200)
        self.assertEqual(self.bob.profile.balance, 200)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ChessConsumerDrawTest(TransactionTestCase):
    """Tests for draw offer/accept/decline via WebSocket."""

    def setUp(self):
        channel_layers.backends = {}
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()
        # Active game: alice = white (to move), bob = black
        self.game = ChessGame.objects.create(
            creator=self.alice,
            opponent=self.bob,
            stake=100,
            creator_side='white',
            status='active',
            white_player=self.alice,
            black_player=self.bob,
            started_at=timezone.now(),
        )

    def _comm(self, user):
        app = _make_app()
        comm = WebsocketCommunicator(app, f'/ws/chess/{self.game.pk}/')
        comm.scope['user'] = user
        return comm

    async def _connect_active(self, comm):
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from()  # game_state
        await comm.receive_json_from()  # player_connected (self)

    def test_draw_offer_broadcasts_to_both(self):
        """White offers draw — both players receive draw_offered."""
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            await white_comm.send_json_to({'action': 'offer_draw'})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'draw_offered')
        self.assertEqual(captured[0]['from_player'], 'alice')
        self.assertEqual(captured[1]['type'], 'draw_offered')
        self.assertEqual(captured[1]['from_player'], 'alice')

        # Game should still be active
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'active')

    def test_draw_accepted_ends_game_no_transfer(self):
        """White offers draw, black accepts — game ends as draw, no coins transferred."""
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            # White offers draw
            await white_comm.send_json_to({'action': 'offer_draw'})
            await white_comm.receive_json_from()  # draw_offered
            await black_comm.receive_json_from()  # draw_offered

            # Black accepts
            await black_comm.send_json_to({'action': 'respond_draw', 'accept': True})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'chess_game_over')
        self.assertEqual(captured[0]['reason'], 'draw')
        self.assertIsNone(captured[0]['winner'])
        self.assertEqual(captured[1]['type'], 'chess_game_over')
        self.assertIsNone(captured[1]['winner'])

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'completed')
        self.assertEqual(self.game.end_reason, 'draw')
        self.assertIsNone(self.game.winner)

        # Balances unchanged — no coin transfer for draws
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.balance, 200)
        self.assertEqual(self.bob.profile.balance, 200)

    def test_draw_declined_broadcasts_to_both(self):
        """White offers draw, black declines — both get draw_declined, game continues."""
        captured = []

        async def run():
            white_comm = self._comm(self.alice)
            black_comm = self._comm(self.bob)

            await self._connect_active(white_comm)
            await self._connect_active(black_comm)
            await white_comm.receive_json_from()  # player_connected(bob)

            # White offers draw
            await white_comm.send_json_to({'action': 'offer_draw'})
            await white_comm.receive_json_from()  # draw_offered
            await black_comm.receive_json_from()  # draw_offered

            # Black declines
            await black_comm.send_json_to({'action': 'respond_draw', 'accept': False})

            captured.append(await white_comm.receive_json_from())
            captured.append(await black_comm.receive_json_from())

            await white_comm.disconnect()
            await black_comm.disconnect()

        async_to_sync(run)()

        self.assertEqual(captured[0]['type'], 'draw_declined')
        self.assertEqual(captured[0]['from_player'], 'bob')
        self.assertEqual(captured[1]['type'], 'draw_declined')

        # Game must still be active
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'active')

    def test_draw_offer_rejected_when_not_your_turn(self):
        """Black tries to offer draw on white's turn — rejected silently."""
        async def run():
            black_comm = self._comm(self.bob)
            await self._connect_active(black_comm)

            await black_comm.send_json_to({'action': 'offer_draw'})
            self.assertTrue(await black_comm.receive_nothing())

            await black_comm.disconnect()

        async_to_sync(run)()

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'active')
