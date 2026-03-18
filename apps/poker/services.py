from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from django.db import transaction

from treys import Card, Evaluator

from .models import PokerAction, PokerHand, PokerPlayer, PokerTable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

evaluator = Evaluator()

RANKS = '23456789TJQKA'
SUITS = 'shdc'


def _build_deck():
    """Return a full 52-card deck as treys Card ints."""
    cards = []
    for r in RANKS:
        for s in SUITS:
            cards.append(Card.new(r + s))
    return cards


def _card_to_str(card_int):
    """Convert a treys card int to a two-char string like 'As', 'Kh'."""
    return Card.int_to_str(card_int)


def _str_to_card(s):
    """Convert a two-char string like 'As' to a treys card int."""
    return Card.new(s)


def _parse_cards(csv_str):
    """Parse a comma-separated card string into treys card ints."""
    if not csv_str:
        return []
    return [_str_to_card(c.strip()) for c in csv_str.split(',') if c.strip()]


def _cards_to_csv(card_ints):
    """Convert a list of treys card ints to comma-separated string."""
    return ','.join(_card_to_str(c) for c in card_ints)


def _get_active_seats(table, exclude_statuses=None):
    """Return PokerPlayers at the table who are still in play, ordered by seat."""
    exclude = exclude_statuses or ['eliminated', 'spectating', 'left', 'invited']
    return list(
        PokerPlayer.objects.filter(table=table)
        .exclude(status__in=exclude)
        .order_by('seat')
    )


def _next_seat(seats, current_seat, skip_seats=None):
    """Find the next seat after current_seat in the circular seat ordering."""
    skip = skip_seats or set()
    seat_numbers = [s.seat for s in seats if s.seat not in skip]
    if not seat_numbers:
        return current_seat
    seat_numbers.sort()
    for s in seat_numbers:
        if s > current_seat:
            return s
    return seat_numbers[0]


def _players_in_hand(hand, table):
    """Return PokerPlayers who are still active in this hand (not folded/eliminated)."""
    return list(
        PokerPlayer.objects.filter(table=table)
        .exclude(status__in=['folded', 'eliminated', 'spectating', 'left', 'invited'])
        .order_by('seat')
    )


def start_hand(table_id):
    """Deal a new hand: rotate dealer, post blinds, deal hole cards.

    Returns (hand, player_cards_map) where player_cards_map is
    {user_id: [card_int, card_int]}.
    """
    with transaction.atomic():
        table = PokerTable.objects.select_for_update().get(pk=table_id)
        active_players = _get_active_seats(table)

        if len(active_players) < 2:
            return None, {}

        # Reset folded players to active for new hand (only those with chips)
        PokerPlayer.objects.filter(
            table=table, status='folded', chips__gt=0,
        ).update(status='active')
        active_players = _get_active_seats(table)

        # Players with 0 chips sit out until they rebuy
        for p in active_players:
            if p.chips == 0:
                p.status = 'folded'
                p.save(update_fields=['status'])
        active_players = [p for p in active_players if p.chips > 0]

        # Rotate dealer
        seat_numbers = [p.seat for p in active_players]
        if table.hand_number == 0:
            dealer_seat = seat_numbers[0]
        else:
            dealer_seat = _next_seat(active_players, table.dealer_seat)

        table.hand_number += 1
        table.dealer_seat = dealer_seat
        table.save(update_fields=['hand_number', 'dealer_seat'])

        # Determine blind positions
        if len(active_players) == 2:
            # Heads-up: dealer posts SB
            sb_seat = dealer_seat
            bb_seat = _next_seat(active_players, dealer_seat)
        else:
            sb_seat = _next_seat(active_players, dealer_seat)
            bb_seat = _next_seat(active_players, sb_seat)

        # Build and shuffle deck
        deck = _build_deck()
        rng = secrets.SystemRandom()
        rng.shuffle(deck)

        # Deal hole cards
        player_cards = {}
        for p in active_players:
            card1 = deck.pop()
            card2 = deck.pop()
            player_cards[str(p.user_id)] = _cards_to_csv([card1, card2])

        # Create hand record
        hand = PokerHand.objects.create(
            table=table,
            hand_number=table.hand_number,
            dealer_seat=dealer_seat,
            player_hands=player_cards,
            status='preflop',
            current_bet=table.big_blind,
            last_raise=table.big_blind,
        )

        # Store remaining deck in memory (we'll deal community from it)
        # Save deck state as CSV in a way we can retrieve later
        # We store the top of deck in the hand's community_cards prefixed with "deck:"
        # Actually, let's store the deck as part of player_hands under a special key
        hand.player_hands['_deck'] = _cards_to_csv(deck)
        hand.save(update_fields=['player_hands'])

        # Post blinds
        sb_player = next(p for p in active_players if p.seat == sb_seat)
        bb_player = next(p for p in active_players if p.seat == bb_seat)

        sb_amount = min(table.small_blind, sb_player.chips)
        bb_amount = min(table.big_blind, bb_player.chips)

        sb_player.chips -= sb_amount
        sb_player.save(update_fields=['chips'])
        if sb_player.chips == 0:
            sb_player.status = 'all_in'
            sb_player.save(update_fields=['status'])

        bb_player.chips -= bb_amount
        bb_player.save(update_fields=['chips'])
        if bb_player.chips == 0:
            bb_player.status = 'all_in'
            bb_player.save(update_fields=['status'])

        hand.pot = sb_amount + bb_amount
        hand.round_bets = {
            str(sb_player.user_id): sb_amount,
            str(bb_player.user_id): bb_amount,
            '_acted': [],  # Blind posting does NOT count as acting
        }
        hand.save(update_fields=['pot', 'round_bets'])

        PokerAction.objects.create(hand=hand, player=sb_player, action='post_blind', amount=sb_amount)
        PokerAction.objects.create(hand=hand, player=bb_player, action='post_blind', amount=bb_amount)

        # Set first to act (UTG = after BB)
        if len(active_players) == 2:
            # Heads-up: SB (dealer) acts first preflop
            first_seat = sb_seat
        else:
            first_seat = _next_seat(active_players, bb_seat)
        hand.current_seat = first_seat
        hand.save(update_fields=['current_seat'])

        # Build the map of user_id -> [card_int, card_int] for sending to clients
        card_map = {}
        for p in active_players:
            cards_csv = player_cards[str(p.user_id)]
            card_map[p.user_id] = cards_csv

        return hand, card_map


