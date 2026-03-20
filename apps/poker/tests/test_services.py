from django.contrib.auth.models import User
from django.test import TestCase

from apps.poker.models import PokerHand, PokerPlayer, PokerTable
from apps.poker.services import (
    advance_round,
    calculate_payouts,
    check_table_over,
    get_valid_actions,
    process_action,
    process_rebuy,
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


class ProcessActionExtendedTest(TestCase):
    """Additional process_action tests for raise, check, and all_in."""

    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'ext_action{i}', password='pass')
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

    def test_raise(self):
        current_player = PokerPlayer.objects.get(table=self.table, seat=self.hand.current_seat)
        hand, action, info = process_action(
            self.hand.pk, current_player.user_id, 'raise', 60
        )
        self.assertEqual(action, 'raise')
        current_player.refresh_from_db()
        self.assertLess(current_player.chips, 1000)

    def test_check_when_no_bet(self):
        """After advancing to flop with bets settled, check should work."""
        # Everyone calls preflop to get to flop
        for _ in range(3):
            hand = PokerHand.objects.get(pk=self.hand.pk)
            current_player = PokerPlayer.objects.get(
                table=self.table, seat=hand.current_seat,
            )
            hand, action, info = process_action(
                hand.pk, current_player.user_id, 'call', 20,
            )
            if info == 'advance_round':
                break

        if info == 'advance_round':
            hand, _ = advance_round(hand.pk)
            hand = PokerHand.objects.get(pk=hand.pk)
            current_player = PokerPlayer.objects.get(
                table=self.table, seat=hand.current_seat,
            )
            hand, action, result_info = process_action(
                hand.pk, current_player.user_id, 'check',
            )
            self.assertEqual(action, 'check')

    def test_all_in(self):
        # Give player minimal chips to force all-in
        current_player = PokerPlayer.objects.get(table=self.table, seat=self.hand.current_seat)
        current_player.chips = 15
        current_player.save(update_fields=['chips'])
        hand, action, info = process_action(
            self.hand.pk, current_player.user_id, 'all_in', 15,
        )
        self.assertEqual(action, 'all_in')
        current_player.refresh_from_db()
        self.assertEqual(current_player.chips, 0)
        self.assertEqual(current_player.status, 'all_in')


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

    def test_advance_turn_to_river(self):
        advance_round(self.hand.pk)  # flop
        advance_round(self.hand.pk)  # turn
        hand, new_cards = advance_round(self.hand.pk)
        self.assertEqual(hand.status, 'river')
        cards = new_cards.split(',')
        self.assertEqual(len(cards), 1)

    def test_advance_river_to_showdown(self):
        advance_round(self.hand.pk)  # flop
        advance_round(self.hand.pk)  # turn
        advance_round(self.hand.pk)  # river
        hand, new_cards = advance_round(self.hand.pk)
        self.assertEqual(hand.status, 'showdown')
        self.assertIsNone(new_cards)

    def test_community_cards_accumulate(self):
        advance_round(self.hand.pk)  # flop: 3 cards
        advance_round(self.hand.pk)  # turn: 4 cards
        hand, _ = advance_round(self.hand.pk)  # river: 5 cards
        community = hand.community_cards.split(',')
        self.assertEqual(len(community), 5)


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


class CheckTableOverTest(TestCase):
    def setUp(self):
        self.users = []
        for i in range(3):
            u = User.objects.create_user(f'table_over{i}', password='pass')
            self.users.append(u)

        self.table = PokerTable.objects.create(
            creator=self.users[0], stake=100, starting_chips=1000,
            small_blind=10, big_blind=20,
        )
        self.table.status = 'active'
        self.table.save()

    def test_table_not_over_with_multiple_players(self):
        for i, u in enumerate(self.users):
            PokerPlayer.objects.create(
                table=self.table, user=u, seat=i, chips=1000, status='active',
            )
        is_over, winner = check_table_over(self.table.pk)
        self.assertFalse(is_over)
        self.assertIsNone(winner)

    def test_table_over_with_one_player(self):
        PokerPlayer.objects.create(
            table=self.table, user=self.users[0], seat=0, chips=3000, status='active',
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.users[1], seat=1, chips=0, status='eliminated',
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.users[2], seat=2, chips=0, status='eliminated',
        )
        is_over, winner = check_table_over(self.table.pk)
        self.assertTrue(is_over)
        self.assertEqual(winner.user_id, self.users[0].pk)

    def test_zero_chips_player_eliminated_when_no_rebuys(self):
        PokerPlayer.objects.create(
            table=self.table, user=self.users[0], seat=0, chips=1500, status='active',
        )
        PokerPlayer.objects.create(
            table=self.table, user=self.users[1], seat=1, chips=0, status='active',
        )
        is_over, winner = check_table_over(self.table.pk)
        self.assertTrue(is_over)
        p1 = PokerPlayer.objects.get(table=self.table, user=self.users[1])
        self.assertEqual(p1.status, 'eliminated')


class ProcessRebuyTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('rebuy_user', password='pass')
        self.user.profile.balance = 500
        self.user.profile.save()
        self.table = PokerTable.objects.create(
            creator=self.user, stake=100, starting_chips=1000,
            allow_rebuys=True, max_rebuys=2,
        )
        self.table.status = 'active'
        self.table.save()
        self.player = PokerPlayer.objects.create(
            table=self.table, user=self.user, seat=0,
            chips=0, status='eliminated', coins_invested=100,
        )

    def test_successful_rebuy(self):
        result = process_rebuy(self.table.pk, self.user.pk)
        self.assertTrue(result)
        self.player.refresh_from_db()
        self.assertEqual(self.player.chips, 1000)
        self.assertEqual(self.player.rebuys_used, 1)
        self.assertEqual(self.player.coins_invested, 200)
        self.assertEqual(self.player.status, 'active')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.balance, 400)

    def test_rebuy_fails_when_not_allowed(self):
        self.table.allow_rebuys = False
        self.table.save()
        result = process_rebuy(self.table.pk, self.user.pk)
        self.assertFalse(result)

    def test_rebuy_fails_when_max_reached(self):
        self.player.rebuys_used = 2
        self.player.save(update_fields=['rebuys_used'])
        result = process_rebuy(self.table.pk, self.user.pk)
        self.assertFalse(result)

    def test_rebuy_fails_with_chips_remaining(self):
        self.player.chips = 500
        self.player.status = 'active'
        self.player.save(update_fields=['chips', 'status'])
        result = process_rebuy(self.table.pk, self.user.pk)
        self.assertFalse(result)

    def test_rebuy_fails_insufficient_balance(self):
        self.user.profile.balance = 10
        self.user.profile.save()
        result = process_rebuy(self.table.pk, self.user.pk)
        self.assertFalse(result)
