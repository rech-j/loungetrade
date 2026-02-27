from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.economy.models import Transaction
from apps.games.models import GameChallenge

from .decorators import rate_limit
from .forms import ProfileEditForm


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('profile')
    return render(request, 'landing.html')


@login_required
def profile_view(request):
    profile = request.user.profile
    transactions = Transaction.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).select_related('sender', 'receiver').order_by('-created_at')[:20]

    completed_games = GameChallenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user),
        status='completed',
    )
    games_played = completed_games.count()
    games_won = completed_games.filter(winner=request.user).count()
    win_rate = round(games_won / games_played * 100, 1) if games_played > 0 else 0
    total_wagered = completed_games.aggregate(total=Sum('stake'))['total'] or 0

    return render(request, 'accounts/profile.html', {
        'profile': profile,
        'transactions': transactions,
        'games_played': games_played,
        'games_won': games_won,
        'win_rate': win_rate,
        'total_wagered': total_wagered,
    })


@login_required
def profile_edit_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ProfileEditForm(instance=profile)
    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def toggle_dark_mode(request):
    if request.method == 'POST':
        profile = request.user.profile
        profile.dark_mode = not profile.dark_mode
        profile.save(update_fields=['dark_mode'])
    # HTMX requests: return empty response (client toggles class directly)
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204)
    referer = request.META.get('HTTP_REFERER', '/')
    if not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        referer = '/'
    return redirect(referer)


@login_required
@rate_limit('user_search', max_requests=30, window=60)
def user_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return render(request, 'accounts/partials/user_list.html', {'users': []})
    from django.contrib.auth.models import User
    users = User.objects.filter(
        username__icontains=q
    ).exclude(
        pk=request.user.pk
    ).select_related('profile')[:10]
    return render(request, 'accounts/partials/user_list.html', {'users': users})


@login_required
@rate_limit('user_search', max_requests=30, window=60)
def user_search_json(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'users': []})
    from django.contrib.auth.models import User
    users = User.objects.filter(
        username__icontains=q
    ).exclude(
        pk=request.user.pk
    ).select_related('profile')[:10]
    return JsonResponse({
        'users': [
            {'id': u.pk, 'username': u.username, 'display_name': u.profile.get_display_name()}
            for u in users
        ]
    })


@login_required
def balance_check(request):
    """HTMX endpoint for real-time balance updates in the nav bar."""
    balance = request.user.profile.balance
    return HttpResponse(f'{balance} coins')