def get_valid_actions(hand, player):
    """Return list of valid actions for the player in the current hand.

    Returns list of dicts: [{'action': 'fold'}, {'action': 'call', 'amount': 20}, ...]
    """
    if hand.status == 'completed':
        return []

    if player.status in ('folded', 'eliminated', 'spectating', 'left', 'all_in'):
        return []

    if hand.current_seat != player.seat:
        return []

    actions = [{'action': 'fold'}]
    round_bets = hand.round_bets or {}
    my_bet = round_bets.get(str(player.user_id), 0)
    to_call = hand.current_bet - my_bet

    if to_call <= 0:
        # No bet to match
        actions.append({'action': 'check'})
        if player.chips > 0:
            min_bet = hand.last_raise or hand.table.big_blind
            if player.chips <= min_bet:
                actions.append({'action': 'all_in', 'amount': player.chips})
            else:
                actions.append({'action': 'bet', 'min': min_bet, 'max': player.chips})
    else:
        # Must call or raise
        if to_call >= player.chips:
            actions.append({'action': 'all_in', 'amount': player.chips})
        else:
            actions.append({'action': 'call', 'amount': to_call})
            min_raise = hand.current_bet + hand.last_raise
            raise_chips_needed = min_raise - my_bet
            if raise_chips_needed >= player.chips:
                actions.append({'action': 'all_in', 'amount': player.chips})
            else:
                actions.append({
                    'action': 'raise',
                    'min': min_raise,
                    'max': my_bet + player.chips,
                })

    return actions


