from django.conf import settings
from django.shortcuts import render

from apps.accounts.models import UserProfile


def leaderboard_view(request):
    size = getattr(settings, 'LEADERBOARD_SIZE', 50)
    profiles = UserProfile.objects.select_related('user').order_by('-balance')[:size]

    user_rank = None
    if request.user.is_authenticated:
        user_balance = request.user.profile.balance
        user_rank = UserProfile.objects.filter(balance__gt=user_balance).count() + 1

    return render(request, 'leaderboard/index.html', {
        'profiles': profiles,
        'user_rank': user_rank,
    })
