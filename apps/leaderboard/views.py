from django.shortcuts import render

from apps.accounts.models import UserProfile


def leaderboard_view(request):
    profiles = UserProfile.objects.select_related('user').order_by('-balance')[:50]
    return render(request, 'leaderboard/index.html', {
        'profiles': profiles,
    })