def process_action(hand_id, player_id, action, amount=0):
    """Validate and apply a player action.

    Returns (hand, action_taken, advance_info) where advance_info is:
    - None if the round continues
    - 'advance_round' if betting round is complete
    - 'showdown' if hand should go to showdown
    - 'winner' if only one player remains
    """
    with transaction.atomic():
        hand = PokerHand.objects.select_for_update().get(pk=hand_id)
        table = hand.table
        player = PokerPlayer.objects.select_for_update().get(
            table=table, user_id=player_id
        )

        # Validate it's this player's turn
        if hand.current_seat != player.seat:
            return hand, None, None
        if hand.status == 'completed':
            return hand, None, None

        valid = get_valid_actions(hand, player)
        valid_action_names = {a['action'] for a in valid}
        if action not in valid_action_names:
            return hand, None, None

        round_bets = hand.round_bets or {}
        my_bet = round_bets.get(str(player.user_id), 0)

        actual_amount = 0

        if action == 'fold':
            player.status = 'folded'
            player.save(update_fields=['status'])

        elif action == 'check':
            actual_amount = 0
            round_bets[str(player.user_id)] = my_bet  # Mark as having acted

        elif action == 'call':
            to_call = hand.current_bet - my_bet
            actual_amount = min(to_call, player.chips)
            player.chips -= actual_amount
            player.save(update_fields=['chips'])
            round_bets[str(player.user_id)] = my_bet + actual_amount
            hand.pot += actual_amount
            if player.chips == 0:
                player.status = 'all_in'
                player.save(update_fields=['status'])

        elif action == 'bet':
            actual_amount = max(amount, hand.last_raise or table.big_blind)
            actual_amount = min(actual_amount, player.chips)
            player.chips -= actual_amount
            player.save(update_fields=['chips'])
            round_bets[str(player.user_id)] = my_bet + actual_amount
            hand.current_bet = my_bet + actual_amount
            hand.last_raise = actual_amount
            hand.pot += actual_amount
            if player.chips == 0:
                player.status = 'all_in'
                player.save(update_fields=['status'])

        elif action == 'raise':
            # amount is the new total bet level
            raise_to = max(amount, hand.current_bet + hand.last_raise)
            raise_amount = raise_to - my_bet
            raise_amount = min(raise_amount, player.chips)
            actual_amount = raise_amount
            player.chips -= raise_amount
            player.save(update_fields=['chips'])
            round_bets[str(player.user_id)] = my_bet + raise_amount
            hand.last_raise = (my_bet + raise_amount) - hand.current_bet
            hand.current_bet = my_bet + raise_amount
            hand.pot += raise_amount
            if player.chips == 0:
                player.status = 'all_in'
                player.save(update_fields=['status'])

        elif action == 'all_in':
            actual_amount = player.chips
            player.chips = 0
            player.status = 'all_in'
            player.save(update_fields=['chips', 'status'])
            round_bets[str(player.user_id)] = my_bet + actual_amount
            new_total = my_bet + actual_amount
            if new_total > hand.current_bet:
                hand.last_raise = new_total - hand.current_bet
                hand.current_bet = new_total
            hand.pot += actual_amount

        # Mark this player as having explicitly acted (distinct from blind posting)
        acted = round_bets.get('_acted', [])
        player_key = str(player.user_id)
        if player_key not in acted:
            acted.append(player_key)
        round_bets['_acted'] = acted

        hand.round_bets = round_bets
        hand.save(update_fields=['pot', 'current_bet', 'last_raise', 'round_bets'])

        # Record the action
        PokerAction.objects.create(
            hand=hand, player=player, action=action, amount=actual_amount,
        )

        # Check what happens next
        active_players = _players_in_hand(hand, table)

        # Only one player left -> they win
        if len(active_players) == 1:
            hand.save(update_fields=['pot', 'current_bet', 'last_raise', 'round_bets'])
            return hand, action, 'winner'

        # Check if betting round is complete
        players_who_can_act = [
            p for p in active_players if p.status not in ('all_in', 'folded')
        ]

        if len(players_who_can_act) == 0:
            # Everyone is all-in or folded
            return hand, action, 'showdown'

        # Find next player to act
        acting_seats = {p.seat for p in players_who_can_act}
        next_s = _next_seat(
            [p for p in active_players if p.seat in acting_seats],
            player.seat,
        )

        # Check if the round is complete by seeing whether the next player
        # has already explicitly acted (not just posted a blind) and matched
        # the current bet.  When a bet/raise increases current_bet,
        # previously-acting players' recorded amounts fall below it, so
        # they'll need to act again — handled naturally.
        acted_set = set(round_bets.get('_acted', []))
        next_player = next((p for p in players_who_can_act if p.seat == next_s), None)
        if next_player:
            np_key = str(next_player.user_id)
            np_has_acted = np_key in acted_set
            np_bet = round_bets.get(np_key, 0)

            if np_has_acted and np_bet >= hand.current_bet:
                return hand, action, 'advance_round'

        hand.current_seat = next_s
        hand.save(update_fields=['current_seat'])
        return hand, action, None


