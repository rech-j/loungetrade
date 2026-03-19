from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import rate_limit
from apps.chess.models import ChessGame
from apps.coinflip.models import CoinFlipChallenge
from apps.economy.models import Transaction
from apps.economy.services import InvalidTrade, mint_coins
from apps.poker.models import PokerPlayer, PokerTable

from .decorators import admin_required
from .forms import BalanceAdjustmentForm, RefundForm
from .services import (
    admin_cancel_chess,
    admin_cancel_coinflip,
    admin_cancel_poker,
    admin_deduct_coins,
    admin_refund_game,
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_required
def dashboard_view(request):
    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # User stats
    total_users = User.objects.count()
    new_users_7d = User.objects.filter(date_joined__gte=seven_days_ago).count()
    new_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()
    top_balances = User.objects.select_related('profile').order_by(
        '-profile__balance'
    )[:5]

    # Game stats
    coinflip_stats = CoinFlipChallenge.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        avg_stake=Avg('stake'),
    )
    chess_stats = ChessGame.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        active=Count('id', filter=Q(status='active')),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        avg_stake=Avg('stake'),
    )
    poker_stats = PokerTable.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        active=Count('id', filter=Q(status='active')),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        avg_stake=Avg('stake'),
    )

    # Economy stats
    from apps.accounts.models import UserProfile
    total_circulation = UserProfile.objects.aggregate(total=Sum('balance'))['total'] or 0
    tx_sums = Transaction.objects.aggregate(
        total_minted=Sum('amount', filter=Q(tx_type='mint')),
        total_traded=Sum('amount', filter=Q(tx_type='trade')),
        total_wagered=Sum('amount', filter=Q(tx_type__in=['game', 'game_win', 'game_loss'])),
    )

    return render(request, 'admin_panel/dashboard.html', {
        'total_users': total_users,
        'new_users_7d': new_users_7d,
        'new_users_30d': new_users_30d,
        'top_balances': top_balances,
        'coinflip_stats': coinflip_stats,
        'chess_stats': chess_stats,
        'poker_stats': poker_stats,
        'total_circulation': total_circulation,
        'total_minted': tx_sums['total_minted'] or 0,
        'total_traded': tx_sums['total_traded'] or 0,
        'total_wagered': tx_sums['total_wagered'] or 0,
    })


@admin_required
def live_stats_partial(request):
    """HTMX partial for real-time monitoring cards."""
    active_coinflips = CoinFlipChallenge.objects.filter(status='pending').count()
    active_chess = ChessGame.objects.filter(status='active').count()
    pending_chess = ChessGame.objects.filter(status='pending').count()
    active_poker = PokerTable.objects.filter(status='active').count()
    pending_poker = PokerTable.objects.filter(status='pending').count()

    return render(request, 'admin_panel/partials/stats_cards.html', {
        'active_coinflips': active_coinflips,
        'active_chess': active_chess,
        'pending_chess': pending_chess,
        'active_poker': active_poker,
        'pending_poker': pending_poker,
    })


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@admin_required
def user_list_view(request):
    users = User.objects.select_related('profile').order_by('-date_joined')

    q = request.GET.get('q', '').strip()
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(profile__display_name__icontains=q)
        )

    sort = request.GET.get('sort', '')
    if sort == 'balance':
        users = users.order_by('-profile__balance')
    elif sort == 'username':
        users = users.order_by('username')
    elif sort == 'oldest':
        users = users.order_by('date_joined')

    paginator = Paginator(users, 25)
    page = paginator.get_page(request.GET.get('page'))

    if request.htmx:
        return render(request, 'admin_panel/partials/user_rows.html', {
            'page': page, 'q': q, 'sort': sort,
        })

    return render(request, 'admin_panel/users/list.html', {
        'page': page, 'q': q, 'sort': sort,
    })


@admin_required
def user_detail_view(request, user_id):
    target = get_object_or_404(User.objects.select_related('profile'), pk=user_id)

    # Per-game stats
    coinflip_stats = CoinFlipChallenge.objects.filter(
        Q(challenger=target) | Q(opponent=target)
    ).aggregate(
        total=Count('id'),
        wins=Count('id', filter=Q(winner=target)),
        total_wagered=Sum('stake'),
    )
    chess_stats = ChessGame.objects.filter(
        Q(creator=target) | Q(opponent=target)
    ).aggregate(
        total=Count('id'),
        wins=Count('id', filter=Q(winner=target)),
        total_wagered=Sum('stake'),
    )
    poker_stats = PokerPlayer.objects.filter(user=target).aggregate(
        total=Count('id'),
        total_invested=Sum('coins_invested'),
    )

    recent_txs = Transaction.objects.filter(
        Q(sender=target) | Q(receiver=target)
    ).select_related('sender', 'receiver').order_by('-created_at')[:20]

    return render(request, 'admin_panel/users/detail.html', {
        'target': target,
        'coinflip_stats': coinflip_stats,
        'chess_stats': chess_stats,
        'poker_stats': poker_stats,
        'recent_txs': recent_txs,
        'balance_form': BalanceAdjustmentForm(),
    })


