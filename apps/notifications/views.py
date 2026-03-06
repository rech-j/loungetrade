from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme


def _get_active_games(user):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge

    chess_games = ChessGame.objects.filter(
        Q(creator=user) | Q(opponent=user),
        status__in=['pending', 'active'],
    ).select_related('creator', 'opponent').order_by('status', '-created_at')[:3]

    coinflip_games = CoinFlipChallenge.objects.filter(
        Q(challenger=user) | Q(opponent=user),
        status='pending',
    ).select_related('challenger', 'opponent').order_by('-created_at')[:3]

    return chess_games, coinflip_games


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:50]
    return render(request, 'notifications/list.html', {
        'notifications': notifications,
    })


@login_required
def unread_partial(request):
    user = request.user
    unread_qs = user.notifications.filter(is_read=False)
    count = unread_qs.count()
    notifications = unread_qs[:5]
    chess_games, coinflip_games = _get_active_games(user)
    return render(request, 'notifications/partials/dropdown.html', {
        'notifications': notifications,
        'unread_count': count,
        'chess_games': chess_games,
        'coinflip_games': coinflip_games,
    })


@login_required
def unread_count(request):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge

    user = request.user
    count = user.notifications.filter(is_read=False).count()
    has_game_activity = (
        ChessGame.objects.filter(
            Q(creator=user) | Q(opponent=user),
            status__in=['pending', 'active'],
        ).exists()
        or CoinFlipChallenge.objects.filter(
            Q(challenger=user) | Q(opponent=user),
            status='pending',
        ).exists()
    )
    return render(request, 'notifications/partials/badge.html', {
        'unread_count': count,
        'has_game_activity': has_game_activity,
    })


@login_required
def mark_read(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    request.user.notifications.filter(pk=pk).update(is_read=True)
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/notifications/'))
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = '/notifications/'
    return redirect(next_url)


@login_required
def mark_all_read(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('notification_list')


@login_required
def game_activity_badge(request):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge

    user = request.user

    # Pending challenges toward you (chess + coinflip)
    chess_challenges = ChessGame.objects.filter(
        opponent=user, status='pending',
    ).count()
    coinflip_challenges = CoinFlipChallenge.objects.filter(
        opponent=user, status='pending',
    ).count()
    pending_challenges = chess_challenges + coinflip_challenges

    # Active games you're in (chess only - coinflip resolves instantly)
    active_games = ChessGame.objects.filter(
        Q(creator=user) | Q(opponent=user),
        status='active',
    ).count()

    return render(request, 'notifications/partials/game_activity.html', {
        'pending_challenges': pending_challenges,
        'active_games': active_games,
        'total_activity': pending_challenges + active_games,
    })


@login_required
def game_activity_mobile(request):
    chess_games, coinflip_games = _get_active_games(request.user)
    return render(request, 'notifications/partials/game_activity_mobile.html', {
        'chess_games': chess_games,
        'coinflip_games': coinflip_games,
    })
