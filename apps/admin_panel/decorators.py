from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def admin_required(view_func):
    """Require login + is_admin_user on the user's profile."""
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.profile.is_admin_user:
            return HttpResponseForbidden('Access denied.')
        return view_func(request, *args, **kwargs)
    return wrapped
