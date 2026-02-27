from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rate_limit
from apps.notifications.models import Notification

from .models import ChessGame


@login_required
def lobby_view(request):
    pending_games = ChessGame.objects.filter(
        Q(creator=request.user) | Q(opponent=request.user),
        status__in=['pending', 'active'],
    ).select_related('creator', 'opponent', 'creator__profile', 'opponent__profile')

    recent_games = ChessGame.objects.filter(
        Q(creator=request.user) | Q(opponent=request.user),
        status='completed',
    ).select_related(
        'creator', 'opponent', 'winner',
        'creator__profile', 'opponent__profile',
    )[:10]

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    return render(request, 'chess/lobby.html', {
        'pending_games': pending_games,
        'recent_games': recent_games,
        'max_stake': max_stake,
    })


@login_required
@rate_limit('chess_challenge', max_requests=10, window=60)
def create_game(request):
    if request.method != 'POST':
        return redirect('chess_lobby')

    opponent_username = request.POST.get('opponent_username', '').strip()
    stake_raw = request.POST.get('stake', 0)
    creator_side = request.POST.get('side', 'random')

    try:
        stake = int(stake_raw)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid stake amount.')
        return redirect('chess_lobby')

    if stake <= 0:
        messages.error(request, 'Stake must be positive.')
        return redirect('chess_lobby')

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    if stake > max_stake:
        messages.error(request, f'Maximum stake is {max_stake} LC.')
        return redirect('chess_lobby')

    if creator_side not in ('white', 'black', 'random'):
        creator_side = 'random'

    try:
        opponent = User.objects.get(username=opponent_username)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('chess_lobby')

    if opponent == request.user:
        messages.error(request, 'You cannot challenge yourself.')
        return redirect('chess_lobby')

    if request.user.profile.balance < stake:
        messages.error(request, 'Insufficient balance.')
        return redirect('chess_lobby')

    if opponent.profile.balance < stake:
        messages.error(request, f'{opponent.username} does not have enough coins.')
        return redirect('chess_lobby')

    existing = ChessGame.objects.filter(
        creator=request.user, opponent=opponent, status='pending'
    ).exists()
    if existing:
        messages.error(request, f'You already have a pending chess challenge with {opponent.username}.')
        return redirect('chess_lobby')

    game = ChessGame.objects.create(
        creator=request.user,
        opponent=opponent,
        stake=stake,
        creator_side=creator_side,
    )

    Notification.objects.create(
        user=opponent,
        notif_type='game_invite',
        title='Chess Challenge!',
        message=f'{request.user.profile.get_display_name()} challenged you to a chess match for {stake} LC!',
        link=f'/chess/play/{game.pk}/',
    )

    return redirect('chess_play', game_id=game.pk)


@login_required
def play_view(request, game_id):
    game = get_object_or_404(ChessGame, pk=game_id)

    if request.user.pk not in (game.creator_id, game.opponent_id):
        messages.error(request, 'You are not part of this game.')
        return redirect('chess_lobby')

    return render(request, 'chess/play.html', {
        'game': game,
        'is_creator': request.user.pk == game.creator_id,
    })


@login_required
def decline_game(request, game_id):
    if request.method != 'POST':
        return redirect('chess_lobby')
    game = get_object_or_404(
        ChessGame, pk=game_id, opponent=request.user, status='pending'
    )
    game.status = 'cancelled'
    game.end_reason = 'cancelled'
    game.save(update_fields=['status', 'end_reason'])
    messages.info(request, 'Chess challenge declined.')
    return redirect('chess_lobby')
