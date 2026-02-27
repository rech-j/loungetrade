from django.urls import path

from . import views

urlpatterns = [
    path('', views.lobby_view, name='coinflip_lobby'),
    path('challenge/', views.create_challenge, name='coinflip_create'),
    path('play/<int:challenge_id>/', views.play_view, name='coinflip_play'),
    path('decline/<int:challenge_id>/', views.decline_challenge, name='coinflip_decline'),
]