def advance_round(hand_id):
    """Deal community cards and advance to the next betting round.

    Returns (hand, new_cards_csv) or (hand, None) if going to showdown.
    """
    with transaction.atomic():
        hand = PokerHand.objects.select_for_update().get(pk=hand_id)
        table = hand.table

        deck_csv = hand.player_hands.get('_deck', '')
        deck = _parse_cards(deck_csv)

        existing_community = _parse_cards(hand.community_cards)

        if hand.status == 'preflop':
            # Deal flop (3 cards)
            new_cards = [deck.pop() for _ in range(3)]
            hand.status = 'flop'
        elif hand.status == 'flop':
            # Deal turn (1 card)
            new_cards = [deck.pop()]
            hand.status = 'turn'
        elif hand.status == 'turn':
            # Deal river (1 card)
            new_cards = [deck.pop()]
            hand.status = 'river'
        elif hand.status == 'river':
            hand.status = 'showdown'
            hand.save(update_fields=['status'])
            return hand, None
        else:
            return hand, None

        all_community = existing_community + new_cards
        hand.community_cards = _cards_to_csv(all_community)

        # Update deck
        hand.player_hands['_deck'] = _cards_to_csv(deck)

        # Reset betting for new round
        hand.current_bet = 0
        hand.last_raise = table.big_blind
        hand.round_bets = {}

        # Set first to act (first active player after dealer)
        active_players = _players_in_hand(hand, table)
        acting_players = [p for p in active_players if p.status not in ('all_in',)]

        if not acting_players:
            # All remaining players are all-in, deal remaining community
            hand.save(update_fields=[
                'status', 'community_cards', 'current_bet', 'last_raise',
                'round_bets', 'player_hands',
            ])
            return hand, _cards_to_csv(new_cards)

        first_seat = _next_seat(acting_players, hand.dealer_seat)
        hand.current_seat = first_seat

        hand.save(update_fields=[
            'status', 'community_cards', 'current_bet', 'last_raise',
            'round_bets', 'current_seat', 'player_hands',
        ])

        return hand, _cards_to_csv(new_cards)


def resolve_hand(hand_id):
    """Evaluate hands and distribute pot. Returns (hand, results_list).

    results_list: [{'user_id': int, 'winnings': int, 'hand_name': str, 'cards': str}]
    """
    with transaction.atomic():
        hand = PokerHand.objects.select_for_update().get(pk=hand_id)
        table = hand.table

        active_players = _players_in_hand(hand, table)

        # If only one player left, they win without showdown
        if len(active_players) == 1:
            winner = active_players[0]
            winner.chips += hand.pot
            winner.save(update_fields=['chips'])
            hand.winner_ids = [winner.user_id]
            hand.status = 'completed'
            hand.save(update_fields=['winner_ids', 'status'])
            return hand, [{'user_id': winner.user_id, 'winnings': hand.pot, 'hand_name': '', 'cards': ''}]

        # Evaluate each player's hand
        community = _parse_cards(hand.community_cards)

        # If community cards aren't complete, deal remaining
        deck = _parse_cards(hand.player_hands.get('_deck', ''))
        while len(community) < 5:
            community.append(deck.pop())
        hand.community_cards = _cards_to_csv(community)

        player_scores = []
        for p in active_players:
            hole_csv = hand.player_hands.get(str(p.user_id), '')
            hole_cards = _parse_cards(hole_csv)
            if len(hole_cards) != 2 or len(community) != 5:
                continue
            score = evaluator.evaluate(hole_cards, community)
            hand_class = evaluator.get_rank_class(score)
            hand_name = evaluator.class_to_string(hand_class)
            player_scores.append({
                'player': p,
                'score': score,
                'hand_name': hand_name,
                'cards': hole_csv,
            })

        # Sort by score (lower = better in treys)
        player_scores.sort(key=lambda x: x['score'])

        # Handle side pots
        results = _distribute_pot(hand, active_players, player_scores)

        hand.winner_ids = [r['user_id'] for r in results if r['winnings'] > 0]
        hand.status = 'completed'
        hand.player_hands['_deck'] = _cards_to_csv(deck)
        hand.save(update_fields=['winner_ids', 'status', 'community_cards', 'player_hands'])

        return hand, results


