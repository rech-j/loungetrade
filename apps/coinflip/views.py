from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rate_limit
from apps.notifications.models import Notification

from .models import CoinFlipChallenge

VALID_CHOICES = {'heads', 'tails'}


@login_required
def lobby_view(request):
    pending_challenges = CoinFlipChallenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user),
        status='pending',
    ).select_related('challenger', 'opponent', 'challenger__profile', 'opponent__profile')

    recent_games = CoinFlipChallenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user),
        status='completed',
    ).select_related(
        'challenger', 'opponent', 'winner',
        'challenger__profile', 'opponent__profile',
    )[:10]

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    return render(request, 'coinflip/lobby.html', {
        'pending_challenges': pending_challenges,
        'recent_games': recent_games,
        'max_stake': max_stake,
    })


@login_required
@rate_limit('coinflip_challenge', max_requests=10, window=60)
def create_challenge(request):
    if request.method != 'POST':
        return redirect('coinflip_lobby')

    opponent_username = request.POST.get('opponent_username', '').strip()
    stake = request.POST.get('stake', 0)
    choice = request.POST.get('choice', 'heads')

    try:
        stake = int(stake)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid stake amount.')
        return redirect('coinflip_lobby')

    if stake <= 0:
        messages.error(request, 'Stake must be positive.')
        return redirect('coinflip_lobby')

    max_stake = getattr(settings, 'MAX_GAME_STAKE', 10000)
    if stake > max_stake:
        messages.error(request, f'Maximum stake is {max_stake} coins.')
        return redirect('coinflip_lobby')

    if choice not in VALID_CHOICES:
        messages.error(request, 'Invalid choice. Pick heads or tails.')
        return redirect('coinflip_lobby')

    try:
        opponent = User.objects.get(username=opponent_username)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('coinflip_lobby')

    if opponent == request.user:
        messages.error(request, 'You cannot challenge yourself.')
        return redirect('coinflip_lobby')

    if request.user.profile.balance < stake:
        messages.error(request, 'You do not have enough coins.')
        return redirect('coinflip_lobby')

    if opponent.profile.balance < stake:
        messages.error(request, f'{opponent.username} does not have enough coins.')
        return redirect('coinflip_lobby')

    # Prevent duplicate pending challenges between same users
    existing = CoinFlipChallenge.objects.filter(
        challenger=request.user,
        opponent=opponent,
        status='pending',
    ).exists()
    if existing:
        messages.error(request, f'You already have a pending challenge with {opponent.username}.')
        return redirect('coinflip_lobby')

    challenge = CoinFlipChallenge.objects.create(
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
        link=f'/coinflip/play/{challenge.pk}/',
    )

    return redirect('coinflip_play', challenge_id=challenge.pk)


@login_required
def play_view(request, challenge_id):
    challenge = get_object_or_404(CoinFlipChallenge, pk=challenge_id)

    if request.user.pk not in (challenge.challenger_id, challenge.opponent_id):
        messages.error(request, 'You are not part of this game.')
        return redirect('coinflip_lobby')

    is_challenger = request.user.pk == challenge.challenger_id

    return render(request, 'coinflip/play.html', {
        'challenge': challenge,
        'is_challenger': is_challenger,
    })


@login_required
def decline_challenge(request, challenge_id):
    """Decline a challenge without needing to open the WebSocket game page."""
    if request.method != 'POST':
        return redirect('coinflip_lobby')
    challenge = get_object_or_404(
        CoinFlipChallenge, pk=challenge_id, opponent=request.user, status='pending',
    )
    challenge.status = 'declined'
    challenge.save(update_fields=['status'])
    messages.info(request, 'Challenge declined.')
    return redirect('coinflip_lobby')
