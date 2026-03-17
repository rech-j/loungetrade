from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rate_limit
from apps.economy.services import InsufficientFunds, poker_buy_in, poker_payout
from apps.notifications.services import send_notification

from .models import PokerPlayer, PokerTable


def _broadcast_to_table(table_id, event):
    """Send a channel-layer event to all WebSocket consumers at a poker table."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(f'poker_{table_id}', event)


@login_required
def lobby_view(request):
    # Public pending tables anyone can join
    public_tables = PokerTable.objects.filter(
        status='pending', is_public=True,
    ).select_related('creator', 'creator__profile').prefetch_related('players')

    # Private tables the user is invited to
    invited_tables = PokerTable.objects.filter(
        status='pending', is_public=False,
        players__user=request.user,
    ).select_related('creator', 'creator__profile').prefetch_related('players')

    # Active tables the user is in
    active_tables = PokerTable.objects.filter(
        status='active',
        players__user=request.user,
    ).select_related('creator', 'creator__profile').prefetch_related('players')

    # Recent completed tables
    recent_tables = PokerTable.objects.filter(
        status='completed',
        players__user=request.user,
    ).select_related('creator', 'creator__profile')[:10]

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    return render(request, 'poker/lobby.html', {
        'public_tables': public_tables,
        'invited_tables': invited_tables,
        'active_tables': active_tables,
        'recent_tables': recent_tables,
        'max_stake': max_stake,
    })


@login_required
@rate_limit('poker_create', max_requests=5, window=60)
def create_table(request):
    if request.method != 'POST':
        return redirect('poker_lobby')

    stake_raw = request.POST.get('stake', 0)
    is_public = request.POST.get('is_public') == 'on'
    starting_chips = request.POST.get('starting_chips', 1000)
    small_blind = request.POST.get('small_blind', 10)
    big_blind = request.POST.get('big_blind', 20)
    max_players = request.POST.get('max_players', 8)
    min_players = request.POST.get('min_players', 3)
    allow_rebuys = request.POST.get('allow_rebuys') == 'on'
    max_rebuys = request.POST.get('max_rebuys', 0)
    time_per_action = request.POST.get('time_per_action', 30)
    invited_usernames = request.POST.getlist('invited_users')

    try:
        stake = int(stake_raw)
        starting_chips = int(starting_chips)
        small_blind = int(small_blind)
        big_blind = int(big_blind)
        max_players = int(max_players)
        min_players = int(min_players)
        max_rebuys = int(max_rebuys)
        time_per_action = int(time_per_action)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid input.')
        return redirect('poker_lobby')

    if stake <= 0:
        messages.error(request, 'Stake must be positive.')
        return redirect('poker_lobby')

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    if stake > max_stake:
        messages.error(request, f'Maximum stake is {max_stake} LC.')
        return redirect('poker_lobby')

    if not (2 <= min_players <= max_players <= 8):
        messages.error(request, 'Player count must be between 2 and 8.')
        return redirect('poker_lobby')

    if big_blind <= 0 or small_blind <= 0 or big_blind < small_blind:
        messages.error(request, 'Invalid blind values.')
        return redirect('poker_lobby')

    if starting_chips < big_blind * 10:
        messages.error(request, 'Starting chips must be at least 10x the big blind.')
        return redirect('poker_lobby')

    if request.user.profile.balance < stake:
        messages.error(request, 'Insufficient balance.')
        return redirect('poker_lobby')

    # Deduct buy-in from creator
    try:
        poker_buy_in(request.user, stake, note='Poker buy-in')
    except InsufficientFunds:
        messages.error(request, 'Insufficient balance.')
        return redirect('poker_lobby')

    table = PokerTable.objects.create(
        creator=request.user,
        is_public=is_public,
        stake=stake,
        starting_chips=starting_chips,
        min_players=min_players,
        max_players=max_players,
        small_blind=small_blind,
        big_blind=big_blind,
        allow_rebuys=allow_rebuys,
        max_rebuys=max_rebuys if allow_rebuys else 0,
        time_per_action=time_per_action,
    )

    # Add creator as first player
    PokerPlayer.objects.create(
        table=table,
        user=request.user,
        seat=0,
        chips=starting_chips,
        status='active',
        coins_invested=stake,
    )

    # Handle invited players (private tables)
    if not is_public and invited_usernames:
        next_seat = 1
        for username in invited_usernames:
            username = username.strip()
            if not username or username == request.user.username:
                continue
            try:
                invited_user = User.objects.get(username=username)
            except User.DoesNotExist:
                continue

            if next_seat >= max_players:
                break

            PokerPlayer.objects.create(
                table=table,
                user=invited_user,
                seat=next_seat,
                chips=0,
                status='invited',
                coins_invested=0,
            )
            next_seat += 1

            send_notification(
                invited_user,
                'game_invite',
                'Poker Invite!',
                f'{request.user.profile.get_display_name()} invited you to a poker table '
                f'for {stake} LC buy-in!',
                link=f'/poker/play/{table.pk}/',
            )

    return redirect('poker_play', table_id=table.pk)


@login_required
def join_table(request, table_id):
    if request.method != 'POST':
        return redirect('poker_lobby')

    table = get_object_or_404(PokerTable, pk=table_id, status='pending')

    # Check if already joined
    existing = PokerPlayer.objects.filter(table=table, user=request.user).first()
    if existing:
        if existing.status == 'invited':
            # Accept invite: deduct buy-in, activate
            try:
                poker_buy_in(request.user, table.stake, note=f'Poker buy-in - Table #{table.pk}')
            except InsufficientFunds:
                messages.error(request, 'Insufficient balance.')
                return redirect('poker_lobby')
            existing.chips = table.starting_chips
            existing.status = 'active'
            existing.coins_invested = table.stake
            existing.save(update_fields=['chips', 'status', 'coins_invested'])
            _broadcast_to_table(table.pk, {
                'type': 'player_joined',
                'username': request.user.username,
                'display_name': request.user.profile.get_display_name(),
                'seat': existing.seat,
                'chips': existing.chips,
                'avatar_url': request.user.profile.avatar.url if request.user.profile.avatar else '',
            })
            return redirect('poker_play', table_id=table.pk)
        else:
            return redirect('poker_play', table_id=table.pk)

    if not table.is_public:
        messages.error(request, 'This table is invite-only.')
        return redirect('poker_lobby')

    player_count = table.players.exclude(status='invited').count()
    if player_count >= table.max_players:
        messages.error(request, 'Table is full.')
        return redirect('poker_lobby')

    if request.user.profile.balance < table.stake:
        messages.error(request, 'Insufficient balance.')
        return redirect('poker_lobby')

    try:
        poker_buy_in(request.user, table.stake, note=f'Poker buy-in - Table #{table.pk}')
    except InsufficientFunds:
        messages.error(request, 'Insufficient balance.')
        return redirect('poker_lobby')

    # Assign next available seat
    taken_seats = set(table.players.values_list('seat', flat=True))
    seat = 0
    while seat in taken_seats:
        seat += 1

    PokerPlayer.objects.create(
        table=table,
        user=request.user,
        seat=seat,
        chips=table.starting_chips,
        status='active',
        coins_invested=table.stake,
    )

    _broadcast_to_table(table.pk, {
        'type': 'player_joined',
        'username': request.user.username,
        'display_name': request.user.profile.get_display_name(),
        'seat': seat,
        'chips': table.starting_chips,
        'avatar_url': request.user.profile.avatar.url if request.user.profile.avatar else '',
    })

    return redirect('poker_play', table_id=table.pk)


@login_required
def play_view(request, table_id):
    table = get_object_or_404(PokerTable, pk=table_id)

    player = PokerPlayer.objects.filter(table=table, user=request.user).first()
    if not player:
        messages.error(request, 'You are not at this table.')
        return redirect('poker_lobby')

    players = list(
        PokerPlayer.objects.filter(table=table)
        .exclude(status='invited')
        .select_related('user', 'user__profile')
        .order_by('seat')
    )

    return render(request, 'poker/play.html', {
        'table': table,
        'player': player,
        'players': players,
        'is_creator': request.user.pk == table.creator_id,
    })


@login_required
def leave_table(request, table_id):
    if request.method != 'POST':
        return redirect('poker_lobby')

    table = get_object_or_404(PokerTable, pk=table_id, status='pending')
    player = get_object_or_404(PokerPlayer, table=table, user=request.user)

    if table.creator == request.user:
        # Creator leaving cancels the table, refund all players
        for p in table.players.exclude(status='invited'):
            if p.coins_invested > 0:
                poker_payout([(p.user, p.coins_invested)], note=f'Poker table cancelled - Table #{table.pk}')
        table.status = 'cancelled'
        table.save(update_fields=['status'])
        _broadcast_to_table(table.pk, {
            'type': 'table_cancelled',
        })
        messages.info(request, 'Poker table cancelled. Buy-ins refunded.')
    else:
        # Non-creator leaving: refund their buy-in
        if player.coins_invested > 0:
            poker_payout([(player.user, player.coins_invested)], note=f'Left poker table #{table.pk}')
        left_seat = player.seat
        player.delete()
        _broadcast_to_table(table.pk, {
            'type': 'player_left',
            'username': request.user.username,
            'seat': left_seat,
        })
        messages.info(request, 'Left the table. Buy-in refunded.')

    return redirect('poker_lobby')


@login_required
def start_table(request, table_id):
    if request.method != 'POST':
        return redirect('poker_lobby')

    table = get_object_or_404(PokerTable, pk=table_id, status='pending', creator=request.user)

    active_count = table.players.exclude(status='invited').count()
    if active_count < table.min_players:
        messages.error(request, f'Need at least {table.min_players} players to start.')
        return redirect('poker_play', table_id=table.pk)

    from django.utils import timezone
    table.status = 'active'
    table.started_at = timezone.now()
    table.save(update_fields=['status', 'started_at'])

    _broadcast_to_table(table.pk, {
        'type': 'table_started',
    })

    return redirect('poker_play', table_id=table.pk)
