from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from apps.accounts.views import landing_page


def health_check(request):
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='/static/favicon/favicon.ico', permanent=True)),
    path('health/', health_check, name='health_check'),
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('apps.accounts.urls')),
    path('economy/', include('apps.economy.urls')),
    path('coinflip/', include('apps.coinflip.urls')),
    path('chess/', include('apps.chess.urls')),
    path('poker/', include('apps.poker.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('leaderboard/', include('apps.leaderboard.urls')),
    path('', landing_page, name='landing'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
