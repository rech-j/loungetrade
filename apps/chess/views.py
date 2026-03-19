import chess

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import rate_limit
from apps.notifications.services import send_notification

from .models import ChessGame, TIME_CONTROL, TIME_CONTROL_CHOICES, TIME_CONTROL_VALUES


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
        'time_controls': TIME_CONTROL_CHOICES,
    })


@login_required
@rate_limit('chess_challenge', max_requests=10, window=60)
def create_game(request):
    if request.method != 'POST':
        return redirect('chess_lobby')

    opponent_username = request.POST.get('opponent_username', '').strip()
    stake_raw = request.POST.get('stake', 0)
    creator_side = request.POST.get('side', 'random')
    time_control_raw = request.POST.get('time_control', TIME_CONTROL)

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
        time_control = int(time_control_raw)
    except (ValueError, TypeError):
        time_control = TIME_CONTROL
    if time_control not in TIME_CONTROL_VALUES:
        time_control = TIME_CONTROL

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
        time_control=time_control,
    )

    tc_label = dict(TIME_CONTROL_CHOICES).get(time_control, f'{time_control}s')
    send_notification(
        opponent,
        'game_invite',
        'Chess Challenge!',
        f'{request.user.profile.get_display_name()} challenged you to a chess match for {stake} LC ({tc_label})!',
        link=f'/chess/play/{game.pk}/',
    )

    return redirect('chess_play', game_id=game.pk)


@login_required
def play_view(request, game_id):
    game = get_object_or_404(ChessGame, pk=game_id)

    is_participant = request.user.pk in (game.creator_id, game.opponent_id)

    # Non-participants can spectate active or completed games
    if not is_participant:
        if game.status not in ('active', 'completed'):
            messages.error(request, 'This game is not available to spectate.')
            return redirect('chess_lobby')

    return render(request, 'chess/play.html', {
        'game': game,
        'is_creator': request.user.pk == game.creator_id,
        'is_spectator': not is_participant,
    })


@login_required
def live_games(request):
    games = ChessGame.objects.filter(
        status='active',
    ).select_related(
        'creator', 'opponent', 'white_player', 'black_player',
        'creator__profile', 'opponent__profile',
    ).order_by('-started_at')

    return render(request, 'chess/live.html', {
        'games': games,
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


@login_required
def cancel_game(request, game_id):
    if request.method != 'POST':
        return redirect('chess_lobby')
    game = get_object_or_404(
        ChessGame, pk=game_id, creator=request.user, status='pending'
    )
    game.status = 'cancelled'
    game.end_reason = 'cancelled'
    game.save(update_fields=['status', 'end_reason'])
    messages.info(request, 'Chess challenge cancelled.')
    return redirect('chess_lobby')


@login_required
def archive_view(request):
    games = ChessGame.objects.filter(
        Q(creator=request.user) | Q(opponent=request.user),
        status='completed',
    ).select_related(
        'creator', 'opponent', 'winner',
        'creator__profile', 'opponent__profile',
    )

    result_filter = request.GET.get('result', 'all')
    if result_filter == 'wins':
        games = games.filter(winner=request.user)
    elif result_filter == 'losses':
        games = games.filter(winner__isnull=False).exclude(winner=request.user)
    elif result_filter == 'draws':
        games = games.filter(winner__isnull=True)

    opponent_query = request.GET.get('opponent', '').strip()
    if opponent_query:
        games = games.filter(
            Q(creator=request.user, opponent__username__icontains=opponent_query) |
            Q(opponent=request.user, creator__username__icontains=opponent_query)
        )

    paginator = Paginator(games, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'chess/archive.html', {
        'page': page,
        'result_filter': result_filter,
        'opponent_query': opponent_query,
    })


@login_required
@rate_limit('chess_challenge', max_requests=10, window=60)
def rematch(request, game_id):
    if request.method != 'POST':
        return redirect('chess_lobby')

    game = get_object_or_404(ChessGame, pk=game_id, status='completed')

    # Only participants can rematch
    if request.user.pk not in (game.creator_id, game.opponent_id):
        messages.error(request, 'You are not a participant in this game.')
        return redirect('chess_lobby')

    opponent = game.get_other_player(request.user)

    # Check balances
    if request.user.profile.balance < game.stake:
        messages.error(request, 'Insufficient balance for rematch.')
        return redirect('chess_play', game_id=game.pk)

    if opponent.profile.balance < game.stake:
        messages.error(request, f'{opponent.username} does not have enough coins.')
        return redirect('chess_play', game_id=game.pk)

    # Prevent duplicate pending rematch
    existing = ChessGame.objects.filter(
        creator=request.user, opponent=opponent, status='pending'
    ).exists()
    if existing:
        messages.error(request, f'You already have a pending challenge with {opponent.username}.')
        return redirect('chess_play', game_id=game.pk)

    new_game = ChessGame.objects.create(
        creator=request.user,
        opponent=opponent,
        stake=game.stake,
        time_control=game.time_control,
        creator_side='random',
    )

    tc_label = dict(TIME_CONTROL_CHOICES).get(game.time_control, f'{game.time_control}s')
    send_notification(
        opponent,
        'game_invite',
        'Rematch!',
        f'{request.user.profile.get_display_name()} wants a rematch for {game.stake} LC ({tc_label})!',
        link=f'/chess/play/{new_game.pk}/',
    )

    return redirect('chess_play', game_id=new_game.pk)


@login_required
def export_pgn(request, game_id):
    game = get_object_or_404(ChessGame, pk=game_id, status='completed')

    # Build PGN headers
    white_name = game.white_player.username if game.white_player else '?'
    black_name = game.black_player.username if game.black_player else '?'

    if game.winner_id == game.white_player_id:
        result = '1-0'
    elif game.winner_id == game.black_player_id:
        result = '0-1'
    elif game.winner_id is None:
        result = '1/2-1/2'
    else:
        result = '*'

    tc_label = dict(TIME_CONTROL_CHOICES).get(game.time_control, str(game.time_control))

    headers = [
        f'[Event "LoungeTrade Chess"]',
        f'[Site "loungecoin.trade"]',
        f'[Date "{game.created_at.strftime("%Y.%m.%d")}"]',
        f'[White "{white_name}"]',
        f'[Black "{black_name}"]',
        f'[Result "{result}"]',
        f'[TimeControl "{game.time_control}"]',
        f'[Termination "{game.get_end_reason_display()}"]',
    ]

    # Replay UCI moves to get SAN notation
    board = chess.Board()
    san_moves = []
    if game.moves_uci:
        for uci_str in game.moves_uci.split():
            move = chess.Move.from_uci(uci_str)
            if move in board.legal_moves:
                san_moves.append(board.san(move))
                board.push(move)

    # Format move text (80 char line wrap)
    move_parts = []
    for i, san in enumerate(san_moves):
        if i % 2 == 0:
            move_parts.append(f'{i // 2 + 1}. {san}')
        else:
            move_parts.append(san)
    move_parts.append(result)

    lines = []
    current_line = ''
    for part in move_parts:
        if current_line and len(current_line) + 1 + len(part) > 80:
            lines.append(current_line)
            current_line = part
        else:
            current_line = (current_line + ' ' + part).strip()
    if current_line:
        lines.append(current_line)

    pgn = '\n'.join(headers) + '\n\n' + '\n'.join(lines) + '\n'

    filename = f'chess_{game.pk}_{white_name}_vs_{black_name}.pgn'
    response = HttpResponse(pgn, content_type='application/x-chess-pgn')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
