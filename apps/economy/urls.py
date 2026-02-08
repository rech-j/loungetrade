from django.urls import path

from . import views

urlpatterns = [
    path('trade/', views.trade_view, name='trade'),
    path('mint/', views.mint_view, name='mint'),
    path('history/', views.history_view, name='history'),
]
