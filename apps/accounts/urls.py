from django.urls import path

from . import views

urlpatterns = [
    path('', views.profile_view, name='profile'),
    path('edit/', views.profile_edit_view, name='profile_edit'),
    path('toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    path('search/', views.user_search, name='user_search'),
    path('search/json/', views.user_search_json, name='user_search_json'),
    path('balance/', views.balance_check, name='balance_check'),
]
