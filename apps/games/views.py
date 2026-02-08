from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rate_limit
from apps.notifications.models import Notification

from .models import GameChallenge

VALID_CHOICES = {'heads', 'tails'}


@login_required
def lobby_view(request):
    pending_challenges = GameChallenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user),
        status='pending',
    ).select_related('challenger', 'opponent', 'challenger__profile', 'opponent__profile')

    recent_games = GameChallenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user),
        status='completed',
    ).select_related(
        'challenger', 'opponent', 'winner',
        'challenger__profile', 'opponent__profile',
    )[:10]

    return render(request, 'games/lobby.html', {
        'pending_challenges': pending_challenges,
        'recent_games': recent_games,
    })


@login_required
@rate_limit('game_challenge', max_requests=10, window=60)
def create_challenge(request):
    if request.method != 'POST':
        return redirect('game_lobby')

    opponent_username = request.POST.get('opponent_username', '').strip()
    stake = request.POST.get('stake', 0)
    choice = request.POST.get('choice', 'heads')

    try:
        stake = int(stake)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid stake amount.')
        return redirect('game_lobby')

    if stake <= 0:
        messages.error(request, 'Stake must be positive.')
        return redirect('game_lobby')

    if choice not in VALID_CHOICES:
        messages.error(request, 'Invalid choice. Pick heads or tails.')
        return redirect('game_lobby')

    try:
        opponent = User.objects.get(username=opponent_username)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('game_lobby')

    if opponent == request.user:
        messages.error(request, 'You cannot challenge yourself.')
        return redirect('game_lobby')

    if request.user.profile.balance < stake:
        messages.error(request, 'You do not have enough coins.')
        return redirect('game_lobby')

    if opponent.profile.balance < stake:
        messages.error(request, f'{opponent.username} does not have enough coins.')
        return redirect('game_lobby')

    # Prevent duplicate pending challenges between same users
    existing = GameChallenge.objects.filter(
        challenger=request.user,
        opponent=opponent,
        status='pending',
    ).exists()
    if existing:
        messages.error(request, f'You already have a pending challenge with {opponent.username}.')
        return redirect('game_lobby')

    challenge = GameChallenge.objects.create(
        challenger=request.user,
        opponent=opponent,
        stake=stake,
        challenger_choice=choice,
    )

    Notification.objects.create(
        user=opponent,
        notif_type='game_invite',
        title='Game Challenge!',
        message=f'{request.user.profile.get_display_name()} challenged you to a coin flip for {stake} coins!',
        link=f'/games/play/{challenge.pk}/',
    )

    return redirect('game_play', challenge_id=challenge.pk)


@login_required
def play_view(request, challenge_id):
    challenge = get_object_or_404(GameChallenge, pk=challenge_id)

    if request.user.pk not in (challenge.challenger_id, challenge.opponent_id):
        messages.error(request, 'You are not part of this game.')
        return redirect('game_lobby')

    is_challenger = request.user.pk == challenge.challenger_id

    return render(request, 'games/play.html', {
        'challenge': challenge,
        'is_challenger': is_challenger,
    })
