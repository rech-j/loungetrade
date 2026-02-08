from django.urls import path

from . import views

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('unread/', views.unread_partial, name='notifications_unread'),
    path('unread-count/', views.unread_count, name='notifications_unread_count'),
    path('read/<int:pk>/', views.mark_read, name='notification_mark_read'),
    path('read-all/', views.mark_all_read, name='notifications_mark_all_read'),
]
