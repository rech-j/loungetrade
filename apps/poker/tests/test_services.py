from django.contrib.auth.models import User
from django.test import TestCase

from apps.poker.models import PokerHand, PokerPlayer, PokerTable
from apps.poker.services import (
    advance_round,
    calculate_payouts,
    get_valid_actions,
    process_action,
    resolve_hand,
    start_hand,
)


class StartHandTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

    def test_start_hand_deals_cards(self):
        hand, card_map = start_hand(self.table.pk)
        self.assertIsNotNone(hand)
        self.assertEqual(hand.hand_number, 1)
        self.assertEqual(len(card_map), 3)
        # Each player should have 2 cards
        for uid, csv in card_map.items():
            cards = csv.split(',')
            self.assertEqual(len(cards), 2)

    def test_start_hand_posts_blinds(self):
        hand, _ = start_hand(self.table.pk)
        self.assertEqual(hand.pot, 30)  # 10 + 20
        self.assertEqual(hand.current_bet, 20)

    def test_start_hand_increments_hand_number(self):
        start_hand(self.table.pk)
        hand2, _ = start_hand(self.table.pk)
        self.assertEqual(hand2.hand_number, 2)


class ProcessActionTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

        self.hand, self.card_map = start_hand(self.table.pk)

    def test_fold(self):
        # Get current player
        current_player = PokerPlayer.objects.get(table=self.table, seat=self.hand.current_seat)
        hand, action, info = process_action(
            self.hand.pk, current_player.user_id, 'fold'
        )
        self.assertEqual(action, 'fold')
        current_player.refresh_from_db()
        self.assertEqual(current_player.status, 'folded')

    def test_call(self):
        current_player = PokerPlayer.objects.get(table=self.table, seat=self.hand.current_seat)
        hand, action, info = process_action(
            self.hand.pk, current_player.user_id, 'call', 20
        )
        self.assertEqual(action, 'call')

    def test_invalid_action_wrong_seat(self):
        # Try to act from a different player
        wrong_player = PokerPlayer.objects.filter(table=self.table).exclude(
            seat=self.hand.current_seat
        ).first()
        hand, action, info = process_action(
            self.hand.pk, wrong_player.user_id, 'fold'
        )
        self.assertIsNone(action)


class GetValidActionsTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

        self.hand, _ = start_hand(self.table.pk)

    def test_utg_can_fold_call_raise(self):
        current_player = PokerPlayer.objects.get(table=self.table, seat=self.hand.current_seat)
        actions = get_valid_actions(self.hand, current_player)
        action_names = {a['action'] for a in actions}
        self.assertIn('fold', action_names)
        self.assertIn('call', action_names)
        self.assertIn('raise', action_names)

    def test_wrong_seat_no_actions(self):
        wrong_player = PokerPlayer.objects.filter(table=self.table).exclude(
            seat=self.hand.current_seat
        ).first()
        actions = get_valid_actions(self.hand, wrong_player)
        self.assertEqual(actions, [])


class AdvanceRoundTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

        self.hand, _ = start_hand(self.table.pk)

    def test_advance_to_flop(self):
        hand, new_cards = advance_round(self.hand.pk)
        self.assertEqual(hand.status, 'flop')
        cards = new_cards.split(',')
        self.assertEqual(len(cards), 3)

    def test_advance_flop_to_turn(self):
        advance_round(self.hand.pk)  # flop
        hand, new_cards = advance_round(self.hand.pk)
        self.assertEqual(hand.status, 'turn')
        cards = new_cards.split(',')
        self.assertEqual(len(cards), 1)


class ResolveHandTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

    def test_resolve_single_winner(self):
        hand, _ = start_hand(self.table.pk)
        # Fold all but one
        players = list(PokerPlayer.objects.filter(table=self.table).order_by('seat'))
        for p in players[1:]:
            p.status = 'folded'
            p.save()

        hand, results = resolve_hand(hand.pk)
        self.assertEqual(hand.status, 'completed')
        self.assertEqual(len([r for r in results if r['winnings'] > 0]), 1)

    def test_resolve_with_community(self):
        hand, _ = start_hand(self.table.pk)
        # Deal all community cards
        advance_round(hand.pk)  # flop
        advance_round(hand.pk)  # turn
        advance_round(hand.pk)  # river

        hand, results = resolve_hand(hand.pk)
        self.assertEqual(hand.status, 'completed')
        self.assertTrue(len(results) >= 2)
        total_winnings = sum(r['winnings'] for r in results)
        self.assertEqual(total_winnings, hand.pot)