@admin_required
@require_POST
@rate_limit('admin_action', max_requests=30, window=60)
def adjust_balance_view(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    form = BalanceAdjustmentForm(request.POST)

    if form.is_valid():
        amount = form.cleaned_data['amount']
        note = form.cleaned_data['note']
        try:
            if amount > 0:
                mint_coins(
                    admin_user=request.user,
                    target_user=target,
                    amount=amount,
                    note=note,
                )
                messages.success(request, f'Added {amount} coins to {target.username}.')
            else:
                admin_deduct_coins(
                    admin_user=request.user,
                    target_user=target,
                    amount=abs(amount),
                    note=note,
                )
                messages.success(request, f'Deducted {abs(amount)} coins from {target.username}.')
        except (InvalidTrade, ValueError) as e:
            messages.error(request, str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')

    return redirect('admin_user_detail', user_id=user_id)


@admin_required
@require_POST
@rate_limit('admin_action', max_requests=30, window=60)
def toggle_admin_view(request, user_id):
    target = get_object_or_404(User.objects.select_related('profile'), pk=user_id)

    if target == request.user:
        messages.error(request, 'You cannot change your own admin status.')
        return redirect('admin_user_detail', user_id=user_id)

    target.profile.is_admin_user = not target.profile.is_admin_user
    target.profile.save(update_fields=['is_admin_user'])

    status = 'granted' if target.profile.is_admin_user else 'revoked'
    messages.success(request, f'Admin access {status} for {target.username}.')
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
@require_POST
@rate_limit('admin_action', max_requests=30, window=60)
def toggle_active_view(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_user_detail', user_id=user_id)

    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])

    status = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'Account {status} for {target.username}.')
    return redirect('admin_user_detail', user_id=user_id)


# ---------------------------------------------------------------------------
# Game Management
# ---------------------------------------------------------------------------

@admin_required
def game_list_view(request):
    game_type = request.GET.get('type', 'all')
    status_filter = request.GET.get('status', 'all')

    games = []

    if game_type in ('all', 'coinflip'):
        qs = CoinFlipChallenge.objects.select_related(
            'challenger', 'opponent', 'winner',
        ).order_by('-created_at')
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)
        for g in qs:
            games.append({
                'type': 'coinflip',
                'id': g.pk,
                'players': f'{g.challenger.username} vs {g.opponent.username}',
                'stake': g.stake,
                'status': g.status,
                'created_at': g.created_at,
            })

    if game_type in ('all', 'chess'):
        qs = ChessGame.objects.select_related(
            'creator', 'opponent', 'winner',
        ).order_by('-created_at')
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)
        for g in qs:
            games.append({
                'type': 'chess',
                'id': g.pk,
                'players': f'{g.creator.username} vs {g.opponent.username}',
                'stake': g.stake,
                'status': g.status,
                'created_at': g.created_at,
            })

    if game_type in ('all', 'poker'):
        qs = PokerTable.objects.select_related('creator').order_by('-created_at')
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)
        for g in qs:
            player_count = g.players.count()
            games.append({
                'type': 'poker',
                'id': g.pk,
                'players': f'{g.creator.username} + {player_count} players',
                'stake': g.stake,
                'status': g.status,
                'created_at': g.created_at,
            })

    # Sort combined list by created_at desc
    games.sort(key=lambda g: g['created_at'], reverse=True)

    paginator = Paginator(games, 25)
    page = paginator.get_page(request.GET.get('page'))

    if request.htmx:
        return render(request, 'admin_panel/partials/game_rows.html', {
            'page': page, 'game_type': game_type, 'status_filter': status_filter,
        })

    return render(request, 'admin_panel/games/list.html', {
        'page': page, 'game_type': game_type, 'status_filter': status_filter,
    })