def _distribute_pot(hand, active_players, player_scores):
    """Distribute pot including side pots. Returns results list."""
    if not player_scores:
        return []

    # Simple pot distribution (handles side pots via all-in amounts)
    # For now, use a simplified approach: best hand wins the pot
    # TODO: proper side pot calculation for complex all-in scenarios

    total_pot = hand.pot
    results = []

    # Find the best score
    best_score = player_scores[0]['score']
    winners = [ps for ps in player_scores if ps['score'] == best_score]

    # Split pot among winners
    share = total_pot // len(winners)
    remainder = total_pot % len(winners)

    for i, w in enumerate(winners):
        winnings = share + (1 if i == 0 else 0) * remainder
        w['player'].chips += winnings
        w['player'].save(update_fields=['chips'])
        results.append({
            'user_id': w['player'].user_id,
            'winnings': winnings,
            'hand_name': w['hand_name'],
            'cards': w['cards'],
        })

    # Add non-winners to results with 0 winnings
    winner_ids = {w['player'].user_id for w in winners}
    for ps in player_scores:
        if ps['player'].user_id not in winner_ids:
            results.append({
                'user_id': ps['player'].user_id,
                'winnings': 0,
                'hand_name': ps['hand_name'],
                'cards': ps['cards'],
            })

    return results


def check_table_over(table_id):
    """Check if the table game is over (one player has all chips or only one non-eliminated).

    Returns (is_over, winner_player_or_none).
    """
    table = PokerTable.objects.get(pk=table_id)
    active = list(
        PokerPlayer.objects.filter(table=table)
        .exclude(status__in=['eliminated', 'spectating', 'left', 'invited'])
    )

    # Eliminate players with 0 chips
    for p in active:
        if p.chips == 0 and p.status not in ('eliminated', 'spectating'):
            if table.allow_rebuys and (table.max_rebuys == 0 or p.rebuys_used < table.max_rebuys):
                continue  # Can still rebuy
            p.status = 'eliminated'
            p.save(update_fields=['status'])

    # Re-check active players
    remaining = list(
        PokerPlayer.objects.filter(table=table)
        .exclude(status__in=['eliminated', 'spectating', 'left', 'invited'])
    )

    if len(remaining) <= 1:
        return True, remaining[0] if remaining else None
    return False, None


def calculate_payouts(table_id):
    """Calculate proportional payouts based on chip counts.

    If a hand is in progress, refund pot contributions back to player stacks
    first so that unfinished-hand bets don't skew the proportional split.

    Returns list of (user, amount) tuples.
    """
    table = PokerTable.objects.get(pk=table_id)
    players = list(PokerPlayer.objects.filter(table=table).exclude(status='invited'))

    # Refund any in-progress hand's pot back to contributors
    current_hand = PokerHand.objects.filter(
        table=table,
    ).exclude(status='completed').order_by('-hand_number').first()

    if current_hand and current_hand.pot > 0:
        from django.db.models import Sum
        contributions = (
            PokerAction.objects.filter(hand=current_hand)
            .values('player__user_id')
            .annotate(total=Sum('amount'))
        )
        contrib_map = {c['player__user_id']: c['total'] for c in contributions}
        for p in players:
            refund = contrib_map.get(p.user_id, 0)
            if refund > 0:
                p.chips += refund
                p.save(update_fields=['chips'])

    total_coins = sum(p.coins_invested for p in players)
    total_chips = sum(p.chips for p in players)

    if total_chips == 0:
        return []

    payouts = []
    distributed = 0
    # Sort by chips descending so remainder goes to largest stack
    players_sorted = sorted(players, key=lambda p: p.chips, reverse=True)

    for i, p in enumerate(players_sorted):
        if p.chips == 0:
            payouts.append((p.user, 0))
            continue
        payout = (p.chips * total_coins) // total_chips
        if i == 0:
            # Give remainder to largest stack
            payout = total_coins - sum(
                (pp.chips * total_coins) // total_chips
                for pp in players_sorted[1:]
                if pp.chips > 0
            )
        distributed += payout
        payouts.append((p.user, payout))

    return payouts


def process_rebuy(table_id, user_id):
    """Process a rebuy for a player. Returns True if successful."""
    with transaction.atomic():
        table = PokerTable.objects.get(pk=table_id)
        player = PokerPlayer.objects.select_for_update().get(
            table=table, user_id=user_id
        )

        if not table.allow_rebuys:
            return False
        if table.max_rebuys > 0 and player.rebuys_used >= table.max_rebuys:
            return False
        if player.chips > 0:
            return False
        if player.status not in ('eliminated', 'active', 'folded'):
            return False

        # Import here to avoid circular imports
        from apps.economy.services import InsufficientFunds, poker_buy_in

        try:
            poker_buy_in(player.user, table.stake, note=f'Poker rebuy - Table #{table.pk}')
        except InsufficientFunds:
            return False

        player.chips = table.starting_chips
        player.rebuys_used += 1
        player.coins_invested += table.stake
        player.status = 'active'
        player.save(update_fields=['chips', 'rebuys_used', 'coins_invested', 'status'])

        return True
