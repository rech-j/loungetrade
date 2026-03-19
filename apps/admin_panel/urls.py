from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard_view, name='admin_dashboard'),
    path('stats/', views.live_stats_partial, name='admin_stats_partial'),
    # Users
    path('users/', views.user_list_view, name='admin_users'),
    path('users/<int:user_id>/', views.user_detail_view, name='admin_user_detail'),
    path('users/<int:user_id>/adjust-balance/', views.adjust_balance_view, name='admin_adjust_balance'),
    path('users/<int:user_id>/toggle-admin/', views.toggle_admin_view, name='admin_toggle_admin'),
    path('users/<int:user_id>/toggle-active/', views.toggle_active_view, name='admin_toggle_active'),
    # Games
    path('games/', views.game_list_view, name='admin_games'),
    path('games/<str:game_type>/<int:game_id>/', views.game_detail_view, name='admin_game_detail'),
    path('games/<str:game_type>/<int:game_id>/cancel/', views.cancel_game_view, name='admin_cancel_game'),
    path('games/<str:game_type>/<int:game_id>/refund/', views.refund_game_view, name='admin_refund_game'),
    # Economy
    path('economy/', views.transaction_list_view, name='admin_transactions'),
    path('economy/stats/', views.economy_stats_view, name='admin_economy_stats'),
]
