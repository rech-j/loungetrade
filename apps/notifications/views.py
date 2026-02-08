from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:50]
    return render(request, 'notifications/list.html', {
        'notifications': notifications,
    })


@login_required
def unread_partial(request):
    notifications = request.user.notifications.filter(is_read=False)[:5]
    count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'notifications/partials/dropdown.html', {
        'notifications': notifications,
        'unread_count': count,
    })


@login_required
def unread_count(request):
    count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'notifications/partials/badge.html', {
        'unread_count': count,
    })


@login_required
def mark_read(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    request.user.notifications.filter(pk=pk).update(is_read=True)
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/notifications/'))
    return redirect(next_url)


@login_required
def mark_all_read(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('notification_list')
