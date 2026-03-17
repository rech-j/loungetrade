from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Notification
from .services import _ws_notify_all_read, _ws_notify_deleted, _ws_notify_read


def _get_active_games(user):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge
    from apps.poker.models import PokerPlayer, PokerTable

    chess_games = ChessGame.objects.filter(
        Q(creator=user) | Q(opponent=user),
        status__in=['pending', 'active'],
    ).select_related('creator', 'opponent').order_by('status', '-created_at')[:3]

    coinflip_games = CoinFlipChallenge.objects.filter(
        Q(challenger=user) | Q(opponent=user),
        status='pending',
    ).select_related('challenger', 'opponent').order_by('-created_at')[:3]

    poker_table_ids = PokerPlayer.objects.filter(
        user=user,
    ).exclude(
        status__in=['invited', 'left'],
    ).values_list('table_id', flat=True)
    poker_tables = PokerTable.objects.filter(
        pk__in=poker_table_ids,
        status__in=['pending', 'active'],
    ).select_related('creator', 'creator__profile').order_by('status', '-created_at')[:3]

    return chess_games, coinflip_games, poker_tables


@login_required
def notification_list(request):
    all_notifications = request.user.notifications.all()
    paginator = Paginator(all_notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    is_htmx_pagination = (
        request.headers.get('HX-Request') == 'true'
        and request.headers.get('HX-Target') == 'notification-list'
    )
    template = 'notifications/partials/notification_list_page.html' if is_htmx_pagination else 'notifications/list.html'

    return render(request, template, {
        'notifications': page_obj,
        'page_obj': page_obj,
    })


@login_required
def unread_partial(request):
    user = request.user
    unread_qs = user.notifications.filter(is_read=False)
    count = unread_qs.count()
    notifications = unread_qs[:5]
    chess_games, coinflip_games, poker_tables = _get_active_games(user)
    return render(request, 'notifications/partials/dropdown.html', {
        'notifications': notifications,
        'unread_count': count,
        'chess_games': chess_games,
        'coinflip_games': coinflip_games,
        'poker_tables': poker_tables,
    })


@login_required
def unread_count(request):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge
    from apps.poker.models import PokerPlayer, PokerTable

    user = request.user
    count = user.notifications.filter(is_read=False).count()

    poker_table_ids = PokerPlayer.objects.filter(
        user=user,
    ).exclude(
        status__in=['invited', 'left'],
    ).values_list('table_id', flat=True)

    has_game_activity = (
        ChessGame.objects.filter(
            Q(creator=user) | Q(opponent=user),
            status__in=['pending', 'active'],
        ).exists()
        or CoinFlipChallenge.objects.filter(
            Q(challenger=user) | Q(opponent=user),
            status='pending',
        ).exists()
        or PokerTable.objects.filter(
            pk__in=poker_table_ids,
            status__in=['pending', 'active'],
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

    notif = request.user.notifications.filter(pk=pk).first()
    if notif and not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        _ws_notify_read(request.user.pk, pk)

    if request.headers.get('HX-Request') == 'true':
        if notif:
            return render(request, 'notifications/partials/notification_row.html', {
                'n': notif,
            })
        return HttpResponse('')

    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/notifications/'))
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = '/notifications/'
    return redirect(next_url)


@login_required
def mark_all_read(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    request.user.notifications.filter(is_read=False).update(is_read=True)
    _ws_notify_all_read(request.user.pk)

    if request.headers.get('HX-Request') == 'true':
        count = 0
        return render(request, 'notifications/partials/badge.html', {
            'unread_count': count,
            'has_game_activity': False,
        })

    return redirect('notification_list')


@login_required
def delete_notification(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.delete()
    _ws_notify_deleted(request.user.pk, pk)

    if request.headers.get('HX-Request') == 'true':
        return HttpResponse('')

    return redirect('notification_list')


@login_required
def game_activity_badge(request):
    from apps.chess.models import ChessGame
    from apps.coinflip.models import CoinFlipChallenge
    from apps.poker.models import PokerPlayer, PokerTable

    user = request.user

    chess_challenges = ChessGame.objects.filter(
        opponent=user, status='pending',
    ).count()
    coinflip_challenges = CoinFlipChallenge.objects.filter(
        opponent=user, status='pending',
    ).count()
    pending_challenges = chess_challenges + coinflip_challenges

    active_chess = ChessGame.objects.filter(
        Q(creator=user) | Q(opponent=user),
        status='active',
    ).count()

    poker_table_ids = PokerPlayer.objects.filter(
        user=user,
    ).exclude(
        status__in=['invited', 'left'],
    ).values_list('table_id', flat=True)
    active_poker = PokerTable.objects.filter(
        pk__in=poker_table_ids,
        status__in=['pending', 'active'],
    ).count()

    active_games = active_chess + active_poker

    return render(request, 'notifications/partials/game_activity.html', {
        'pending_challenges': pending_challenges,
        'active_games': active_games,
        'total_activity': pending_challenges + active_games,
    })


@login_required
def game_activity_mobile(request):
    chess_games, coinflip_games, poker_tables = _get_active_games(request.user)
    return render(request, 'notifications/partials/game_activity_mobile.html', {
        'chess_games': chess_games,
        'coinflip_games': coinflip_games,
        'poker_tables': poker_tables,
    })
