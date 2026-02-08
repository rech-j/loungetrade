from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import landing_page

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('apps.accounts.urls')),
    path('economy/', include('apps.economy.urls')),
    path('games/', include('apps.games.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('leaderboard/', include('apps.leaderboard.urls')),
    path('', landing_page, name='landing'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
