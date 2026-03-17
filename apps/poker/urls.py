from django.urls import path

from . import views

urlpatterns = [
    path('', views.lobby_view, name='poker_lobby'),
    path('create/', views.create_table, name='poker_create'),
    path('join/<int:table_id>/', views.join_table, name='poker_join'),
    path('play/<int:table_id>/', views.play_view, name='poker_play'),
    path('leave/<int:table_id>/', views.leave_table, name='poker_leave'),
    path('start/<int:table_id>/', views.start_table, name='poker_start'),
]
