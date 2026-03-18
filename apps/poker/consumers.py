import asyncio
import json
import logging

from channels.db import database_sync_to_async
from django.utils import timezone

from apps.economy.services import InsufficientFunds, poker_buy_in, poker_payout
from apps.games.mixins import BaseGameConsumer
from apps.notifications.services import send_notification

from .models import PokerHand, PokerPlayer, PokerTable
from .services import (
    advance_round,
    calculate_payouts,
    check_table_over,
    get_valid_actions,
    process_action,
    process_rebuy,
    resolve_hand,
    start_hand,
)

logger = logging.getLogger(__name__)


class PokerConsumer(BaseGameConsumer):
    game_type = 'poker'

    async def connect(self):
        self.table_id = self.scope['url_route']['kwargs']['table_id']
        self.room_group_name = f'poker_{self.table_id}'
        self.user = self.scope['user']
        self._action_timer = None

        if self.user.is_anonymous:
            await self.close()
            return

        player = await self.get_player()
        if not player:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.set_online(True)

        logger.info('Poker WS connected: user=%s table=%s', self.user.username, self.table_id)

        # Send current table state to this player
        await self.send_table_state()

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'player_connected',
            'username': self.user.username,
        })

        # Auto-deal first hand if the table is active but no hand has been dealt
        await self.maybe_deal_first_hand()

    async def disconnect(self, close_code):
        if self._action_timer and not self._action_timer.done():
            self._action_timer.cancel()

        if hasattr(self, 'user') and not self.user.is_anonymous:
            await self.set_online(False)

            # Auto-vote yes for end vote if offline
            await self.auto_vote_end()

            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'player_disconnected',
                'username': self.user.username,
            })

        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get('action')

        if action == 'poker_action':
            if self.is_throttled():
                return
            await self.handle_poker_action(data)
        elif action == 'vote_end':
            await self.handle_vote_end(data)
        elif action == 'rebuy':
            await self.handle_rebuy()
        elif action == 'start_game':
            await self.handle_start_game()

    async def handle_start_game(self):
        """Creator starts the game via WebSocket (alternative to HTTP view)."""
        table = await self.get_table()
        if not table or table.status != 'active':
            return

        # Deal first hand
        hand, card_map = await database_sync_to_async(start_hand)(table.pk)
        if not hand:
            await self.send(text_data=json.dumps({
                'type': 'error', 'message': 'Not enough players to start.',
            }))
            return

        await self.broadcast_hand_started(hand, card_map)

    async def maybe_deal_first_hand(self):
        """Auto-deal the first hand if table is active with no hands yet."""
        table = await self.get_table()
        if not table or table.status != 'active' or table.hand_number > 0:
            return

        # Use atomic check to prevent double-dealing from concurrent connects
        dealt = await self._try_claim_first_deal()
        if not dealt:
            return

        await asyncio.sleep(0.5)
        hand, card_map = await database_sync_to_async(start_hand)(table.pk)
        if hand:
            await self.broadcast_hand_started(hand, card_map)

    @database_sync_to_async
    def _try_claim_first_deal(self):
        """Atomically check and mark that first deal is being handled."""
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            t = PokerTable.objects.select_for_update().get(pk=self.table_id)
            if t.status == 'active' and t.hand_number == 0:
                # Mark hand_number to -1 temporarily as a lock sentinel
                # start_hand will set it to 1
                return True
            return False

    async def handle_poker_action(self, data):
        poker_action = data.get('poker_action', '')
        amount = data.get('amount', 0)

        try:
            amount = int(amount)
        except (ValueError, TypeError):
            amount = 0

        player = await self.get_player()
        if not player:
            return

        hand = await self.get_current_hand()
        if not hand:
            return

        hand, action_taken, advance_info = await database_sync_to_async(
            process_action
        )(hand.pk, self.user.pk, poker_action, amount)

        if not action_taken:
            return

        # Cancel any existing timer
        if self._action_timer and not self._action_timer.done():
            self._action_timer.cancel()

        # Broadcast the action
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'player_acted',
            'username': self.user.username,
            'poker_action': action_taken,
            'amount': amount,
            'pot': hand.pot,
        })

        if advance_info == 'winner':
            # Only one player left
            hand, results = await database_sync_to_async(resolve_hand)(hand.pk)
            await self.broadcast_hand_result(hand, results, showdown=False)
            await self.check_and_continue(hand)

        elif advance_info == 'showdown':
            # Deal remaining community cards and evaluate
            await self.deal_remaining_and_showdown(hand)

        elif advance_info == 'advance_round':
            hand, new_cards = await database_sync_to_async(advance_round)(hand.pk)
            if hand.status == 'showdown' or new_cards is None:
                await self.deal_remaining_and_showdown(hand)
            else:
                await self.channel_layer.group_send(self.room_group_name, {
                    'type': 'community_cards',
                    'cards': new_cards,
                    'round': hand.status,
                    'pot': hand.pot,
                })
                # Send action_required
                await self.send_action_required(hand)
        else:
            # Round continues, next player's turn
            await self.send_action_required(hand)

    async def deal_remaining_and_showdown(self, hand):
        """Deal remaining community cards and resolve the hand."""
        # Deal remaining community cards if needed
        while hand.status not in ('showdown', 'completed'):
            hand, new_cards = await database_sync_to_async(advance_round)(hand.pk)
            if new_cards:
                await self.channel_layer.group_send(self.room_group_name, {
                    'type': 'community_cards',
                    'cards': new_cards,
                    'round': hand.status,
                    'pot': hand.pot,
                })
                await asyncio.sleep(0.5)

        hand, results = await database_sync_to_async(resolve_hand)(hand.pk)
        await self.broadcast_hand_result(hand, results, showdown=True)
        await self.check_and_continue(hand)

    async def check_and_continue(self, hand):
        """Check if game is over, otherwise deal next hand."""
        table = await self.get_table()
        is_over, winner = await database_sync_to_async(check_table_over)(table.pk)

        if is_over:
            await self.end_game(table)
        else:
            # Brief pause then deal next hand
            await asyncio.sleep(2)
            new_hand, card_map = await database_sync_to_async(start_hand)(table.pk)
            if new_hand:
                await self.broadcast_hand_started(new_hand, card_map)
            else:
                await self.end_game(table)

    async def end_game(self, table):
        """End the game and pay out."""
        payouts = await database_sync_to_async(calculate_payouts)(table.pk)

        if payouts:
            payout_tuples = [(user, amount) for user, amount in payouts if amount > 0]
            if payout_tuples:
                await database_sync_to_async(poker_payout)(
                    payout_tuples, note=f'Poker payout - Table #{table.pk}'
                )

        await database_sync_to_async(self._finish_table)(table.pk)

        # Create notifications
        await database_sync_to_async(self._create_game_notifications)(table.pk, payouts)

        payout_data = []
        for user, amount in payouts:
            username = await self.get_username(user.pk)
            payout_data.append({'username': username, 'amount': amount})

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'game_over',
            'payouts': payout_data,
        })

    def _finish_table(self, table_id):
        PokerTable.objects.filter(pk=table_id, status='active').update(
            status='completed', ended_at=timezone.now(),
        )

    def _create_game_notifications(self, table_id, payouts):
        table = PokerTable.objects.get(pk=table_id)
        for user, amount in payouts:
            player = PokerPlayer.objects.get(table=table, user=user)
            net = amount - player.coins_invested
            if net > 0:
                send_notification(
                    user,
                    'game_result',
                    'Poker Win!',
                    f'You won {net} LC profit at poker table #{table.pk}!',
                    link='/poker/',
                )
            elif net < 0:
                send_notification(
                    user,
                    'game_result',
                    'Poker Result',
                    f'You lost {abs(net)} LC at poker table #{table.pk}.',
                    link='/poker/',
                )

    async def handle_vote_end(self, data):
        vote = data.get('vote', True)

        if vote:
            result = await self.process_vote_end(True)
            if result == 'all_voted':
                # Wait for current hand to complete, then end
                table = await self.get_table()
                await self.end_game(table)
                return
        else:
            await self.process_vote_end(False)

        table = await self.get_table()
        vote_info = await self.get_vote_info()
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'end_vote_update',
            'active': table.end_vote_active,
            'votes': vote_info,
        })

    async def handle_rebuy(self):
        success = await database_sync_to_async(process_rebuy)(
            self.table_id, self.user.pk
        )
        if success:
            player = await self.get_player()
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'player_rebuyed',
                'username': self.user.username,
                'chips': player.chips if player else 0,
            })
        else:
            await self.send(text_data=json.dumps({
                'type': 'error', 'message': 'Rebuy failed.',
            }))

    # Broadcasting helpers

    async def broadcast_hand_started(self, hand, card_map):
        """Broadcast hand start. Send hole cards privately to each player."""
        table = await self.get_table()
        players = await self.get_all_players()

        # Broadcast general hand info to the group
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'hand_started',
            'hand_number': hand.hand_number,
            'dealer_seat': hand.dealer_seat,
            'pot': hand.pot,
            'small_blind': table.small_blind,
            'big_blind': table.big_blind,
            'players': [
                {
                    'username': p.user.username,
                    'seat': p.seat,
                    'chips': p.chips,
                    'status': p.status,
                }
                for p in players
            ],
        })

        # Send action_required after a brief delay
        await asyncio.sleep(0.3)
        await self.send_action_required(hand)

    async def send_action_required(self, hand):
        """Send action_required to the group with whose turn + valid actions."""
        hand = await database_sync_to_async(
            lambda: PokerHand.objects.select_related('table').get(pk=hand.pk)
        )()
        player = await database_sync_to_async(
            lambda: PokerPlayer.objects.select_related('user').get(
                table=hand.table, seat=hand.current_seat
            )
        )()
        valid = await database_sync_to_async(get_valid_actions)(hand, player)

        table = hand.table
        timeout = table.time_per_action if table.time_per_action > 0 else 0

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'action_required',
            'seat': hand.current_seat,
            'username': player.user.username,
            'valid_actions': valid,
            'current_bet': hand.current_bet,
            'pot': hand.pot,
            'timeout': timeout,
        })

        # Start action timer
        if timeout > 0:
            if self._action_timer and not self._action_timer.done():
                self._action_timer.cancel()
            self._action_timer = asyncio.ensure_future(
                self.action_timeout(hand.pk, player.user_id, timeout)
            )

    async def action_timeout(self, hand_id, user_id, timeout):
        """Auto-fold if player doesn't act in time."""
        try:
            await asyncio.sleep(timeout)

            # Guard: verify the hand still expects this player's action
            hand = await database_sync_to_async(
                lambda: PokerHand.objects.select_related('table').get(pk=hand_id)
            )()
            if hand.status in ('completed', 'showdown'):
                return
            player = await database_sync_to_async(
                lambda: PokerPlayer.objects.get(table=hand.table, user_id=user_id)
            )()
            if hand.current_seat != player.seat:
                return

            hand, action_taken, advance_info = await database_sync_to_async(
                process_action
            )(hand_id, user_id, 'fold')

            if action_taken:
                username = await self.get_username(user_id)
                await self.channel_layer.group_send(self.room_group_name, {
                    'type': 'player_acted',
                    'username': username,
                    'poker_action': 'fold',
                    'amount': 0,
                    'pot': hand.pot,
                })

                if advance_info == 'winner':
                    hand, results = await database_sync_to_async(resolve_hand)(hand.pk)
                    await self.broadcast_hand_result(hand, results, showdown=False)
                    await self.check_and_continue(hand)
                elif advance_info == 'showdown':
                    await self.deal_remaining_and_showdown(hand)
                elif advance_info == 'advance_round':
                    hand, new_cards = await database_sync_to_async(advance_round)(hand.pk)
                    if hand.status == 'showdown' or new_cards is None:
                        await self.deal_remaining_and_showdown(hand)
                    else:
                        await self.channel_layer.group_send(self.room_group_name, {
                            'type': 'community_cards',
                            'cards': new_cards,
                            'round': hand.status,
                            'pot': hand.pot,
                        })
                        await self.send_action_required(hand)
                else:
                    await self.send_action_required(hand)
        except asyncio.CancelledError:
            pass

    async def broadcast_hand_result(self, hand, results, showdown=True):
        """Broadcast hand results."""
        result_data = []
        for r in results:
            username = await self.get_username(r['user_id'])
            result_data.append({
                'username': username,
                'winnings': r['winnings'],
                'hand_name': r.get('hand_name', ''),
                'cards': r.get('cards', '') if showdown else '',
            })

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'showdown' if showdown else 'hand_complete',
            'results': result_data,
            'community_cards': hand.community_cards,
            'pot': hand.pot,
        })

    async def send_table_state(self):
        """Send complete table state to the connecting player."""
        table = await self.get_table()
        players = await self.get_all_players()
        hand = await self.get_current_hand()
        player = await self.get_player()

        my_cards = ''
        if hand and hand.player_hands:
            my_cards = hand.player_hands.get(str(self.user.pk), '')

        state = {
            'type': 'table_state',
            'table_id': table.pk,
            'status': table.status,
            'stake': table.stake,
            'starting_chips': table.starting_chips,
            'small_blind': table.small_blind,
            'big_blind': table.big_blind,
            'allow_rebuys': table.allow_rebuys,
            'max_rebuys': table.max_rebuys,
            'min_players': table.min_players,
            'max_players': table.max_players,
            'time_per_action': table.time_per_action,
            'hand_number': table.hand_number,
            'dealer_seat': table.dealer_seat,
            'is_creator': table.creator_id == self.user.pk,
            'my_seat': player.seat if player else -1,
            'my_cards': my_cards,
            'players': [
                {
                    'username': p.user.username,
                    'display_name': p.user.profile.get_display_name(),
                    'seat': p.seat,
                    'chips': p.chips,
                    'status': p.status,
                    'is_online': p.is_online,
                    'avatar_url': p.user.profile.avatar.url if p.user.profile.avatar else '',
                }
                for p in players
            ],
        }

        if hand:
            state['hand'] = {
                'hand_number': hand.hand_number,
                'status': hand.status,
                'community_cards': hand.community_cards,
                'pot': hand.pot,
                'current_seat': hand.current_seat,
                'current_bet': hand.current_bet,
                'dealer_seat': hand.dealer_seat,
            }

        await self.send(text_data=json.dumps(state))

    # Channel layer event handlers

    async def hand_started(self, event):
        """Send hand_started to client, with their private hole cards."""
        hand = await self.get_current_hand()
        my_cards = ''
        if hand and hand.player_hands:
            my_cards = hand.player_hands.get(str(self.user.pk), '')

        await self.send(text_data=json.dumps({
            'type': 'hand_started',
            'hand_number': event['hand_number'],
            'dealer_seat': event['dealer_seat'],
            'pot': event['pot'],
            'small_blind': event['small_blind'],
            'big_blind': event['big_blind'],
            'players': event['players'],
            'my_cards': my_cards,
        }))

    async def action_required(self, event):
        await self.send(text_data=json.dumps({
            'type': 'action_required',
            'seat': event['seat'],
            'username': event['username'],
            'valid_actions': event['valid_actions'] if event['username'] == self.user.username else [],
            'current_bet': event['current_bet'],
            'pot': event['pot'],
            'timeout': event['timeout'],
        }))

    async def player_acted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_acted',
            'username': event['username'],
            'poker_action': event['poker_action'],
            'amount': event['amount'],
            'pot': event['pot'],
        }))

    async def community_cards(self, event):
        await self.send(text_data=json.dumps({
            'type': 'community_cards',
            'cards': event['cards'],
            'round': event['round'],
            'pot': event['pot'],
        }))

    async def showdown(self, event):
        await self.send(text_data=json.dumps({
            'type': 'showdown',
            'results': event['results'],
            'community_cards': event['community_cards'],
            'pot': event['pot'],
        }))

    async def hand_complete(self, event):
        await self.send(text_data=json.dumps({
            'type': 'hand_complete',
            'results': event['results'],
            'community_cards': event['community_cards'],
            'pot': event['pot'],
        }))

    async def pot_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'pot_update',
            'pot': event['pot'],
            'side_pots': event.get('side_pots', []),
        }))

    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
            'username': event['username'],
        }))

    async def player_disconnected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_disconnected',
            'username': event['username'],
        }))

    async def player_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_joined',
            'username': event['username'],
            'display_name': event['display_name'],
            'seat': event['seat'],
            'chips': event['chips'],
            'avatar_url': event.get('avatar_url', ''),
        }))

    async def player_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_left',
            'username': event['username'],
            'seat': event['seat'],
        }))

    async def table_cancelled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'table_cancelled',
        }))

    async def table_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'table_started',
        }))

    async def end_vote_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'end_vote_update',
            'active': event['active'],
            'votes': event['votes'],
        }))

    async def game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'payouts': event['payouts'],
        }))

    async def player_eliminated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_eliminated',
            'username': event['username'],
        }))

    async def player_rebuyed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_rebuyed',
            'username': event['username'],
            'chips': event['chips'],
        }))

    async def game_error(self, event):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message'],
        }))

    # Database helpers

    @database_sync_to_async
    def get_table(self):
        try:
            return PokerTable.objects.get(pk=self.table_id)
        except PokerTable.DoesNotExist:
            return None

    @database_sync_to_async
    def get_player(self):
        try:
            return PokerPlayer.objects.select_related('user', 'user__profile').get(
                table_id=self.table_id, user=self.user,
            )
        except PokerPlayer.DoesNotExist:
            return None

    @database_sync_to_async
    def get_all_players(self):
        return list(
            PokerPlayer.objects.filter(table_id=self.table_id)
            .exclude(status='invited')
            .select_related('user', 'user__profile')
            .order_by('seat')
        )

    @database_sync_to_async
    def get_current_hand(self):
        try:
            return PokerHand.objects.filter(
                table_id=self.table_id
            ).select_related('table').order_by('-hand_number').first()
        except PokerHand.DoesNotExist:
            return None

    @database_sync_to_async
    def set_online(self, online):
        PokerPlayer.objects.filter(
            table_id=self.table_id, user=self.user,
        ).update(is_online=online)

    @database_sync_to_async
    def auto_vote_end(self):
        try:
            table = PokerTable.objects.get(pk=self.table_id)
            if table.end_vote_active:
                PokerPlayer.objects.filter(
                    table=table, user=self.user,
                ).update(vote_end=True)
        except PokerTable.DoesNotExist:
            pass

    @database_sync_to_async
    def process_vote_end(self, vote):
        from django.db import transaction
        with transaction.atomic():
            table = PokerTable.objects.select_for_update().get(pk=self.table_id)

            if vote:
                if not table.end_vote_active:
                    table.end_vote_active = True
                    table.end_vote_initiated_by = self.user
                    table.save(update_fields=['end_vote_active', 'end_vote_initiated_by'])

                PokerPlayer.objects.filter(
                    table=table, user=self.user,
                ).update(vote_end=True)

                # Auto-vote yes for offline players
                PokerPlayer.objects.filter(
                    table=table, is_online=False,
                ).exclude(status__in=['eliminated', 'spectating', 'left', 'invited']).update(vote_end=True)

                # Check if all active players voted
                active = PokerPlayer.objects.filter(
                    table=table,
                ).exclude(status__in=['eliminated', 'spectating', 'left', 'invited'])
                all_voted = all(p.vote_end for p in active)
                if all_voted:
                    return 'all_voted'
            else:
                # Reset all votes
                table.end_vote_active = False
                table.end_vote_initiated_by = None
                table.save(update_fields=['end_vote_active', 'end_vote_initiated_by'])
                PokerPlayer.objects.filter(table=table).update(vote_end=False)

            return None

    @database_sync_to_async
    def get_vote_info(self):
        players = PokerPlayer.objects.filter(
            table_id=self.table_id,
        ).exclude(status__in=['invited', 'left']).select_related('user')
        return [
            {'username': p.user.username, 'voted': p.vote_end}
            for p in players
        ]