@admin_required
def game_detail_view(request, game_type, game_id):
    context = {'game_type': game_type, 'game_id': game_id}

    if game_type == 'coinflip':
        game = get_object_or_404(
            CoinFlipChallenge.objects.select_related('challenger', 'opponent', 'winner'),
            pk=game_id,
        )
        context['game'] = game
        context['can_cancel'] = game.status == 'pending'
        context['can_refund'] = game.status == 'completed'
    elif game_type == 'chess':
        game = get_object_or_404(
            ChessGame.objects.select_related('creator', 'opponent', 'winner', 'white_player', 'black_player'),
            pk=game_id,
        )
        context['game'] = game
        context['can_cancel'] = game.status in ('pending', 'active')
        context['can_refund'] = game.status == 'completed'
    elif game_type == 'poker':
        game = get_object_or_404(
            PokerTable.objects.select_related('creator'),
            pk=game_id,
        )
        context['game'] = game
        context['players'] = game.players.select_related('user').order_by('seat')
        context['can_cancel'] = game.status in ('pending', 'active')
        context['can_refund'] = game.status == 'completed'
    else:
        return HttpResponseForbidden('Invalid game type.')

    context['refund_form'] = RefundForm()
    return render(request, 'admin_panel/games/detail.html', context)


@admin_required
@require_POST
@rate_limit('admin_action', max_requests=30, window=60)
def cancel_game_view(request, game_type, game_id):
    try:
        if game_type == 'coinflip':
            admin_cancel_coinflip(request.user, game_id)
        elif game_type == 'chess':
            admin_cancel_chess(request.user, game_id)
        elif game_type == 'poker':
            admin_cancel_poker(request.user, game_id)
        else:
            messages.error(request, 'Invalid game type.')
            return redirect('admin_games')
        messages.success(request, f'{game_type.title()} game #{game_id} cancelled.')
    except Exception as e:
        messages.error(request, f'Failed to cancel: {e}')

    return redirect('admin_game_detail', game_type=game_type, game_id=game_id)


@admin_required
@require_POST
@rate_limit('admin_action', max_requests=30, window=60)
def refund_game_view(request, game_type, game_id):
    form = RefundForm(request.POST)
    if form.is_valid():
        try:
            target = User.objects.get(pk=form.cleaned_data['user_id'])
            admin_refund_game(
                admin_user=request.user,
                target_user=target,
                amount=form.cleaned_data['amount'],
                game_type=game_type,
                game_id=game_id,
                note=form.cleaned_data['note'],
            )
            messages.success(
                request,
                f'Refunded {form.cleaned_data["amount"]} coins to {target.username}.'
            )
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except (InvalidTrade, ValueError) as e:
            messages.error(request, str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')

    return redirect('admin_game_detail', game_type=game_type, game_id=game_id)


# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------

@admin_required
def transaction_list_view(request):
    txs = Transaction.objects.select_related('sender', 'receiver').order_by('-created_at')

    tx_type = request.GET.get('type', '')
    if tx_type:
        txs = txs.filter(tx_type=tx_type)

    user_q = request.GET.get('user', '').strip()
    if user_q:
        txs = txs.filter(
            Q(sender__username__icontains=user_q) | Q(receiver__username__icontains=user_q)
        )

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        txs = txs.filter(created_at__date__gte=date_from)
    if date_to:
        txs = txs.filter(created_at__date__lte=date_to)

    paginator = Paginator(txs, 50)
    page = paginator.get_page(request.GET.get('page'))

    if request.htmx:
        return render(request, 'admin_panel/partials/transaction_rows.html', {
            'page': page, 'tx_type': tx_type, 'user_q': user_q,
            'date_from': date_from, 'date_to': date_to,
        })

    return render(request, 'admin_panel/economy/transactions.html', {
        'page': page, 'tx_type': tx_type, 'user_q': user_q,
        'date_from': date_from, 'date_to': date_to,
    })


@admin_required
def economy_stats_view(request):
    from apps.accounts.models import UserProfile

    total_circulation = UserProfile.objects.aggregate(total=Sum('balance'))['total'] or 0
    total_minted = Transaction.objects.filter(tx_type='mint').aggregate(
        total=Sum('amount')
    )['total'] or 0

    # Daily volume for last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_volume = (
        Transaction.objects.filter(created_at__gte=thirty_days_ago)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(
            mint_volume=Sum('amount', filter=Q(tx_type='mint')),
            trade_volume=Sum('amount', filter=Q(tx_type='trade')),
            game_volume=Sum('amount', filter=Q(tx_type__in=['game', 'game_win', 'game_loss'])),
            tx_count=Count('id'),
        )
        .order_by('-date')
    )

    # Top 10 holders
    top_holders = User.objects.select_related('profile').order_by(
        '-profile__balance'
    )[:10]

    return render(request, 'admin_panel/economy/stats.html', {
        'total_circulation': total_circulation,
        'total_minted': total_minted,
        'daily_volume': daily_volume,
        'top_holders': top_holders,
    })
