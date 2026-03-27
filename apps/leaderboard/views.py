from datetime import timedelta

from django.conf import settings
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.economy.models import Transaction


def _bulk_deltas(user_ids, since):
    """Compute 24-hour balance deltas for a set of user IDs in a single query.

    Uses conditional aggregation so the database does the work instead of Python.
    Returns a dict mapping user_id → net delta.
    """
    if not user_ids:
        return {}

    qs = (
        Transaction.objects
        .filter(created_at__gte=since)
        .filter(Q(sender_id__in=user_ids) | Q(receiver_id__in=user_ids))
        .values('id')  # dummy grouping so we can annotate per-row
    )

    # It's cleaner to aggregate from the User side: for each user, sum
    # received amounts minus sent amounts in a single pass.
    from django.contrib.auth.models import User

    deltas_qs = (
        User.objects
        .filter(pk__in=user_ids)
        .annotate(
            received=Sum(
                Case(
                    When(received_transactions__created_at__gte=since, then='received_transactions__amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            ),
            sent=Sum(
                Case(
                    When(sent_transactions__created_at__gte=since, then='sent_transactions__amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            ),
        )
        .values_list('pk', 'received', 'sent')
    )

    return {
        uid: (received or 0) - (sent or 0)
        for uid, received, sent in deltas_qs
    }


def leaderboard_view(request):
    size = getattr(settings, 'LEADERBOARD_SIZE', 50)
    profiles = list(
        UserProfile.objects.select_related('user')
        .filter(leaderboard_hidden=False)
        .order_by('-balance')[:size]
    )

    last_24h = timezone.now() - timedelta(hours=24)
    user_ids = [p.user_id for p in profiles]

    deltas = _bulk_deltas(user_ids, last_24h)

    for p in profiles:
        p.delta_24h = deltas.get(p.user_id, 0)

    user_rank = None
    user_profile = None
    user_in_list = False

    if request.user.is_authenticated:
        user_balance = request.user.profile.balance
        user_rank = UserProfile.objects.filter(
            balance__gt=user_balance, leaderboard_hidden=False,
        ).count() + 1
        user_in_list = any(p.user_id == request.user.id for p in profiles)

        if not user_in_list:
            user_profile = request.user.profile
            uid = request.user.id
            user_delta = _bulk_deltas([uid], last_24h)
            user_profile.delta_24h = user_delta.get(uid, 0)

    return render(request, 'leaderboard/index.html', {
        'profiles': profiles,
        'user_rank': user_rank,
        'user_profile': user_profile,
        'user_in_list': user_in_list,
    })
