from django.urls import path

from . import views

urlpatterns = [
    path('', views.lobby_view, name='game_lobby'),
    path('challenge/', views.create_challenge, name='create_challenge'),
    path('play/<int:challenge_id>/', views.play_view, name='game_play'),
]
