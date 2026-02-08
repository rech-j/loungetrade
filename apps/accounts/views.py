from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.economy.models import Transaction

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
    return render(request, 'accounts/profile.html', {
        'profile': profile,
        'transactions': transactions,
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
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
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
