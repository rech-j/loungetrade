from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.economy.models import Transaction


def leaderboard_view(request):
    size = getattr(settings, 'LEADERBOARD_SIZE', 50)
    profiles = list(UserProfile.objects.select_related('user').order_by('-balance')[:size])

    last_24h = timezone.now() - timedelta(hours=24)
    user_ids = [p.user_id for p in profiles]
    user_ids_set = set(user_ids)

    txns = Transaction.objects.filter(
        created_at__gte=last_24h
    ).filter(
        Q(sender_id__in=user_ids) | Q(receiver_id__in=user_ids)
    ).values('sender_id', 'receiver_id', 'amount')

    deltas = {}
    for t in txns:
        if t['receiver_id'] in user_ids_set:
            deltas[t['receiver_id']] = deltas.get(t['receiver_id'], 0) + t['amount']
        if t['sender_id'] in user_ids_set:
            deltas[t['sender_id']] = deltas.get(t['sender_id'], 0) - t['amount']

    for p in profiles:
        p.delta_24h = deltas.get(p.user_id, 0)

    user_rank = None
    user_profile = None
    user_in_list = False

    if request.user.is_authenticated:
        user_balance = request.user.profile.balance
        user_rank = UserProfile.objects.filter(balance__gt=user_balance).count() + 1
        user_in_list = any(p.user_id == request.user.id for p in profiles)

        if not user_in_list:
            user_profile = request.user.profile
            uid = request.user.id
            u_txns = Transaction.objects.filter(
                created_at__gte=last_24h
            ).filter(
                Q(sender_id=uid) | Q(receiver_id=uid)
            ).values('sender_id', 'receiver_id', 'amount')
            u_delta = 0
            for t in u_txns:
                if t['receiver_id'] == uid:
                    u_delta += t['amount']
                if t['sender_id'] == uid:
                    u_delta -= t['amount']
            user_profile.delta_24h = u_delta

    return render(request, 'leaderboard/index.html', {
        'profiles': profiles,
        'user_rank': user_rank,
        'user_profile': user_profile,
        'user_in_list': user_in_list,
    })
