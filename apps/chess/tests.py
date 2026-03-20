from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from apps.chess.models import ChessGame
from apps.notifications.models import Notification


class ChessLobbyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass1234')

    def test_lobby_requires_login(self):
        response = self.client.get('/chess/')
        self.assertEqual(response.status_code, 302)

    def test_lobby_accessible_when_logged_in(self):
        self.client.login(username='testuser', password='pass1234')
        response = self.client.get('/chess/')
        self.assertEqual(response.status_code, 200)


class ChessLiveGamesViewTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()

    def test_live_requires_login(self):
        response = self.client.get('/chess/live/')
        self.assertEqual(response.status_code, 302)

    def test_live_returns_200(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/live/')
        self.assertEqual(response.status_code, 200)

    def test_live_shows_active_games(self):
        game = ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50,
            white_player=self.alice, black_player=self.bob,
            status='active', started_at=timezone.now(),
        )
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/live/')
        self.assertIn(game, response.context['games'])

    def test_live_excludes_pending_and_completed(self):
        ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50, status='pending',
        )
        ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50,
            white_player=self.alice, black_player=self.bob,
            status='completed', winner=self.alice, end_reason='checkmate',
            ended_at=timezone.now(),
        )
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/live/')
        self.assertEqual(len(response.context['games']), 0)


class CreateChessGameTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 200
        self.alice.profile.save()
        self.bob.profile.balance = 200
        self.bob.profile.save()

    def _post(self, **kwargs):
        defaults = {'opponent_username': 'bob', 'stake': 50, 'side': 'white', 'time_control': 600}
        defaults.update(kwargs)
        return self.client.post('/chess/challenge/', defaults)

    def test_create_game_success(self):
        self.client.login(username='alice', password='pass1234')
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChessGame.objects.filter(creator=self.alice, opponent=self.bob).exists())

    def test_create_game_sends_notification(self):
        self.client.login(username='alice', password='pass1234')
        self._post()
        self.assertEqual(
            Notification.objects.filter(user=self.bob, notif_type='game_invite').count(), 1
        )

    def test_cannot_challenge_self(self):
        self.client.login(username='alice', password='pass1234')
        self._post(opponent_username='alice')
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_insufficient_balance(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=500)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_duplicate_pending_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post()
        self._post()
        self.assertEqual(ChessGame.objects.count(), 1)

    def test_zero_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=0)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_negative_stake_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=-100)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_stake_above_max_rejected(self):
        self.client.login(username='alice', password='pass1234')
        self._post(stake=99999)
        self.assertEqual(ChessGame.objects.count(), 0)

    def test_time_control_stored(self):
        self.client.login(username='alice', password='pass1234')
        self._post(time_control=180)
        game = ChessGame.objects.get()
        self.assertEqual(game.time_control, 180)

    def test_invalid_time_control_defaults(self):
        self.client.login(username='alice', password='pass1234')
        self._post(time_control=999)
        game = ChessGame.objects.get()
        self.assertEqual(game.time_control, 600)

    def test_default_time_control(self):
        self.client.login(username='alice', password='pass1234')
        self._post()
        game = ChessGame.objects.get()
        self.assertEqual(game.time_control, 600)


class ChessPlayViewAccessTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_creator_can_access_play(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_opponent_can_access_play(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_non_participant_redirected_for_pending(self):
        self.client.login(username='eve', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)

    def test_non_participant_can_spectate_active(self):
        self.game.status = 'active'
        self.game.white_player = self.alice
        self.game.black_player = self.bob
        self.game.save()
        self.client.login(username='eve', password='pass1234')
        response = self.client.get(f'/chess/play/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_spectator'])


class DeclineChessGameTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_opponent_can_decline(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'cancelled')

    def test_creator_cannot_decline(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_non_participant_cannot_decline(self):
        self.client.login(username='eve', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_cannot_decline_non_pending(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/decline/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)


class CancelChessGameTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 100
        self.alice.profile.save()
        self.bob.profile.balance = 100
        self.bob.profile.save()
        self.game = ChessGame.objects.create(creator=self.alice, opponent=self.bob, stake=50)

    def test_creator_can_cancel(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'cancelled')

    def test_opponent_cannot_cancel(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_cannot_cancel_active_game(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/cancel/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)


class ChessArchiveViewTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.carol = User.objects.create_user('carol', 'carol@test.com', 'pass1234')
        self.alice.profile.balance = 500
        self.alice.profile.save()
        self.bob.profile.balance = 500
        self.bob.profile.save()
        self.carol.profile.balance = 500
        self.carol.profile.save()

        now = timezone.now()

        # Alice beat Bob (checkmate)
        self.game_win = ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50,
            white_player=self.alice, black_player=self.bob,
            status='completed', winner=self.alice, end_reason='checkmate',
            ended_at=now,
        )
        # Alice lost to Bob (resign)
        self.game_loss = ChessGame.objects.create(
            creator=self.bob, opponent=self.alice, stake=30,
            white_player=self.bob, black_player=self.alice,
            status='completed', winner=self.bob, end_reason='resign',
            ended_at=now,
        )
        # Alice drew with Carol
        self.game_draw = ChessGame.objects.create(
            creator=self.alice, opponent=self.carol, stake=20,
            white_player=self.alice, black_player=self.carol,
            status='completed', winner=None, end_reason='stalemate',
            ended_at=now,
        )
        # Bob beat Carol (not involving Alice)
        self.game_other = ChessGame.objects.create(
            creator=self.bob, opponent=self.carol, stake=10,
            white_player=self.bob, black_player=self.carol,
            status='completed', winner=self.bob, end_reason='checkmate',
            ended_at=now,
        )

    def test_archive_requires_login(self):
        response = self.client.get('/chess/archive/')
        self.assertEqual(response.status_code, 302)

    def test_archive_shows_own_games_only(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/')
        self.assertEqual(response.status_code, 200)
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertIn(self.game_win.pk, game_ids)
        self.assertIn(self.game_loss.pk, game_ids)
        self.assertIn(self.game_draw.pk, game_ids)
        self.assertNotIn(self.game_other.pk, game_ids)

    def test_filter_wins(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?result=wins')
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertEqual(game_ids, [self.game_win.pk])

    def test_filter_losses(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?result=losses')
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertEqual(game_ids, [self.game_loss.pk])

    def test_filter_draws(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?result=draws')
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertEqual(game_ids, [self.game_draw.pk])

    def test_filter_by_opponent(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?result=all&opponent=carol')
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertEqual(game_ids, [self.game_draw.pk])

    def test_opponent_search_case_insensitive(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?result=all&opponent=BOB')
        page = response.context['page']
        game_ids = [g.pk for g in page]
        self.assertIn(self.game_win.pk, game_ids)
        self.assertIn(self.game_loss.pk, game_ids)

    def test_empty_archive(self):
        eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.client.login(username='eve', password='pass1234')
        response = self.client.get('/chess/archive/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page'].paginator.count, 0)

    def test_pagination(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get('/chess/archive/?page=1')
        self.assertEqual(response.status_code, 200)
        # Invalid page defaults to page 1
        response = self.client.get('/chess/archive/?page=999')
        self.assertEqual(response.status_code, 200)


class ChessPGNExportTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.alice.profile.balance = 500
        self.alice.profile.save()
        self.bob.profile.balance = 500
        self.bob.profile.save()
        self.game = ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50,
            white_player=self.alice, black_player=self.bob,
            status='completed', winner=self.alice, end_reason='checkmate',
            moves_uci='e2e4 e7e5 d1h5 b8c6 f1c4 g8f6 h5f7',
            ended_at=timezone.now(),
        )

    def test_pgn_download(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.get(f'/chess/pgn/{self.game.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-chess-pgn')
        content = response.content.decode()
        self.assertIn('[White "alice"]', content)
        self.assertIn('[Black "bob"]', content)
        self.assertIn('[Result "1-0"]', content)
        self.assertIn('1. e4 e5', content)

    def test_pgn_requires_login(self):
        response = self.client.get(f'/chess/pgn/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)

    def test_pgn_404_for_non_completed(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='alice', password='pass1234')
        response = self.client.get(f'/chess/pgn/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)


class ChessRematchTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.alice = User.objects.create_user('alice', 'alice@test.com', 'pass1234')
        self.bob = User.objects.create_user('bob', 'bob@test.com', 'pass1234')
        self.eve = User.objects.create_user('eve', 'eve@test.com', 'pass1234')
        self.alice.profile.balance = 500
        self.alice.profile.save()
        self.bob.profile.balance = 500
        self.bob.profile.save()
        self.game = ChessGame.objects.create(
            creator=self.alice, opponent=self.bob, stake=50,
            white_player=self.alice, black_player=self.bob,
            status='completed', winner=self.alice, end_reason='checkmate',
            time_control=300,
            ended_at=timezone.now(),
        )

    def test_rematch_creates_new_game(self):
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        new_game = ChessGame.objects.filter(status='pending').first()
        self.assertIsNotNone(new_game)
        self.assertEqual(new_game.creator, self.alice)
        self.assertEqual(new_game.opponent, self.bob)
        self.assertEqual(new_game.stake, 50)
        self.assertEqual(new_game.time_control, 300)

    def test_rematch_sends_notification(self):
        self.client.login(username='alice', password='pass1234')
        self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(
            Notification.objects.filter(user=self.bob, notif_type='game_invite').count(), 1
        )

    def test_opponent_can_rematch(self):
        self.client.login(username='bob', password='pass1234')
        response = self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        new_game = ChessGame.objects.filter(status='pending').first()
        self.assertIsNotNone(new_game)
        self.assertEqual(new_game.creator, self.bob)
        self.assertEqual(new_game.opponent, self.alice)

    def test_non_participant_cannot_rematch(self):
        self.client.login(username='eve', password='pass1234')
        response = self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ChessGame.objects.filter(status='pending').count(), 0)

    def test_cannot_rematch_active_game(self):
        self.game.status = 'active'
        self.game.save()
        self.client.login(username='alice', password='pass1234')
        response = self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_insufficient_balance_rejected(self):
        self.alice.profile.balance = 10
        self.alice.profile.save()
        self.client.login(username='alice', password='pass1234')
        self.client.post(f'/chess/rematch/{self.game.pk}/')
        self.assertEqual(ChessGame.objects.filter(status='pending').count(), 0)
