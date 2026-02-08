from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'balance', 'is_admin_user', 'created_at')
    list_filter = ('is_admin_user',)
    search_fields = ('user__username', 'display_name')
    readonly_fields = ('created_at',)
