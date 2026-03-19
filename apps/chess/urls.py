from django.urls import path
from . import views

urlpatterns = [
    path('', views.lobby_view, name='chess_lobby'),
    path('archive/', views.archive_view, name='chess_archive'),
    path('live/', views.live_games, name='chess_live'),
    path('challenge/', views.create_game, name='chess_create'),
    path('play/<int:game_id>/', views.play_view, name='chess_play'),
    path('decline/<int:game_id>/', views.decline_game, name='chess_decline'),
    path('cancel/<int:game_id>/', views.cancel_game, name='chess_cancel'),
    path('pgn/<int:game_id>/', views.export_pgn, name='chess_pgn'),
    path('rematch/<int:game_id>/', views.rematch, name='chess_rematch'),
]
