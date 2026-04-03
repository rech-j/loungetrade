from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from apps.accounts.views import landing_page
from config.sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
}


def health_check(request):
    """Lightweight health check that verifies database connectivity."""
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'error', 'detail': 'database unavailable'}, status=503)


urlpatterns = [
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),
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
    path('admin-panel/', include('apps.admin_panel.urls')),
    path('', landing_page, name='landing'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
