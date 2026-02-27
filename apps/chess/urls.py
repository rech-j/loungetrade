from django.urls import path
from . import views

urlpatterns = [
    path('', views.lobby_view, name='chess_lobby'),
    path('challenge/', views.create_game, name='chess_create'),
    path('play/<int:game_id>/', views.play_view, name='chess_play'),
    path('decline/<int:game_id>/', views.decline_game, name='chess_decline'),
]