class CalculatePayoutsTest(TestCase):
    def test_proportional_payout(self):
        users = []
        for i in range(3):
            u = User.objects.create_user(f'player{i}', password='pass')
            users.append(u)

        table = PokerTable.objects.create(creator=users[0], stake=100)
        for i, u in enumerate(users):
            PokerPlayer.objects.create(
                table=table, user=u, seat=i,
                chips=1000 if i == 0 else 500 if i == 1 else 0,
                status='active' if i < 2 else 'eliminated',
                coins_invested=100,
            )

        payouts = calculate_payouts(table.pk)
        total = sum(amount for _, amount in payouts)
        self.assertEqual(total, 300)  # 3 * 100 LC invested

    def test_pot_refunded_before_payout(self):
        """When a hand is in progress, pot chips are refunded to stacks
        before calculating proportional payouts."""
        users = []
        for i in range(3):
            u = User.objects.create_user(f'payout_refund{i}', password='pass')
            users.append(u)

        table = PokerTable.objects.create(
            creator=users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        table.status = 'active'
        table.save()

        for i, u in enumerate(users):
            PokerPlayer.objects.create(
                table=table, user=u, seat=i, chips=1000,
                status='active', coins_invested=100,
            )

        # Start a hand (posts blinds, deducting from stacks into pot)
        hand, _ = start_hand(table.pk)
        pot_before = hand.pot  # should be 30 (10 SB + 20 BB)
        self.assertEqual(pot_before, 30)

        # Chips in stacks are now 1000+990+980 = 2970, but total should be 3000
        players = list(PokerPlayer.objects.filter(table=table).order_by('seat'))
        stack_total = sum(p.chips for p in players)
        self.assertEqual(stack_total, 2970)

        # Calculate payouts — should refund pot first, so total LC = 300
        payouts = calculate_payouts(table.pk)
        total = sum(amount for _, amount in payouts)
        self.assertEqual(total, 300)

        # Verify stacks were restored (pot refunded back)
        players = list(PokerPlayer.objects.filter(table=table).order_by('seat'))
        stack_total_after = sum(p.chips for p in players)
        self.assertEqual(stack_total_after, 3000)


class StartHandZeroChipsTest(TestCase):
    """Players with 0 chips should be excluded from new hands."""

    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'zero_chips{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            chips = 0 if i == 2 else 1000
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=chips, status='active',
            )

    def test_zero_chip_player_excluded(self):
        hand, card_map = start_hand(self.table.pk)
        self.assertIsNotNone(hand)
        # Only 2 players should be dealt cards
        self.assertEqual(len(card_map), 2)
        # The 0-chip player should not have cards
        self.assertNotIn(str(self.users[2].pk), card_map)

    def test_zero_chip_player_set_to_folded(self):
        start_hand(self.table.pk)
        zero_player = PokerPlayer.objects.get(table=self.table, user=self.users[2])
        self.assertEqual(zero_player.status, 'folded')
        self.assertEqual(zero_player.chips, 0)


class ActedTrackingTest(TestCase):
    """The _acted list in round_bets tracks explicit actions, not blind posts."""

    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'acted{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )

        self.hand, _ = start_hand(self.table.pk)

    def test_blinds_not_in_acted(self):
        """Blind posting should not count as having acted."""
        acted = self.hand.round_bets.get('_acted', [])
        self.assertEqual(acted, [])

    def test_action_added_to_acted(self):
        """An explicit action should add the player to _acted."""
        current_player = PokerPlayer.objects.get(
            table=self.table, seat=self.hand.current_seat,
        )
        hand, action, _ = process_action(
            self.hand.pk, current_player.user_id, 'call', 20,
        )
        self.assertIn(str(current_player.user_id), hand.round_bets['_acted'])
